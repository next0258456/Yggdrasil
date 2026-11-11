# 02. Langfuse Production LLMOps (`02-langfuse`)

> **Triết lý:** Trạm thu phí trung tâm (**AI Gateway**) & Sổ cái kế toán AI (**FinOps Accounting**) theo mô hình **"Best-of-Breed Open Source"**.  
> Đóng vai trò là **"Kế toán trưởng & Kiểm toán viên"** cho toàn bộ hệ thống AI: Mọi Agent bắt buộc đi qua cổng **Langfuse Native AI Gateway** và ghi sổ tức thì xuống **ClickHouse OLAP**, giúp Phòng Kế toán và Sếp nắm rõ từng phòng ban, từng nhân sự đang tiêu bao nhiêu tiền, vào tác vụ gì, có hiệu quả hay không (Automated Evals & 1-giây Prompt Rollback).

---

## 📦 Danh Sách Các Services Trong Docker Compose

Toàn bộ cụm bao gồm **7 container** hoạt động đồng bộ trên mạng riêng `langfuse-net`:

| Service Container | Image & Phiên Bản | Port Host | Vai Trò & Chức Năng |
| :--- | :--- | :--- | :--- |
| **`ai-gateway`** | `langfuse/ai-gateway:latest` | `3031:3031` | **Native Rust LLM Proxy:** Proxy trung tâm điều phối mọi cuộc gọi LLM, bảo mật Key, Zero-code Tracing (< 3ms latency). |
| **`langfuse-web`** | `langfuse/langfuse:latest` (`v4.77+`) | `3100:3000` | Web UI Dashboard, Quản lý Prompt, Evals, và Ingestion API. |
| **`langfuse-worker`** | `langfuse/langfuse-worker:latest` | *Internal* | Async background worker xử lý batching, eval pipelines, blob encryption. |
| **`clickhouse`** | `clickhouse/clickhouse-server:latest` (`26.10+`) | `8123:8123`<br>`9002:9000` | CSDL phân tích OLAP cột, hỗ trợ inverted full-text index cho traces. |
| **`postgres`** | `postgres:16-alpine` | *Internal* | CSDL quan hệ lưu trữ Metadata: Users, Projects, RBAC, API Keys. |
| **`redis`** | `redis:7-alpine` | *Internal* | Task queue (BullMQ) & caching trung gian. |
| **`minio`** | `cgr.dev/chainguard/minio:latest` | `9091:9091` (UI)<br>`9090:9000` (API) | S3-compatible Object Storage lưu trữ raw payloads, multimodal blobs & export files. |

> [!NOTE]
> * Cổng Web UI của Langfuse được map sang **`3100`** để tránh xung đột cổng `3000` với `yggdrasil-ontology-ui` của nhánh `01-nvidia-framework`.  
> * Cổng Native AI Gateway lắng nghe tại **`3031`**.

---

## 🛡️ Kiến Trúc "All-in-One" Langfuse AI Gateway Trong Yggdrasil

Thay vì gọi trực tiếp sang OpenAI, Anthropic hay NVIDIA NIM, toàn bộ lưu lượng của Agent và Pipeline RAG được hội tụ trực tiếp qua **Langfuse Native AI Gateway**:

```mermaid
sequenceDiagram
    autonumber
    actor Agent as Agent / Ứng Dụng
    participant GW as Langfuse AI Gateway (:3031, Rust)
    participant NIM as NVIDIA NIM / Model Provider
    participant CH as ClickHouse OLAP (:8123)
    participant UI as Langfuse Web Dashboard (:3100)

    Agent->>GW: 1. Gửi request LLM (kèm Gateway Key: lf-gw-xxx)
    GW->>GW: 2. Xác thực Key, giải mã Upstream Provider Key
    GW->>NIM: 3. Chuyển tiếp Request tới NVIDIA NIM / OpenAI
    NIM-->>GW: 4. Trả về Stream Completion & Token Usage
    GW-->>Agent: 5. Trả kết quả về cho Agent (Overhead < 3ms)
    GW-)CH: 6. Ghi ngầm Trace, Latency, Prompt & Cost vào ClickHouse
    UI->>CH: 7. Báo cáo FinOps, Audit Log & Kích hoạt Auto-Evals
```

---

## 🌟 4 Điểm Cốt Lõi Của Nhánh 02-Langfuse

### 1. Zero-Code Tracing (Không Cần Cài SDK Langfuse)
* Agent của phòng ban chỉ cần gọi theo chuẩn OpenAI API thông thường, trỏ `base_url` về Gateway:
  ```python
  from openai import OpenAI

  client = OpenAI(
      base_url="http://localhost:3031/v1",
      api_key="lf-gw-xxxxxxxxxxxx",
  )
  ```
