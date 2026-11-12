# Hướng Dẫn Triển Khai Langfuse Production Stack (`02-langfuse`)

Tài liệu hướng dẫn vận hành chi tiết cụm LLMOps Langfuse v3 kết hợp **LiteLLM Proxy (Cầu dao Cắt tiền Tự động & Thu hồi API Key)**, **Native AI Gateway (Rust)**, ClickHouse OLAP, PostgreSQL, Redis và MinIO S3 Object Storage.

---

## 🔑 Bảng Thông Tin Truy Cập & Tài Khoản Mặc Định

| Dịch Vụ | Địa Chỉ Truy Cập | Tài Khoản / Thông Tin Kết Nối | Mục Đích |
| :--- | :--- | :--- | :--- |
| **LiteLLM Proxy & UI** | `http://localhost:4000` | **Master Key:** `sk-yggdrasil-master-admin-2026`<br>**Swagger UI:** `http://localhost:4000/` | **Cầu dao Cắt tiền Tự động (`max_budget` USD)**, giới hạn RPM/TPM, cấp & thu hồi Virtual Key (`/key/block`, `/key/delete`) |
| **Langfuse AI Gateway** | `http://localhost:3031` | Cổng LLM Proxy nội bộ (`/v1/...`) | Định tuyến Upstream, bảo mật Provider Key gốc |
| **Langfuse Web UI** | `http://localhost:3100` | Tự đăng ký tài khoản Admin ở lần đầu truy cập | Dashboard Sổ cái Kế toán FinOps, Prompts CMS, Evals |
| **MinIO Console** | `http://localhost:9091` | **User:** `minioadmin`<br>**Pass:** `minioadmin_secret_2026` | Quản lý bucket, raw payloads, multimodal blobs |
| **ClickHouse HTTP** | `http://localhost:8123` | **User:** `clickhouse`<br>**Pass:** `clickhouse_secret_password`<br>**Database:** `default` | API truy vấn dữ liệu phân tích OLAP |
| **ClickHouse Native** | `localhost:9002` | Port native cho migration và CLI client | Quản trị internal & migration |
| **PostgreSQL 16** | *Mạng nội bộ Docker* | **User:** `langfuse`<br>**Pass:** `langfuse_secret_password`<br>**DB:** `langfuse` (Schema `public` & `litellm`) | Lưu trữ metadata Langfuse + bảng ngân sách Virtual Keys của LiteLLM |
| **Redis 7** | *Mạng nội bộ Docker* | Port `6379` không cần mật khẩu | Bộ đếm Rate-Limit (RPM/TPM), trạng thái khóa Key tức thì & BullMQ |

---

## ⚡ Các Lệnh Kiểm Tra Sức Khỏe Nhanh (Smoke Test)

### 1. Kiểm tra trạng thái toàn bộ 8 containers
```bash
docker ps --filter name=yggdrasil-
```

### 2. Kiểm tra LiteLLM Proxy Health (Cầu dao FinOps)
```bash
curl http://localhost:4000/health/liveliness
# Kết quả mong đợi: "I'm alive!"
```

### 3. Kiểm tra AI Gateway Health
```bash
curl http://localhost:3031/health
# Kết quả mong đợi: {"status":"ok"}
```

### 3. Kiểm tra Ingestion API của Langfuse Web
```bash
curl http://localhost:3100/api/public/health
# Kết quả mong đợi: {"status":"OK","version":"3.227.0"}
```

### 4. Kiểm tra phản hồi ClickHouse
```bash
curl http://localhost:8123/ping
# Kết quả mong đợi: Ok.
```

---

## 🛑 Dừng & Tái Khởi Động

* **Dừng stack:**
  ```bash
  cd "deploy/ai-platform/02-langfuse"
  docker compose down
  ```
* **Xóa sạch dữ liệu (Reset sạch sẽ):**
  ```bash
  docker compose down -v
  ```
