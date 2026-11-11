# Hướng Dẫn Triển Khai (`01-nvidia-framework`)

Tài liệu hướng dẫn khởi chạy nhanh cụm **NVIDIA Enterprise AI Platform** trên Yggdrasil theo 2 chế độ: **Chế độ Cloud API (Siêu nhẹ, không cần GPU)** và **Chế độ Hybrid Local Vision/OCR (Tự host cụm model Nemotron bóc tách bảng biểu & văn bản)**.

---

## 1. Cấu Trúc Port & Dịch Vụ

| Dịch vụ (Container) | Cổng (Host) | Vai trò | Chế độ chạy |
| :--- | :--- | :--- | :--- |
| **`auto-ontology-frontend`** | `:3000` | Giao diện Web UI quản trị Semantic Graph & Chat SQL | Mặc định |
| **`auto-ontology`** | `:3001` | FastAPI Backend sinh câu truy vấn SQL tất định | Mặc định |
| **`ingestion-service`** | `:3002` | Worker quét Schema & dữ liệu mẫu từ DB nguồn | Mặc định |
| **`auto-ontology-mcp`** | `:3003` | MCP Server cho phép Agent gọi NL-to-SQL (`http://localhost:3003/mcp`) | Mặc định |
| **`postgres`** | `:5432` | PostgreSQL 17 + `pgvector` lưu trữ Catalog & Ontology | Mặc định |
| **`retriever`** | `:7670` | NeMo-Retriever API & MCP Server (`http://localhost:7670/mcp`) | Mặc định |
| **`vectordb`** | `:7671` | LanceDB Vector Store lưu trữ tài liệu RAG | Mặc định |
| **`phoenix`** | `:6006` / `:4317` | Arize Phoenix UI (`:6006`) & OTLP Trace Collector (`:4317`) | Mặc định |
| **`nemoclaw`** | `:7681` | Autonomous Always-on Agent Worker (OpenShell Sandbox & OpenClaw Loop) | Mặc định |
| **`nim-page-elements`** | `:8001` | `nemotron-page-elements-v3` (kiến trúc YOLOX 54M ~200MB) phân vùng Layout trang PDF | `--profile local-vision` |
| **`nim-table-structure`** | `:8002` | `nemotron-table-structure-v1` (kiến trúc YOLOX 54M ~200MB) bổ dòng, cột & cell bảng biểu | `--profile local-vision` |
| **`nim-ocr`** | `:8003` | `nemotron-ocr-v2` (~300MB) đọc chữ đa ngôn ngữ trong cell | `--profile local-vision` |

---

## 2. Các Bước Triển Khai

### Bước 1: Tạo file `.env`
```bash
cd "ai platform/01-nvidia-framework"
cp .env.example .env
```

### Bước 2: Điền API Key vào `.env`

#### Phương án A — Chạy 100% qua API (Máy Dev không cần GPU)
Mở `.env` và cấu hình tầng LLM bằng bất kỳ nhà cung cấp OpenAI-compatible nào (DeepSeek, Gemini, OpenAI) kèm khóa `NVIDIA_API_KEY` cho tầng bóc tách tài liệu:
```dotenv
# 1. Tầng LLM Suy luận (DeepSeek / Gemini / OpenAI)
DEFAULT_MODELS_ENDPOINT=https://api.deepseek.com/v1
DEFAULT_MODELS_API_KEY=sk-xxxx
DEFAULT_MODELS_MODEL=deepseek-chat

# 2. Tầng Embedding & Multimodal OCR qua API
NVIDIA_API_KEY=nvapi-xxxx
EMBED_ENDPOINT=https://integrate.api.nvidia.com/v1
EMBED_API_KEY=nvapi-xxxx
EMBED_MODEL=nvidia/nemotron-3-embed-1b
```

Khởi động cụm dịch vụ:
```bash
docker compose up -d
```

---

#### Phương án B — Chế độ Hybrid (Tự host cụm Nemotron Vision + OCR ~700MB tại chỗ)
Nếu muốn tự host 3 model thị giác Nemotron (`nemotron-page-elements-v3`, `nemotron-table-structure-v1`, `nemotron-ocr-v2`) tại chỗ để bóc tách bảng biểu nội bộ không qua mạng ngoài:

1. Sửa 3 dòng Endpoint trong `.env` trỏ vào mạng nội bộ Docker:
```dotenv
NGC_API_KEY=nvapi-xxxx
NIM_PAGE_ELEMENTS_URL=http://nim-page-elements:8000/v1/infer
NIM_TABLE_STRUCTURE_URL=http://nim-table-structure:8000/v1/infer
NIM_OCR_URL=http://nim-ocr:8000/v1/infer
```