* Mọi prompt, completion, số lượng token, latency p50/p95/p99 tự động ghi thẳng vào ClickHouse OLAP mà không cần chèn mã decorator vào codebase.

### 2. Bảo Mật Tuyệt Đối API Key Gốc (Key Vault)
* Lập trình viên và Agent **không bao giờ nhìn thấy** NVIDIA NIM Key hay OpenAI Key thật.
* Key gốc được mã hóa lưu tập trung trong Langfuse UI (`Organization Settings` $\rightarrow$ `AI Gateway` $\rightarrow$ `Providers & Models`). 
* Agent từng phòng ban chỉ được cấp **Gateway Key** (`lf-gw-...`) với metadata phân quyền (`team: finance`, `team: marketing`).

### 3. Prompt Management & Rollback trong 1 Giây (So Sánh Với Bộ Đôi NVIDIA/SkillEvaluator & Arize Phoenix)

| Tiêu Chí | Langfuse v4 (Nhánh 02) | Arize Phoenix (Nhánh 01) | NVIDIA SkillEvaluator (Nhánh 01) |
| :--- | :--- | :--- | :--- |
| **Quản lý Prompt tập trung** | 🏆 **Tách rời 100% khỏi Code:** Prompt lưu trên UI, hỗ trợ biến Mustache (`{{schema}}`). | ❌ Không có (Phoenix chỉ log prompt tĩnh đi kèm trace). | ❌ Không có (Prompt viết cứng trong code Python của Agent). |
| **Vòng đời & Gán nhãn môi trường** | 🏆 **Rất mạnh:** Hỗ trợ nhãn `production`, `staging`, `canary` linh hoạt. | ⚠️ Sơ khai (chủ yếu là playground thử nghiệm). | ❌ Quản lý thủ công qua Git commit. |
| **Tốc độ Rollback khi có sự cố** | ⚡ **1 Giây:** Bấm nút rollback trên UI, Agent tự kéo prompt mới mà **không cần rebuild hay restart container**. | ⏱️ Chậm: Phải sửa code, commit Git và restart container. | ⏱️ Chậm: Phải chạy lại pipeline kiểm thử và redeploy code. |
| **Liên kết Prompt Version với Live Evals** | 🏆 **Thời gian thực:** Đối chiếu trực tiếp Prompt v1.2 vs v1.3 xem bản nào sinh câu trả lời ít ảo giác hơn ngay trên production traffic. | ⚠️ Evals tốt nhưng không gắn chặt theo từng version của prompt ngoài runtime. | 🎯 Rất mạnh về benchmark kỹ năng Agent (Task Success Rate), nhưng chạy dạng offline evaluation. |

* **Điểm vượt trội thực tế:** Trong khi `SkillEvaluator` là thước đo kỹ năng trong phòng thí nghiệm và `Phoenix` là kính hiển vi soi trace lúc debug, thì **Langfuse đóng vai trò là "Bảng điều khiển tác chiến"**: Cho phép Product Manager và Domain Expert trực tiếp tinh chỉnh prompt, thử nghiệm A/B canary, và rollback tức thì khi phát hiện Agent nói linh tinh mà không cần phiền đến kỹ sư Backend!

### 4. Automated Evals (LLM-as-a-Judge)
* Tự động chấm điểm mọi lượt trả lời của Agent theo bộ 3 chỉ số **RAG Triad**:
  * **Faithfulness (Độ trung thực):** Phát hiện ảo giác so với văn bản ngữ cảnh.
  * **Answer Relevance:** Đánh giá câu trả lời có đúng trọng tâm câu hỏi.
  * **SQL Correctness:** Kiểm tra cú pháp SQL trước khi thực thi vào database.

---

## ⚖️ Đánh Giá Ưu & Nhược Điểm (Pros & Cons)

### Ưu điểm (Pros):
* ✅ **Minh bạch tài chính cho Phòng Kế Toán (FinOps & Cost Attribution):** Thay vì cuối tháng nhận một cục hóa đơn mù mờ, Phòng Kế Toán biết chính xác **phòng ban nào, nhân sự nào, hay con Agent nào đã tiêu bao nhiêu tiền, vào khung giờ nào và cho tác vụ gì** thông qua cơ chế cấp Gateway Key gắn nhãn (`team: finance`, `team: hr`, `user_id`).
* ✅ **Hạch toán khấu hao GPU nội bộ (Internal Chargeback):** Kể cả khi chạy model miễn phí tự host (NVIDIA NIM local), sếp vẫn áp được đơn giá nội bộ (\$/1M token) trên Langfuse để tính toán phòng ban nào đang ngốn nhiều tài nguyên server/điện năng nhất.
* ✅ **Trạm thu phí trung tâm (Native AI Gateway):** Gom toàn bộ API Key gốc của công ty về một két sắt duy nhất. Nhân viên và Agent chỉ được cấp vé qua trạm (`lf-gw-...`); nhân viên nghỉ việc hoặc Agent bị lỗi chỉ cần thu hồi vé trong 1 click mà không sợ lộ Key gốc.
* ✅ **Đo lường hiệu quả đồng tiền (ROI trên từng Prompt):** Gắn liền số tiền đã đốt với chất lượng câu trả lời (Auto-Evals), giúp sếp phát hiện ngay phòng ban nào đang đốt tiền vô ích cho những câu lệnh bị ảo giác để chỉnh sửa hoặc rollback Prompt tức thì (1 giây).
* ✅ **Truy vấn sổ cái tức thì nhờ ClickHouse OLAP:** Kế toán bấm lọc báo cáo chi phí của cả quý hoặc tra cứu lịch sử kiểm toán (`audit_logs`) trên hàng triệu lượt gọi chỉ mất vài chục mili-giây.

