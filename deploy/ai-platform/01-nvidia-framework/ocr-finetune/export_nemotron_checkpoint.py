"""
export_nemotron_checkpoint.py
Công cụ suy luận thử nghiệm và xuất mô hình đã fine-tune sang TorchScript / Trọng số chuẩn:
- Tải checkpoint best_nemotron_recognizer_vi.pt
- Chạy inference nhận diện chữ tiếng Việt có dấu trên ảnh đầu vào
"""

import os
import argparse
import torch
from PIL import Image, ImageFont, ImageDraw
import numpy as np

from vietnamese_charset import get_vietnamese_characters
from model_architecture import NemotronOCRRecognizer

def decode_prediction(log_probs: torch.Tensor, idx2char: dict, blank_idx: int = 0) -> str:
    preds = log_probs.argmax(dim=-1).permute(1, 0)[0]  # (T)
    prev = None
    chars = []
    for idx in preds.tolist():
        if idx != prev and idx != blank_idx:
            chars.append(idx2char.get(idx, ''))
        prev = idx
    return "".join(chars)

def run_inference(image_path: str, checkpoint_path: str, charset_path: str):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 1. Load charset
    if not os.path.exists(charset_path):
        raise FileNotFoundError(f"Không tìm thấy file charset: {charset_path}")
    with open(charset_path, "r", encoding="utf-8") as f:
        tokens = [line.rstrip("\r\n") for line in f]
    char2idx = {t: i for i, t in enumerate(tokens)}
    idx2char = {i: t for i, t in enumerate(tokens)}

    # 2. Load model
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Không tìm thấy checkpoint: {checkpoint_path}")

    ckpt = torch.load(checkpoint_path, map_location=device)
    vocab_size = ckpt.get("vocab_size", len(tokens))
    model = NemotronOCRRecognizer(vocab_size=vocab_size).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    # 3. Chuẩn bị ảnh
    if not os.path.exists(image_path):
        # Tự tạo 1 ảnh test mẫu nếu không có sẵn
        img = Image.new('RGB', (350, 32), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        font = None
        for font_name in ["arial.ttf", "times.ttf"]:
            try:
                font = ImageFont.truetype(font_name, 20)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()
        draw.text((10, 4), "Doanh thu FUTA: 15.000.000 ₫", font=font, fill=(0, 0, 0))
        img.save(image_path)
        print(f"[*] Đã tạo ảnh test mẫu: {image_path}")
    else:
        img = Image.open(image_path).convert('RGB')

    # Resize về height 32
    w, h = img.size
    target_w = min(int(32 * (w / h)), 512)
    img_resized = img.resize((target_w, 32), Image.Resampling.BILINEAR)
    padded_img = Image.new('RGB', (512, 32), color=(255, 255, 255))
    padded_img.paste(img_resized, (0, 0))

    img_np = np.array(padded_img, dtype=np.float32) / 255.0
    img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0)
    img_tensor = ((img_tensor - 0.5) / 0.5).to(device)

    # 4. Suy luận
    with torch.no_grad():
        log_probs = model(img_tensor)
        text = decode_prediction(log_probs, idx2char)

    print(f"\n[✓] Kết quả OCR Nhận Diện: '{text}'")
    return text

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=str, default="deploy/ai-platform/01-nvidia-framework/ocr-finetune/checkpoints/sample_test.png")
    parser.add_argument("--ckpt", type=str, default="deploy/ai-platform/01-nvidia-framework/ocr-finetune/checkpoints/best_nemotron_recognizer_vi.pt")
    parser.add_argument("--charset", type=str, default="deploy/ai-platform/01-nvidia-framework/ocr-finetune/checkpoints/charset_vi.txt")
    args = parser.parse_args()

    run_inference(args.image, args.ckpt, args.charset)