2. Khởi động kèm cờ `--profile local-vision`:
```bash
docker compose --profile local-vision up -d
```

---

## 3. Kiểm Tra Hệ Thống Sau Khi Lên

1. **Kiểm tra trạng thái Migration & Healthcheck:**
   ```bash
   docker compose ps
   ```
   *(Lưu ý: 2 job `auto-ontology-migrate` và `frontend-migrate` sẽ chạy một lần rồi thoát với mã `Exited (0)` — đây là hành vi chuẩn).*

2. **Truy cập các giao diện quản trị & Agent (Tài khoản mặc định):**
   - **Auto-Ontology Web UI:** `http://localhost:3000`
     - Email: `admin@yggdrasil.local` | Password: `yggdrasil_admin_123`
   - **NemoClaw Web Terminal / Dashboard:** `http://localhost:7681`
     - Gateway Token: `yggdrasil_super_secret_auth_key_2026`
   - **Arize Phoenix (Prompt CMS, Playground & OTLP Traces):** `http://localhost:6006`
     - Email: `admin@localhost` | Password: `admin`
   - **NeMo-Retriever Healthcheck:** `curl http://localhost:7670/v1/health`

3. **Kết nối Agent vào 2 cổng MCP Server:**
   - **Cổng SQL / Ontology MCP:** `http://localhost:3003/mcp`
   - **Cổng Tài liệu / SOP RAG MCP:** `http://localhost:7670/mcp`

---

## 4. Lưu Ý Quan Trọng Về Xử Lý Tiếng Việt (Vietnamese OCR Strategy)

### ⚠️ Giới hạn của `nemotron-ocr-v2`:
- Qua kiểm toán trực tiếp file từ điển giải mã `v2_multilingual/charset.txt` (14.246 tokens), model này chỉ hỗ trợ English, Chinese, Japanese, Korean, Russian và **KHÔNG HỖ TRỢ 67 ký tự có dấu tiếng Việt (0 / 67)**.
- Nếu ép đọc trực tiếp văn bản tiếng Việt sẽ bị **rụng toàn bộ dấu** hoặc sinh ký tự lỗi (`đ` $\rightarrow$ `d`, `ế` $\rightarrow$ `e`).

### ✅ Độ chính xác của 2 model Nemotron Vision với Bảng biểu Tiếng Việt:
- 2 model thị giác của NVIDIA là **`nemotron-page-elements-v3`** và **`nemotron-table-structure-v1`** (sử dụng kiến trúc backbone YOLOX 54M) chạy dựa trên cấu trúc pixel hình học (Visual Geometry) nên **không phụ thuộc ngôn ngữ**. 
- Thử nghiệm thực tế trên trang số liệu tài chính tiếng Việt (Trang 19 Báo cáo tài chính) cho kết quả chính xác 100%: nhận diện đúng 7 dòng, 2 cột, 14 ô cell độc lập trong 0.6 giây.

### 🎯 Chiến lược xử lý văn bản Tiếng Việt:
1. **Phương án 1 — "Fast-to-Market" (Triển khai ngay — Khuyên dùng):**
   - Giữ nguyên 2 model **`nemotron-page-elements-v3`** và **`nemotron-table-structure-v1`** của NVIDIA để cắt layout và bổ lưới ô cell.
   - Thay thế bước đọc chữ trong cell bằng **PaddleOCR Tiếng Việt (`lang='vi'`)** chạy local (nặng ~10MB, mã nguồn mở, hỗ trợ chuẩn 100% tiếng Việt có dấu).
2. **Phương án 2 — "Pure Vendor Tier" (Thuần NVIDIA — Sẽ có hỗ trợ sau):**
   - Giữ thuần 100% stack NVIDIA, không train lại từ đầu cả 83.8M tham số.
   - **Đóng băng (Freeze):** `Detector` (45.4M) và `Relational model` (2.3M) vì chúng đã làm rất tốt khâu dò vị trí dòng chữ và thứ tự đọc.
   - **Chỉ Fine-tune:** Con **`Recognizer` (36.1M)**: Thêm 67 ký tự tiếng Việt vào `charset.txt`, đóng băng CNN Encoder (9.8M) và chỉ train lại Transformer Decoder + Linear Head (khoảng 26.3M tham số trainable với CTCLoss). Phần này sẽ có kịch bản và tài liệu hỗ trợ sau.