### Nhược điểm & Lưu ý thực tế (Cons):
* ⚠️ **AI Gateway đang ở bản Beta (Chưa có cầu dao cắt tiền tự động):** Langfuse làm cực tốt vai trò "Kế toán trưởng" (đếm tiền, phân bổ chi phí, bắn cảnh báo), nhưng tính năng **Hard Spend Limit (tự động sập cầu dao ngắt điện khi phòng ban tiêu lố hạn mức USD)** vẫn đang nằm trên Roadmap. Muốn cắt điện tự động 100% ở production, hiện tại **bắt buộc phải chạy kèm 1 service riêng đứng trước (khuyên dùng LiteLLM Proxy)**.
* ⚠️ **Bắt buộc đi kèm ClickHouse Engine:** Langfuse v4 yêu cầu bắt buộc phải có ClickHouse để chạy. Tuy nhiên, nếu ở tầng Data Platform bên dưới công ty đã có sẵn cụm ClickHouse rồi thì cực kỳ lợi: chỉ cần tạo thêm 1 database `langfuse` chung vào cụm đó là xong (không tốn thêm RAM nuôi container mới). Chỉ khi dựng lẻ độc lập từ đầu mới phải cõng thêm container ClickHouse (~4GB RAM).

---

## 🚀 Hướng Dẫn Vận Hành Từng Bước

### Bước 1: Khởi động toàn bộ cụm dịch vụ

```bash
cd "ai platform/02-langfuse"
docker compose up -d
```

### Bước 2: Tạo tài khoản Admin
1. Mở trình duyệt truy cập: **`http://localhost:3100`**
2. Bấm **Sign Up** để tạo tài khoản admin đầu tiên.
3. Tạo Organization (ví dụ: `Yggdrasil-Corp`) và Project đầu tiên.

### Bước 3: Cấu hình AI Gateway & Nạp Provider Key
1. Bấm vào tên Organization ở góc trên bên trái $\rightarrow$ chọn **AI Gateway**.
2. Vào mục **Providers & Models** $\rightarrow$ bấm **Add Provider**:
   * Dán API Key thật của NVIDIA NIM hoặc OpenAI vào đây.
3. Vào mục **Gateway keys** $\rightarrow$ bấm **+ Create key**:
   * Chọn loại **Service account key**.
   * Đặt tên: `key-agent-ke-toan`.
   * Gắn metadata: `{"team": "finance"}`.
   * Sao chép key dạng `lf-gw-xxxxxxxxxxxx`.

### Bước 4: Test gọi Model qua Gateway

```bash
curl http://localhost:3031/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer lf-gw-xxxxxxxxxxxx" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Xin chào, kiểm tra kết nối AI Gateway!"}]
  }'
```

---

## ⚡ Các Lệnh Kiểm Tra Sức Khỏe Nhanh (Smoke Test)

```bash
# 1. Kiểm tra trạng thái 7 container
docker ps --filter name=yggdrasil-langfuse

# 2. Kiểm tra AI Gateway Health
curl http://localhost:3031/health
# Mong đợi: {"status":"ok"}

# 3. Kiểm tra Ingestion API của Langfuse Web
curl http://localhost:3100/api/public/health
# Mong đợi: {"status":"OK","version":"4.77.0"}

# 4. Kiểm tra ClickHouse OLAP
curl http://localhost:8123/ping
# Mong đợi: Ok.

# 5. Xem danh sách bảng ClickHouse đã khởi tạo
docker exec yggdrasil-langfuse-clickhouse clickhouse-client -u clickhouse --password clickhouse_secret_password --query "SHOW TABLES;"
```

---

## 🛑 Dừng & Reset Dữ Liệu

* **Dừng toàn bộ cụm:**
  ```bash
  docker compose down
  ```
* **Xóa sạch dữ liệu (Reset sạch sẽ volume):**
  ```bash
  docker compose down -v
  ```
