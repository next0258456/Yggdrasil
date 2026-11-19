# Hướng Dẫn Triển Khai (`03-y7l-native`)

Kiến trúc thực dụng lấy **`n8n` làm trung tâm** kết hợp 1 sidecar Python siêu mỏng **`y7l-tools` (`:8300`)** chuyên xử lý tác vụ Track B (DuckDB RLS, Obsidian Zero-Chunking, Voice Memo tối thiểu STT/TTS, PDF/OCR nhẹ và JWT 10h).

---

## 1. Bảng Cổng & Thành Phần

| Thành phần | Cổng (Mặc định) | Cổng (Standalone) | Vai trò |
| :--- | :---: | :---: | :--- |
| **`y7l-tools` (Sidecar Track B)** | `:8300` | `:8300` | FastAPI + In-Process DuckDB RLS, Obsidian Vault loader, Edge-TTS/Whisper proxy, PDF extractor |
| **`n8n` (Trung tâm điều phối & RAG)** | `:5678` *(có sẵn)* | `:5679` | Chạy 6 workflow: Chat/Voice Memo, Obsidian SQL RAG, SOP Hybrid RAG, Webview Login, HR IAM Kill-Switch, FinOps Token Ledger |
| **`LiteLLM Proxy`** | `:4000` *(có sẵn)* | `:4001` | Cầu dao cắt tiền (`max_budget`), RPM/TPM limit, khóa/thu hồi Virtual Key trong 1s |
| **`Redis`** | `:6379` *(có sẵn)* | `:6380` | Lưu phiên JWT 10h (`y7l:session:<uid>`), Metric Cache, bộ đếm chi tiêu tháng |
| **`Postgres + pgvector`** | *(tuỳ chọn)* | `:5434` | Bảng `y7l_sop_chunks` & hàm `y7l_hybrid_search_sop` (Dense + BM25 + RRF) cho `WF-03` |

---

## 2. Cấu Hình Google Sheet Ngày 1 (Không Cần Langfuse/ClickHouse)

### Sheet 1: `AI_Token_Ledger` (Dành cho `WF-06`)
Tạo tab **`AI_Token_Ledger`** với dòng tiêu đề (Row 1):
`timestamp | month | department | user_id | workflow | model | prompt_tokens | completion_tokens | total_tokens | estimated_cost_usd | status`

### Sheet 2: `HR_Master_IAM` (Dành cho `WF-05`)
Tạo tab **`HR_Master_IAM`** với dòng tiêu đề (Row 1):
`username | chat_user_id | department | region | role | status | revoke_session`

---

## 3. Các Bước Khởi Chạy

### Bước 1: Tạo `.env` và seed dữ liệu mẫu
```bash
cd deploy/ai-platform/03-y7l-native
cp .env.example .env
uv sync --extra dev
uv run python data/seed_data.py
```

### Bước 2: Chạy kiểm định Vault Linter, Evals & Unit Tests
```bash
uv run python evals/vault_linter.py
uv run python evals/run_evals.py
uv run pytest -v
```

### Bước 3: Khởi động Sidecar `y7l-tools`

* **Chế độ mặc định** (dùng `n8n :5678`, `Redis :6379`, `LiteLLM :4000` đang chạy sẵn trên máy):
  ```bash
  docker compose up -d
  ```
* **Chế độ Standalone** (server mới chưa có bất kỳ dịch vụ nào):
  ```bash
  docker compose --profile standalone up -d
  ```

### Bước 4: Nạp Schema Hybrid RAG & Import 6 Workflows vào `n8n`
1. Nếu dùng `Postgres + pgvector` riêng, chạy script khởi tạo bảng & hàm RRF:
   ```bash
   psql "$DATABASE_URL" -f db/init_sop_hybrid.sql
   ```
   *(Với `--profile standalone`, file [`db/init_sop_hybrid.sql`](./db/init_sop_hybrid.sql) tự chạy khi khởi tạo container `y7l-postgres`.)*
2. Import 6 file JSON trong [`n8n-workflows/`](./n8n-workflows/) vào n8n ở trạng thái `inactive` rồi gán credential (`Redis`, `Postgres`, `Google Sheets`):
   ```bash
   N8N_URL=http://localhost:5678 N8N_API_KEY=your_api_key uv run python scripts/import_n8n_workflows.py
   ```

---

## 4. Smoke Test Nhanh (Track-B Sidecar `:8300`)

```bash
# 1. Healthcheck
curl http://localhost:8300/health

# 2. Kiểm tra Obsidian Vault Linter
curl http://localhost:8300/vault/lint

# 3. Đăng nhập lấy 10h JWT cho sale_north
TOKEN=$(curl -s -X POST http://localhost:8300/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"sale_north","password":"north123","chat_user_id":"zalo_n01"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 4. Kiểm tra RLS Isolation (sale_north thử truy vấn South -> phải trả về empty=true)
curl -X POST http://localhost:8300/sql/execute-rls \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT * FROM gold_sales_obt WHERE region = '\''South'\''"}'
```

---

## 5. Nâng Cấp Ngày 10 Lên Langfuse + ClickHouse (0 Dòng Sửa n8n)

Khi doanh nghiệp đã có cụm ClickHouse và cần Prompt CMS Rollback 1s hoặc Auto-Evals sâu trên UI:
1. Khởi động [`../02-langfuse/docker-compose.yaml`](../02-langfuse/docker-compose.yaml).
2. Điền `LANGFUSE_PUBLIC_KEY` và `LANGFUSE_SECRET_KEY` cho container `LiteLLM Proxy (:4000)`.
3. Giữ nguyên 100% 6 workflow trong `n8n`: mọi request qua `LiteLLM (:4000)` sẽ tự đổ trace vào ClickHouse song song với Google Sheet `AI_Token_Ledger`.
