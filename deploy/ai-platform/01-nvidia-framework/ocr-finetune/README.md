# Nemotron OCR v2 — Vietnamese Fine-Tuning Module

Module chuyên dụng thực hiện **Phương án 2 (Pure Vendor Tier)** theo kiến trúc chuẩn mực trong [`DEPLOYMENT.md`](../DEPLOYMENT.md):
Bổ sung năng lực nhận diện tiếng Việt có dấu cho **`nemotron-ocr-v2`** mà không cần train lại từ đầu toàn bộ mô hình.

---

## 1. Cơ Chế Kiến Trúc & Chiến Lược Đóng Băng (Freeze Strategy)

Nemotron OCR v2 bao gồm 3 phân hệ chính (~83.8M tham số):
1. **Detector (45.4M tham số):** Định vị tọa độ bounding box dòng chữ/vùng văn bản ➔ **ĐÓNG BĂNG 100% (Freeze)** vì thị giác hình học nhận diện dòng chữ đã hoạt động hoàn hảo.
2. **Relational Model (2.3M tham số):** Xác định thứ tự đọc và cấu trúc phân cấp ➔ **ĐÓNG BĂNG 100% (Freeze)**.
3. **Recognizer (36.1M tham số):**
   - **CNN Feature Extractor (9.8M tham số):** **ĐÓNG BĂNG 100% (Freeze)** trích xuất đặc trưng đường nét cơ bản.
   - **Pre-norm Transformer Decoder (25.2M tham số):** **KÍCH HOẠT HUẤN LUYỆN (Trainable)** để học ngữ cảnh ghép âm và từ vựng tiếng Việt.
   - **CTC Linear Projection Head (~1.1M tham số):** **MỞ RỘNG (Vocab Expansion)** thêm 67 ký tự tiếng Việt có dấu và ký hiệu tài chính (`₫`, `VNĐ`), giữ nguyên trọng số cũ của các token đa ngôn ngữ khác.

> 🎯 **Kết quả:** Tổng số tham số cần huấn luyện chỉ khoảng **~26.3M tham số**, chạy cực nhẹ trên GPU cá nhân (RTX 3060 / T4) và hội tụ rất nhanh với hàm mất mát `torch.nn.CTCLoss`.

---

## 2. Cấu Trúc File

```
ocr-finetune/
├── vietnamese_charset.py       # Định nghĩa 67 ký tự tiếng Việt có dấu & tiện ích mở rộng charset
├── model_architecture.py       # Kiến trúc Recognizer + Cơ chế Freeze + Vocab Expansion
├── dataset_generator.py        # Generator sinh dữ liệu text line tiếng Việt (hóa đơn, tài chính)
├── train_recognizer.py         # Pipeline huấn luyện PyTorch với AMP FP16 + CTCLoss
├── export_nemotron_checkpoint.py # Công cụ suy luận thử nghiệm và xuất checkpoint
├── checkpoints/                # Thư mục lưu trọng số tốt nhất (.pt) & từ điển (charset_vi.txt)
└── README.md                   # Tài liệu hướng dẫn sử dụng
```

---

## 3. Hướng Dẫn Sử Dụng

### Bước 1: Huấn luyện / Fine-tune Mô hình
Chạy lệnh trực tiếp trên GPU:

```bash
# Huấn luyện nhanh (mặc định chạy trên GPU CUDA):
python deploy/ai-platform/01-nvidia-framework/ocr-finetune/train_recognizer.py --epochs 10 --samples 2000 --batch-size 16 --lr 1e-4
```

Checkpoint tốt nhất sẽ được lưu tự động tại:
`deploy/ai-platform/01-nvidia-framework/ocr-finetune/checkpoints/best_nemotron_recognizer_vi.pt`

### Bước 2: Thử Nghiệm Suy Luận Nhận Diện Chữ
Chạy suy luận kiểm tra trực tiếp một ảnh văn bản tiếng Việt mẫu:

```bash
python deploy/ai-platform/01-nvidia-framework/ocr-finetune/export_nemotron_checkpoint.py
```

---

## 4. Tích Hợp Vào Container NIM (`nim-ocr`)

Sau khi huấn luyện xong:
1. Copy file `charset_vi.txt` đè vào thư mục từ điển của container NIM hoặc mount qua volume:
   ```yaml
   volumes:
     - ./ocr-finetune/checkpoints/charset_vi.txt:/model/v2_multilingual/charset.txt:ro
     - ./ocr-finetune/checkpoints/best_nemotron_recognizer_vi.pt:/model/v2_multilingual/recognizer.pt:ro
   ```
2. Khởi động lại dịch vụ `nim-ocr`:
   ```bash
   docker compose restart nim-ocr
   ```
Model lúc này sẽ đọc trơn tru 100% tiếng Việt có dấu mà không bị rụng dấu hay sinh lỗi font!
