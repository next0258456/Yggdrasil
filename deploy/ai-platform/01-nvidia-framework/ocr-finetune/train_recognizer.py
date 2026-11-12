"""
train_recognizer.py
Script huấn luyện Fine-tune Nemotron OCR v2 Recognizer cho Tiếng Việt:
- Thực hiện đúng Phương án 2 (DEPLOYMENT.md): Freeze CNN Encoder 9.8M, Train 26.3M tham số
- CTCLoss với Blank Token = 0
- Automatic Mixed Precision (AMP FP16) trên CUDA GPU
- Greedy CTC Decoder in kết quả đọc thử nghiệm trực tiếp theo từng epoch
"""

import os
import sys
import time
import argparse
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from vietnamese_charset import expand_charset_file, get_vietnamese_characters
from model_architecture import NemotronOCRRecognizer
from dataset_generator import SyntheticVietnameseOCRDataset, ocr_collate_fn

def greedy_ctc_decode(log_probs: torch.Tensor, idx2char: dict, blank_idx: int = 0) -> list:
    """
    Giải mã nhanh Greedy CTC từ log_probs (T, B, V).
    Loại bỏ các token liên tiếp trùng nhau và blank token.
    """
    preds = log_probs.argmax(dim=-1).permute(1, 0)  # (B, T)
    decoded_strings = []

    for sequence in preds:
        prev_idx = None
        chars = []
        for idx in sequence.tolist():
            if idx != prev_idx and idx != blank_idx:
                chars.append(idx2char.get(idx, ''))
            prev_idx = idx
        decoded_strings.append("".join(chars))

    return decoded_strings

def train(
    epochs: int = 5,
    batch_size: int = 16,
    lr: float = 1e-4,
    samples_per_epoch: int = 1000,
    checkpoint_dir: str = "deploy/ai-platform/01-nvidia-framework/ocr-finetune/checkpoints"
):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[*] Thiết bị huấn luyện: {device} (CUDA Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None'})")

    # 1. Chuẩn bị bảng ký tự tiếng Việt mở rộng
    charset_path = os.path.join(checkpoint_dir, "charset_vi.txt")
    dummy_orig = os.path.join(checkpoint_dir, "charset_base_sample.txt")
    
    # Tạo danh sách token cơ bản nếu chưa có
    base_chars = [chr(i) for i in range(32, 127)]  # ASCII in được
    os.makedirs(checkpoint_dir, exist_ok=True)
    with open(dummy_orig, "w", encoding="utf-8") as f:
        f.write("<blank>\n<unk>\n")
        for c in base_chars:
            f.write(f"{c}\n")

    num_old, num_new, added = expand_charset_file(dummy_orig, charset_path)
    print(f"[*] Đã nạp từ điển: {num_old} token gốc -> {num_new} token (+{len(added)} ký tự tiếng Việt có dấu).")

    # Tạo map index <-> char
    with open(charset_path, "r", encoding="utf-8") as f:
        tokens = [line.rstrip("\r\n") for line in f]
    char2idx = {t: i for i, t in enumerate(tokens)}
    idx2char = {i: t for i, t in enumerate(tokens)}

    # 2. Khởi tạo mô hình & Thiết lập Freeze tham số
    model = NemotronOCRRecognizer(vocab_size=num_old).to(device)
    model.freeze_cnn_encoder()
    model.unfreeze_decoder_and_head()
    model.expand_vocab(num_new)
    model = model.to(device)

    stats = model.count_parameters()
    print(f"[*] Cấu hình Tham số: Tổng: {stats['total']:,} | Trainable: {stats['trainable']:,} ({stats['trainable_percent']}%) | Frozen: {stats['frozen']:,}")

    # 3. Chuẩn bị Dataloader
    dataset = SyntheticVietnameseOCRDataset(
        char2idx=char2idx,
        num_samples=samples_per_epoch,
        img_height=32,
        max_width=512
    )
    dataloader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=ocr_collate_fn,
        num_workers=0,
        pin_memory=True if device.type == "cuda" else False
    )

    # 4. Thiết lập Optimizer, Loss & Scheduler
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=lr, weight_decay=1e-2)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CTCLoss(blank=0, zero_infinity=True)
    scaler = torch.amp.GradScaler('cuda', enabled=(device.type == "cuda"))

    # 5. Huấn luyện vòng lặp
    best_loss = float("inf")
    print(f"\n[+] Bắt đầu quá trình Fine-tuning ({epochs} Epochs, {len(dataloader)} Steps/Epoch):")
    print("=" * 75)

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        start_time = time.time()

        for step, (images, targets, input_lengths, target_lengths) in enumerate(dataloader, 1):
            images = images.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)
            input_lengths = input_lengths.to(device, non_blocking=True)
            target_lengths = target_lengths.to(device, non_blocking=True)

            optimizer.zero_grad()

            with torch.amp.autocast('cuda', enabled=(device.type == "cuda")):
                log_probs = model(images)  # (T, B, V)
                loss = criterion(log_probs, targets, input_lengths, target_lengths)

            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(trainable_params, max_norm=5.0)
            scaler.step(optimizer)
            scaler.update()

            total_loss += loss.item()

            if step % max(1, len(dataloader) // 5) == 0 or step == len(dataloader):
                print(f"Epoch [{epoch}/{epochs}] - Step [{step}/{len(dataloader)}] - Loss: {loss.item():.4f}")

        avg_loss = total_loss / len(dataloader)
        scheduler.step()
        elapsed = time.time() - start_time

        # Kiểm tra đọc thử nghiệm trực tiếp 1 batch mẫu
        model.eval()
        with torch.no_grad():
            sample_img, sample_target, s_in_len, s_tgt_len = dataset[0]
            sample_batch = sample_img.unsqueeze(0).to(device)
            sample_log_probs = model(sample_batch)
            pred_text = greedy_ctc_decode(sample_log_probs, idx2char)[0]
            print(f"[*] Demo suy luận Epoch {epoch}: Text dự đoán -> '{pred_text}'")

        print(f"--- Kết thúc Epoch {epoch}: Avg Loss = {avg_loss:.4f} | Thời gian: {elapsed:.2f}s ---")

        # Lưu Checkpoint tốt nhất
        if avg_loss < best_loss:
            best_loss = avg_loss
            ckpt_path = os.path.join(checkpoint_dir, "best_nemotron_recognizer_vi.pt")
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "vocab_size": num_new,
                "loss": best_loss
            }, ckpt_path)
            print(f"[✓] Đã lưu Checkpoint xuất sắc nhất tại: {ckpt_path}")

    print("\n" + "=" * 75)
    print(f"[🎉] Hoàn tất quá trình Fine-tuning! Model Tiếng Việt sẵn sàng sử dụng tại: {checkpoint_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-tune Nemotron Recognizer for Vietnamese")
    parser.add_argument("--epochs", type=int, default=3, help="Số lượng epoch huấn luyện")
    parser.add_argument("--batch-size", type=int, default=16, help="Kích thước batch")
    parser.add_argument("--lr", type=float, default=1e-4, help="Tốc độ học (Learning rate)")
    parser.add_argument("--samples", type=int, default=300, help="Số lượng mẫu ảnh sinh mỗi epoch")
    args = parser.parse_args()

    train(
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        samples_per_epoch=args.samples
    )
