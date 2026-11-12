"""
finetune_invoice_clean.py
Fine-tune bổ sung cho Nemotron OCR Recognizer:
- Khởi tạo từ checkpoint đã học ademax (best_nemotron_recognizer_vi_scan.pt)
- Trộn tập dữ liệu scan ademax với các mẫu chữ số hóa đơn, số tiền, mã số thuế, ký hiệu hóa đơn
- Giúp model nhận diện cực kỳ sạch sẽ và chuẩn xác cả chữ số in kim lẫn văn bản tiếng Việt
"""

import os
import io
import time
import random
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
import pyarrow.parquet as pq

from model_architecture import NemotronOCRRecognizer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "ademax", "data")
TRAIN_PARQUET = os.path.join(DATA_DIR, "train-00000-of-00001-2f5fcc01788814cd.parquet")
CHECKPOINT_DIR = os.path.join(BASE_DIR, "checkpoints")
CHARSET_PATH = os.path.join(CHECKPOINT_DIR, "charset_vi.txt")
SRC_CKPT = os.path.join(CHECKPOINT_DIR, "best_nemotron_recognizer_vi_scan.pt")
OUT_CKPT = os.path.join(CHECKPOINT_DIR, "best_nemotron_recognizer_vi_clean.pt")

# Các mẫu số tiền, mã số thuế, tiêu đề hóa đơn để bổ sung trọng số chữ số
INVOICE_SYNTH_TEMPLATES = [
    "3.500.000", "7.000.000", "2.000.000", "9.000.000", "01", "02", "1", "2", "3", "4", "5", "6",
    "Khóa học thực hành kế toán tổng hợp", "Dịch vụ kế toán thuế quý 3/2023", "Khóa", "Quý",
    "CÔNG TY KẾ TOÁN THIÊN ƯNG", "CÔNG TY CỔ PHẦN KIẾN TRÚC VÀ XÂY DỰNG IGS",
    "0110329220", "0110329573", "00B6C354D9CCF448A3B1A58180C35B6737",
    "HÓA ĐƠN BÁN HÀNG", "SALES INVOICE", "2C23TTU", "00002438", "Chín triệu đồng./.",
    "Số 9A, ngõ 181 đường Xuân Thủy, Phường Dịch Vọng Hậu, Quận Cầu Giấy, Thành phố Hà Nội",
    "Số 10, xóm Giữa, thôn Đông Lai, Xã Liên Hồng, Huyện Đan Phượng, Thành phố Hà Nội",
    "Nguyễn Thị Mai", "Người mua hàng (Buyer)", "Người bán hàng (Seller)",
    "Tổng cộng tiền thanh toán (Total payment):", "Số tiền viết bằng chữ (Amount in words):",
    "15.000.000", "25.500.000", "1.200.000", "500.000", "10.000.000", "100.000",
    "ĐVT (Unit)", "SL (Quantity)", "Đơn giá (Unit Price)", "Thành tiền (Amount)",
    "Tên hàng hóa, dịch vụ (Description)", "Mã của Cơ quan thuế:", "MST (Tax Code):"
]

