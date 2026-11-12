"""
full_pipeline_test.py
Pipeline Full OCR Nemotron theo kiến trúc NVIDIA:
1. Text Region & Line Detector (Trích xuất các dòng văn bản theo thứ tự đọc)
2. Fine-tuned Nemotron OCR Recognizer (Đọc chữ tiếng Việt có dấu với GPU RTX 3060)
3. Xuất kết quả bóc tách văn bản có cấu trúc và ảnh khoanh vùng trực quan
"""

import os
import cv2
import numpy as np
import torch
from PIL import Image

from vietnamese_charset import get_vietnamese_characters
from model_architecture import NemotronOCRRecognizer

def decode_prediction(log_probs: torch.Tensor, idx2char: dict, blank_idx: int = 0) -> str:
    preds = log_probs.argmax(dim=-1).permute(1, 0)[0]
    prev = None
    chars = []
    for idx in preds.tolist():
        if idx != prev and idx != blank_idx:
            chars.append(idx2char.get(idx, ''))
        prev = idx
    return "".join(chars)

def filter_nested_boxes(boxes):
    """Loại bỏ các box con bị lồng hoàn toàn bên trong box lớn hơn."""
    boxes = sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)
    kept = []
    for x, y, w, h in boxes:
        is_inside = False
        for kx, ky, kw, kh in kept:
            # Nếu tâm của box nằm trong box đã giữ
            cx, cy = x + w / 2, y + h / 2
            if kx <= cx <= kx + kw and ky <= cy <= ky + kh:
                is_inside = True
                break
        if not is_inside:
            kept.append((x, y, w, h))
    return kept

def detect_text_lines(image_cv: np.ndarray):
    """
    Phát hiện các dòng văn bản (bounding boxes) trên hóa đơn:
    Dùng RETR_LIST để xuyên qua khung viền hoa văn lớn và lọc các dòng chữ.
    """
    gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
    h_img, w_img = gray.shape

    # Binarize
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8
    )

    # Nối các chữ trên cùng dòng ngang
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (18, 3))
    dilated = cv2.dilate(thresh, kernel, iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    raw_boxes = []

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # Bỏ khung viền toàn trang hoặc vạch kẻ bảng đơn lẻ
        if w > w_img * 0.90 or h > 55 or h < 9 or w < 20:
            continue
        # Bỏ các đường kẻ ngang bảng biểu siêu mỏng
        if w > 300 and h < 12:
            continue
        raw_boxes.append((x, y, w, h))

    # Lọc bỏ box lồng nhau
    boxes = filter_nested_boxes(raw_boxes)

    # Sắp xếp các box theo thứ tự đọc: từ trên xuống dưới, từ trái sang phải
    boxes = sorted(boxes, key=lambda b: (round(b[1] / 15) * 15, b[0]))
    return boxes

def run_full_ocr(image_path: str, checkpoint_path: str, charset_path: str, output_dir: str):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[*] Thiết bị suy luận: {device} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")

    # 1. Nạp từ điển
    with open(charset_path, "r", encoding="utf-8") as f:
        tokens = [line.rstrip("\r\n") for line in f]
    char2idx = {t: i for i, t in enumerate(tokens)}
    idx2char = {i: t for i, t in enumerate(tokens)}

    # 2. Nạp Model đã fine-tune
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    vocab_size = ckpt.get("vocab_size", len(tokens))
    model = NemotronOCRRecognizer(vocab_size=vocab_size).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    print(f"[*] Đã nạp thành công Checkpoint Fine-tuned (Vocab: {vocab_size} tokens)")

    # 3. Đọc ảnh gốc
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")

    img_bgr = cv2.imread(image_path)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    annotated = img_bgr.copy()

    # 4. Dò tìm các dòng văn bản
    print("[*] Đang phân tích layout và phát hiện các dòng văn bản (Text Detection)...")
    boxes = detect_text_lines(img_bgr)
    print(f"[✓] Đã phát hiện {len(boxes)} dòng văn bản trên hóa đơn.")

    # 5. Nhận diện từng dòng qua Nemotron Recognizer
    print("\n" + "=" * 80)
    print("KẾT QUẢ BÓC TÁCH HÓA ĐƠN QUA NEMOTRON OCR TIẾNG VIỆT:")
    print("=" * 80)

    extracted_lines = []
    os.makedirs(output_dir, exist_ok=True)

    with torch.no_grad():
        for idx, (x, y, w, h) in enumerate(boxes, 1):
            pad_x = 3
            pad_y = 2
            x0 = max(0, x - pad_x)
            y0 = max(0, y - pad_y)
            x1 = min(img_rgb.shape[1], x + w + pad_x)
            y1 = min(img_rgb.shape[0], y + h + pad_y)

            crop = img_rgb[y0:y1, x0:x1]
            if crop.size == 0 or crop.shape[0] < 4 or crop.shape[1] < 4:
                continue

            crop_pil = Image.fromarray(crop)
            c_w, c_h = crop_pil.size
            target_w = min(int(32 * (c_w / c_h)), 512)
            crop_resized = crop_pil.resize((target_w, 32), Image.Resampling.BILINEAR)

            padded_crop = Image.new('RGB', (512, 32), color=(255, 255, 255))
            padded_crop.paste(crop_resized, (0, 0))

            tensor = torch.from_numpy(np.array(padded_crop, dtype=np.float32) / 255.0).permute(2, 0, 1).unsqueeze(0)
            tensor = ((tensor - 0.5) / 0.5).to(device)

            with torch.amp.autocast('cuda', enabled=(device.type == "cuda")):
                log_probs = model(tensor)
                line_text = decode_prediction(log_probs, idx2char)

            line_text = line_text.strip()
            if len(line_text) > 0:
                print(f"[{idx:02d}] (x={x:03d}, y={y:03d}, w={w:03d}, h={h:02d}) -> {line_text}")
                extracted_lines.append(f"[{idx:02d}] {line_text}")

                # Vẽ bounding box lên ảnh kết quả
                cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 180, 0), 1)
                cv2.putText(annotated, str(idx), (x, max(10, y - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)

    # Lưu ảnh kết quả annotated
    out_img_path = os.path.join(output_dir, "annotated_invoice_boxes.png")
    cv2.imwrite(out_img_path, annotated)
    print("=" * 80)
    print(f"[✓] Đã xuất ảnh khoanh vùng bounding boxes tại: {out_img_path}")

    # Lưu file text kết quả
    out_txt_path = os.path.join(output_dir, "extracted_invoice.txt")
    with open(out_txt_path, "w", encoding="utf-8") as f:
        for l in extracted_lines:
            f.write(l + "\n")
    print(f"[✓] Đã xuất toàn bộ nội dung bóc tách vào: {out_txt_path}")

if __name__ == "__main__":
    img_target = r"C:\Users\CongAnh\.gemini\antigravity\brain\04a2b0da-0a12-469a-8a03-b42a468b993c\.user_uploaded\media_1794499827361_8c0edca0.jpg"
    ckpt_target = "deploy/ai-platform/01-nvidia-framework/ocr-finetune/checkpoints/best_nemotron_recognizer_vi.pt"
    charset_target = "deploy/ai-platform/01-nvidia-framework/ocr-finetune/checkpoints/charset_vi.txt"
    out_dir = "deploy/ai-platform/01-nvidia-framework/ocr-finetune/test_results"

    run_full_ocr(img_target, ckpt_target, charset_target, out_dir)
