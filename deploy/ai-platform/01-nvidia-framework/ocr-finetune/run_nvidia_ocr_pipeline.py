"""
run_nvidia_ocr_pipeline.py
Quy trình End-to-End OCR chuẩn NVIDIA Framework cho tài liệu & hóa đơn:
1. NVIDIA Nemotron Page Elements v3 (YOLOX) -> Phát hiện cấu trúc trang (Table, Title, Text, Header/Footer)
2. NVIDIA Nemotron Table Structure v1 (YOLOX) -> Bóc tách cấu trúc bảng biểu (Rows, Columns, Cells)
3. Fine-tuned Nemotron OCR Recognizer (Huấn luyện trên ademax/ocr_scan_vi_01) -> Nhận diện text tiếng Việt chuẩn xác
4. Xuất kết quả có cấu trúc: JSON, Markdown và ảnh trực quan Bounding Box
"""

import os
import sys
import json
import torch
import numpy as np
from PIL import Image, ImageDraw

# Thư mục cache mô hình NVIDIA trên máy
PAGE_MODEL_DIR = r"C:\Users\CongAnh\.cache\huggingface\hub\models--nvidia--nemotron-page-elements-v3\snapshots\df62dbb631502575ac4d43b44d700b1674ab1d56"
TABLE_MODEL_DIR = r"C:\Users\CongAnh\.cache\huggingface\hub\models--nvidia--nemotron-table-structure-v1\snapshots\9350162faa1110320af62699105780b0c87b73ad"

# Checkpoint Recognizer tiếng Việt huấn luyện trên dữ liệu Scan thực tế (ademax/ocr_scan_vi_01)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

CKPT_PATH = os.path.join(BASE_DIR, "checkpoints", "best_nemotron_recognizer_vi_scan.pt")
CHARSET_PATH = os.path.join(BASE_DIR, "checkpoints", "charset_vi.txt")

from model_architecture import NemotronOCRRecognizer

def decode_ctc(log_probs: torch.Tensor, idx2char: dict, blank_idx: int = 0) -> str:
    """Greedy CTC Decoder cho nhận diện text tiếng Việt."""
    preds = log_probs.argmax(dim=-1).permute(1, 0)[0]  # (T,)
    prev = None
    chars = []
    for idx in preds.tolist():
        if idx != prev and idx != blank_idx:
            chars.append(idx2char.get(idx, ''))
        prev = idx
    return "".join(chars)

def split_into_lines(crop_pil: Image.Image, min_line_h: int = 12):
    """Tách khối văn bản nhiều dòng thành các dòng đơn lẻ dựa trên projection profile."""
    if crop_pil.height <= 32:
        return [crop_pil]
    
    gray = np.array(crop_pil.convert('L'))
    bin_img = (gray < 220).astype(np.float32)
    proj = bin_img.sum(axis=1)

    lines = []
    in_line = False
    start_y = 0
    for y, val in enumerate(proj):
        if val > 1 and not in_line:
            in_line = True
            start_y = max(0, y - 2)
        elif val <= 1 and in_line:
            in_line = False
            end_y = min(len(proj), y + 2)
            if end_y - start_y >= min_line_h:
                lines.append((start_y, end_y))

    if in_line:
        lines.append((start_y, len(proj)))

    if not lines:
        return [crop_pil]
    return [crop_pil.crop((0, y1, crop_pil.width, y2)) for y1, y2 in lines]