def render_synthetic_line(text: str, target_h: int = 32) -> Image.Image:
    """Render dòng chữ với font chữ đa dạng và thêm noise nhẹ."""
    font_size = random.randint(18, 22)
    font = None
    for fn in ["arial.ttf", "times.ttf", "calibri.ttf", "segoeui.ttf"]:
        try:
            font = ImageFont.truetype(fn, font_size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    dummy = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(dummy)
    bbox = d.textbbox((0, 0), text, font=font)
    tw = max(bbox[2] - bbox[0] + 16, 32)
    th = max(bbox[3] - bbox[1] + 8, target_h)

    # Nền trắng ngà hoặc xám nhẹ
    bg = (random.randint(240, 255), random.randint(240, 255), random.randint(240, 255))
    img = Image.new("RGB", (tw, th), color=bg)
    draw = ImageDraw.Draw(img)

    # Nét chữ đen hoặc xanh đậm
    fg = (random.randint(0, 40), random.randint(0, 40), random.randint(0, 60))
    draw.text((8, (th - (bbox[3] - bbox[1])) // 2), text, font=font, fill=fg)

    # Thỉnh thoảng thêm vạch mờ như watermark
    if random.random() < 0.3:
        draw.line([(0, random.randint(0, th)), (tw, random.randint(0, th))], fill=(210, 220, 230), width=1)

    # Resize về target_h
    aspect = tw / max(th, 1)
    new_w = max((int(target_h * aspect) // 4) * 4, 16)
    return img.resize((new_w, target_h), Image.Resampling.BILINEAR)

class CombinedCleanDataset(Dataset):
    """Kết hợp giữa ảnh scan ademax và các mẫu hóa đơn/số tiền tăng cường."""
    def __init__(self, parquet_path: str, char2idx: dict, synth_count: int = 3000):
        self.table = pq.read_table(parquet_path)
        self.char2idx = char2idx
        self.synth_count = synth_count
        self.total_len = len(self.table) + synth_count

    def __len__(self):
        return self.total_len

    def __getitem__(self, idx: int):
        if idx < len(self.table):
            row = self.table.slice(idx, 1)
            img_bytes = row["image"][0].as_py()["bytes"]
            text = row["text"][0].as_py() or ""
            try:
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            except Exception:
                img = Image.new("RGB", (64, 32), (255, 255, 255))
            w, h = img.size
            aspect = w / max(h, 1)
            new_w = min(int(32 * aspect), 512)
            new_w = max((new_w // 4) * 4, 16)
            img = img.resize((new_w, 32), Image.Resampling.BILINEAR)
        else:
            # Mẫu synthetic số tiền hóa đơn
            text = random.choice(INVOICE_SYNTH_TEMPLATES)
            if random.random() < 0.4:
                # Sinh số tiền ngẫu nhiên
                amount = f"{random.randint(100, 9999) * 1000:,}".replace(",", ".")
                text = f"{amount}"
            img = render_synthetic_line(text, target_h=32)

        arr = (np.array(img, dtype=np.float32) / 255.0 - 0.5) / 0.5
        tensor = torch.from_numpy(arr).permute(2, 0, 1)

        target = [self.char2idx.get(c, self.char2idx.get(" ", 1)) for c in text]
        target_tensor = torch.tensor(target, dtype=torch.long)
        return tensor, target_tensor, img.width, len(target)

def clean_collate_fn(batch):
    images, targets, widths, target_lengths = zip(*batch)
    max_w = ((max(widths) + 3) // 4) * 4
    batch_size = len(images)
    padded_images = torch.full((batch_size, 3, 32, max_w), 1.0, dtype=torch.float32)

    for i, img in enumerate(images):
        w = img.shape[2]
        padded_images[i, :, :, :w] = img

    input_lengths = torch.tensor([w // 4 for w in widths], dtype=torch.long)
    target_lengths = torch.tensor(target_lengths, dtype=torch.long)
    all_targets = torch.cat(targets, dim=0)
    return padded_images, all_targets, input_lengths, target_lengths

def train_clean(epochs: int = 4, batch_size: int = 32, lr: float = 1.5e-4):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[*] Huấn luyện tinh chỉnh độ sạch trên: {device} ({torch.cuda.get_device_name(0)})")

    with open(CHARSET_PATH, "r", encoding="utf-8") as f:
        tokens = [l.strip("\r\n") for l in f if l.strip("\r\n")]
    char2idx = {t: i for i, t in enumerate(tokens)}
    idx2char = {i: t for i, t in enumerate(tokens)}
    vocab_size = len(tokens)

    # Nạp checkpoint đã học scan ademax
    ckpt = torch.load(SRC_CKPT, map_location=device, weights_only=False)
    model = NemotronOCRRecognizer(vocab_size=vocab_size, d_model=512).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    print(f"[*] Đã nạp nền tảng từ: {SRC_CKPT} (Epoch {ckpt.get('epoch')}, Loss {ckpt.get('val_loss', 0):.4f})")

    dataset = CombinedCleanDataset(TRAIN_PARQUET, char2idx, synth_count=4000)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, collate_fn=clean_collate_fn, num_workers=0)
    print(f"[*] Tổng mẫu huấn luyện kết hợp: {len(dataset):,} ({len(loader)} batches/epoch)")

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs * len(loader), eta_min=1e-5)
    criterion = nn.CTCLoss(blank=0, zero_infinity=True)
    scaler = torch.amp.GradScaler("cuda")

    for epoch in range(1, epochs + 1):
        model.train()
        start_t = time.time()
        running_loss = 0.0
        steps = 0

        for b_idx, (imgs, targets, in_lens, tgt_lens) in enumerate(loader):
            imgs = imgs.to(device)
            targets = targets.to(device)
            in_lens = in_lens.to(device)
            tgt_lens = tgt_lens.to(device)

            optimizer.zero_grad()
            with torch.amp.autocast("cuda"):
                log_probs = model(imgs)
                loss = criterion(log_probs, targets, in_lens, tgt_lens)

            if torch.isnan(loss) or torch.isinf(loss):
                continue

            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()

            running_loss += loss.item()
            steps += 1

            if (b_idx + 1) % 100 == 0 or (b_idx + 1) == len(loader):
                print(f"Epoch [{epoch}/{epochs}] Batch [{b_idx+1}/{len(loader)}] | Loss: {running_loss/steps:.4f} | Time: {time.time()-start_t:.1f}s")

    # Lưu checkpoint sạch
    torch.save({
        "epoch": 10,
        "model_state_dict": model.state_dict(),
        "vocab_size": vocab_size,
        "val_loss": running_loss / max(steps, 1)
    }, OUT_CKPT)
    print(f"\n[★] ĐÃ HOÀN TẤT VÀ LƯU CHECKPOINT SẠCH: {OUT_CKPT}")

if __name__ == "__main__":
    train_clean(epochs=3, batch_size=32, lr=1.5e-4)