def recognize_single_line(crop_img: Image.Image, recognizer_model, idx2char: dict, device: torch.device, target_height: int = 32, is_cell: bool = False) -> str:
    """Đưa 1 dòng văn bản qua Recognizer tiếng Việt để đọc nội dung."""
    w, h = crop_img.size
    if w < 6 or h < 6:
        return ""

    if is_cell and w > 10 and h > 10:
        crop_img = crop_img.crop((2, 2, w - 2, h - 2))
        w, h = crop_img.size

    img_np = np.array(crop_img, dtype=np.float32)
    if img_np.std() < 18.0 and img_np.mean() > 240.0:
        return ""

    aspect = w / max(h, 1)
    target_w = min(int(target_height * aspect), 512)
    target_w = max((target_w // 4) * 4, 16)
    resized = crop_img.resize((target_w, target_height), Image.Resampling.BILINEAR)
    arr = (np.array(resized, dtype=np.float32) / 255.0 - 0.5) / 0.5
    
    if len(arr.shape) == 2:
        arr = np.stack([arr] * 3, axis=-1)
    elif arr.shape[2] == 4:
        arr = arr[:, :, :3]

    img_tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(device)

    with torch.inference_mode():
        log_probs = recognizer_model(img_tensor)
        text = decode_ctc(log_probs, idx2char)
    return text.strip()

def recognize_text(crop_img: Image.Image, recognizer_model, idx2char: dict, device: torch.device, target_height: int = 32, is_cell: bool = False) -> str:
    """Nhận diện text cho block văn bản (hỗ trợ tách nhiều dòng)."""
    if is_cell or crop_img.height <= 32:
        return recognize_single_line(crop_img, recognizer_model, idx2char, device, target_height, is_cell=is_cell)
    
    lines = split_into_lines(crop_img)
    texts = []
    for line in lines:
        t = recognize_single_line(line, recognizer_model, idx2char, device, target_height, is_cell=False)
        if t:
            texts.append(t)
    return " \n ".join(texts)

def run_nvidia_pipeline(image_path: str, output_dir: str):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[*] Khởi động NVIDIA Pipeline trên thiết bị: {device} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")
    os.makedirs(output_dir, exist_ok=True)

    # 1. Nạp ảnh gốc
    img_pil = Image.open(image_path).convert("RGB")
    W, H = img_pil.size
    img_np = np.array(img_pil)
    print(f"[*] Ảnh đầu vào: {image_path} (Kích thước: {W}x{H})")

    # 2. Nạp Model 1: Nemotron Page Elements v3
    print("\n" + "="*50)
    print("[1/3] Nạp mô hình NVIDIA Nemotron Page Elements v3 (YOLOX)...")
    if PAGE_MODEL_DIR not in sys.path:
        sys.path.insert(0, PAGE_MODEL_DIR)

    cur_dir = os.getcwd()
    os.chdir(PAGE_MODEL_DIR)
    from nemotron_page_elements_v3.model import define_model as define_page_model
    from nemotron_page_elements_v3.utils import postprocess_preds_page_element
    from nemotron_page_elements_v3.post_processing.wbf import weighted_boxes_fusion

    page_model = define_page_model("page_element_v3")
    os.chdir(cur_dir)

    with torch.inference_mode():
        x = page_model.preprocess(img_np)
        preds = page_model(x, img_np.shape)[0]

    p_boxes, p_labels, p_scores = postprocess_preds_page_element(
        preds, page_model.thresholds_per_class, page_model.labels
    )
    if len(p_boxes) > 0:
        for _ in range(2):
            p_boxes, p_labels, p_scores = weighted_boxes_fusion(
                p_boxes[:, None],
                p_labels[:, None],
                p_scores[:, None],
                merge_type="biggest",
                conf_type="max",
                iou_thr=0.01,
            )
    print(f"[*] Page Elements v3 phát hiện {len(p_boxes)} đối tượng trang.")

    # 3. Nạp Model 2: Nemotron Table Structure v1
    print("\n" + "="*50)
    print("[2/3] Nạp mô hình NVIDIA Nemotron Table Structure v1 (YOLOX)...")
    if TABLE_MODEL_DIR not in sys.path:
        sys.path.insert(0, TABLE_MODEL_DIR)

    os.chdir(TABLE_MODEL_DIR)
    from nemotron_table_structure_v1.model import define_model as define_table_model
    from nemotron_table_structure_v1.utils import postprocess_preds_table_structure
    from nemotron_table_structure_v1.post_processing.wbf import weighted_boxes_fusion as wbf_table
    from nemotron_table_structure_v1.utils import reorder_boxes

    table_model = define_table_model("table_structure_v1")
    os.chdir(cur_dir)

    # 4. Nạp Model 3: Fine-tuned Nemotron Recognizer tiếng Việt (ademax/ocr_scan_vi_01)
    print("\n" + "="*50)
    print("[3/3] Nạp Fine-tuned Nemotron OCR Recognizer (Đã train trên ademax/ocr_scan_vi_01)...")
    with open(CHARSET_PATH, "r", encoding="utf-8") as f:
        tokens = [line.rstrip("\r\n") for line in f]
    idx2char = {i: t for i, t in enumerate(tokens)}
    ckpt = torch.load(CKPT_PATH, map_location=device, weights_only=False)
    vocab_size = ckpt.get("vocab_size", len(tokens))
    recognizer = NemotronOCRRecognizer(vocab_size=vocab_size).to(device)
    recognizer.load_state_dict(ckpt["model_state_dict"])
    recognizer.eval()
    print(f"[*] Recognizer nạp từ: {CKPT_PATH} (Epoch {ckpt.get('epoch')}, Val Loss: {ckpt.get('val_loss', 0):.4f})")

    # Tạo canvas vẽ trực quan
    viz_img = img_pil.copy()
    draw = ImageDraw.Draw(viz_img)

    results = {
        "page_elements": [],
        "tables": []
    }

    # Bóc tách và chạy inference
    table_index = 0
    for idx, (b, lbl, score) in enumerate(zip(p_boxes, p_labels, p_scores)):
        cls_name = page_model.labels[int(lbl)]
        x1, y1, x2, y2 = int(b[0] * W), int(b[1] * H), int(b[2] * W), int(b[3] * H)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(W, x2), min(H, y2)

        if cls_name == "table":
            table_index += 1
            print(f"\n[+] Phân tích Bảng {table_index} tọa độ: [{x1}, {y1}, {x2}, {y2}] (Score: {score:.2f})")
            draw.rectangle([x1, y1, x2, y2], outline="red", width=3)

            table_crop = img_pil.crop((x1, y1, x2, y2))
            t_w, t_h = table_crop.size
            table_np = np.array(table_crop)

            with torch.inference_mode():
                tx = table_model.preprocess(table_np)
                tpreds = table_model(tx, table_np.shape)[0]

            t_boxes, t_labels, t_scores = postprocess_preds_table_structure(
                tpreds, table_model.threshold, table_model.labels
            )
            if len(t_boxes) > 0:
                for _ in range(2):
                    t_boxes, t_labels, t_scores = wbf_table(
                        t_boxes[:, None],
                        t_labels[:, None],
                        t_scores[:, None],
                        merge_type="biggest",
                        conf_type="max",
                        iou_thr=0.1,
                    )
                t_boxes, t_labels, t_scores = reorder_boxes(t_boxes, t_labels, table_model.labels, t_scores)

            cells = []
            rows = []
            cols = []

            for tb, tl, ts in zip(t_boxes, t_labels, t_scores):
                tcls = table_model.labels[int(tl)]
                bx1, by1, bx2, by2 = int(tb[0] * t_w), int(tb[1] * t_h), int(tb[2] * t_w), int(tb[3] * t_h)
                abs_box = [x1 + bx1, y1 + by1, x1 + bx2, y1 + by2]

                if tcls == "cell":
                    cell_crop = table_crop.crop((bx1, by1, bx2, by2))
                    text = recognize_text(cell_crop, recognizer, idx2char, device, is_cell=True)
                    cells.append({
                        "box_rel": [bx1, by1, bx2, by2],
                        "box_abs": abs_box,
                        "text": text,
                        "score": float(ts)
                    })
                    draw.rectangle(abs_box, outline="#00e5ff", width=1)
                elif tcls == "row":
                    rows.append({"box_rel": [bx1, by1, bx2, by2], "box_abs": abs_box})
                elif tcls == "column":
                    cols.append({"box_rel": [bx1, by1, bx2, by2], "box_abs": abs_box})

            cells_sorted = sorted(cells, key=lambda c: (round(c['box_abs'][1] / 18) * 18, c['box_abs'][0]))
            print(f"    -> Đã bóc tách {len(cells)} cells, {len(rows)} rows, {len(cols)} columns")
            results["tables"].append({
                "table_id": table_index,
                "box": [x1, y1, x2, y2],
                "score": float(score),
                "cells_count": len(cells),
                "cells": cells_sorted
            })
        else:
            crop_elt = img_pil.crop((x1, y1, x2, y2))
            text = recognize_text(crop_elt, recognizer, idx2char, device, is_cell=False)
            color = "#ff9100" if cls_name == "title" else "#00e676"
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
            results["page_elements"].append({
                "class": cls_name,
                "box": [x1, y1, x2, y2],
                "score": float(score),
                "text": text
            })
            print(f"[+] [{cls_name.upper():6s}] ({score:.2f}) -> {text}")

    # Lưu ảnh trực quan
    viz_path = os.path.join(output_dir, "nvidia_yolo_ocr_visualized.png")
    viz_img.save(viz_path)
    print(f"\n[*] Đã lưu ảnh trực quan hóa: {viz_path}")

    # Lưu JSON
    json_path = os.path.join(output_dir, "nvidia_yolo_ocr_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Lưu Markdown
    md_path = os.path.join(output_dir, "nvidia_yolo_ocr_table.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# KẾT QUẢ FULL OCR NVIDIA (YOLOX + NEMOTRON RECOGNIZER SCAN VI)\n\n")
        f.write("## 1. Các thành phần trang (Page Elements v3)\n")
        for elt in sorted(results["page_elements"], key=lambda e: e["box"][1]):
            f.write(f"- **[{elt['class'].upper()}]** ({elt['score']:.2f}): `{elt['text']}`\n")

        f.write("\n## 2. Bóc tách bảng biểu (Table Structure v1)\n")
        for t in results["tables"]:
            f.write(f"### Bảng #{t['table_id']} (Độ tin cậy: {t['score']:.2f})\n")
            f.write(f"- Tổng số Cells: {t['cells_count']}\n\n")
            f.write("| STT | Tọa độ Box | Nội dung nhận diện |\n")
            f.write("|---|---|---|\n")
            for ci, c in enumerate(t["cells"]):
                f.write(f"| {ci+1} | `{c['box_abs']}` | **{c['text']}** |\n")

    print(f"[*] Đã lưu báo cáo Markdown: {md_path}")
    return results

if __name__ == "__main__":
    img_path = r"C:\Users\CongAnh\.gemini\antigravity\brain\04a2b0da-0a12-469a-8a03-b42a468b993c\.user_uploaded\media_1794499827361_8c0edca0.jpg"
    out_dir = r"c:\Users\CongAnh\Desktop\Yggdrasil\deploy\ai-platform\01-nvidia-framework\ocr-finetune\outputs"
    run_nvidia_pipeline(img_path, out_dir)
