# 02. Langfuse Production LLMOps (`02-langfuse`)

> **Triết lý:** Trạm thu phí trung tâm (**LiteLLM Proxy + Langfuse AI Gateway**) & Sổ cái kế toán AI (**FinOps Accounting**) theo mô hình **"Best-of-Breed Open Source"**.  
> Đóng vai trò là **"Cầu dao Cắt điện Tự động & Kế toán trưởng"** cho toàn bộ hệ thống AI: Mọi Agent bắt buộc đi qua chốt chặn **LiteLLM Proxy (`:4000`)** (kiểm soát trần chi tiêu USD `max_budget`, giới hạn RPM/TPM và cắt/thu hồi API Key tức thì) kết hợp **Langfuse Native AI Gateway (`:3031`)** và ghi sổ tức thì xuống **ClickHouse OLAP (`:8123`)**, giúp Phòng Kế toán và Sếp vừa nắm rõ từng xu chi phí, vừa tự động sập cầu dao ngắt điện ngay lập tức khi phòng ban tiêu lố hạn mức hoặc Agent bị lặp vô hạn!

---

## 📦 Danh Sách Các Services Trong Docker Compose

Toàn bộ cụm bao gồm **8 container** hoạt động đồng bộ trên mạng riêng `langfuse-net`:

| Service Container | Image & Phiên Bản | Port Host | Vai Trò & Chức Năng |
| :--- | :--- | :--- | :--- |
| **`litellm-proxy`** | `ghcr.io/berriai/litellm:main-stable` | `4000:4000` | **Cầu dao Cắt tiền Tự động & Quản lý Virtual Key:** Cấp/thu hồi/khóa API Key tức thì (`/key/block`, `/key/delete`), ép trần chi tiêu cứng (`max_budget` USD), giới hạn RPM/TPM trên Redis. |
| **`ai-gateway`** | `langfuse/ai-gateway:latest` | `3031:3031` | **Native Rust LLM Proxy:** Proxy trung tâm điều phối cuộc gọi LLM nội bộ, bảo mật Key gốc, Zero-code Tracing (< 3ms latency). |
| **`langfuse-web`** | `langfuse/langfuse:latest` (`v4.77+`) | `3100:3000` | Web UI Dashboard Sổ cái FinOps, Quản lý Prompt, Evals, và Ingestion API. |
| **`langfuse-worker`** | `langfuse/langfuse-worker:latest` | *Internal* | Async background worker xử lý batching, eval pipelines, blob encryption. |
| **`clickhouse`** | `clickhouse/clickhouse-server:latest` (`26.10+`) | `8123:8123`<br>`9002:9000` | CSDL phân tích OLAP cột, hỗ trợ inverted full-text index cho traces. |
| **`postgres`** | `postgres:16-alpine` | *Internal* | CSDL quan hệ lưu trữ Metadata: Users, Projects, RBAC (schema `public`) & bảng ngân sách Virtual Keys của LiteLLM (schema `litellm`). |
| **`redis`** | `redis:7-alpine` | *Internal* | Bộ đếm Rate-Limit (RPM/TPM), trạng thái khóa Key tức thì & Task queue (BullMQ). |
| **`minio`** | `cgr.dev/chainguard/minio:latest` | `9091:9091` (UI)<br>`9090:9000` (API) | S3-compatible Object Storage lưu trữ raw payloads, multimodal blobs & export files. |

> [!NOTE]
> * Cổng **LiteLLM Proxy** lắng nghe tại **`4000`** (cổng chính cho các Agent gọi vào để chịu sự kiểm soát ngân sách cứng và thu hồi Key tức thì).
> * Cổng Web UI của Langfuse được map sang **`3100`** để tránh xung đột cổng `3000` với `yggdrasil-ontology-ui` của nhánh `01-nvidia-framework`.  
> * Cổng Native AI Gateway lắng nghe tại **`3031`**.

---

## 🛡️ Kiến Trúc "Cầu Dao Kép" LiteLLM + Langfuse Trong Yggdrasil

Sự kết hợp giữa **LiteLLM Proxy (`:4000`)** và **Langfuse (`:3031` / `:3100`)** giải quyết triệt để bài toán vận hành tài chính AI thực tế: **Langfuse làm Sổ cái Kế toán & Quản trị Prompt**, còn **LiteLLM làm Cầu dao Cắt điện Tự động (Hard Spend Cap & Key Revocation)**:

```mermaid
sequenceDiagram
    autonumber
    actor Agent as Agent / Phòng Ban
    participant LiteLLM as ⚡ LiteLLM Proxy (:4000)<br/>(Hard Spend Cap & Key Revocation)
    participant Redis as Redis + Postgres<br/>(Budget & Rate-Limit State)
    participant GW as Langfuse AI Gateway (:3031, Rust)
    participant NIM as NVIDIA NIM / Model Provider
    participant CH as ClickHouse OLAP (:8123)
    participant UI as Langfuse Web Dashboard (:3100)

    Agent->>LiteLLM: 1. Gửi request LLM (Virtual Key: sk-ygg-finance-xxx)
    LiteLLM->>Redis: 2. Kiểm tra trạng thái Key (Blocked?), RPM/TPM & Hạn mức USD (max_budget)
    alt Key đã bị thu hồi hoặc Vượt trần ngân sách USD
        Redis-->>LiteLLM: Báo vượt trần / Key bị khóa!
        LiteLLM-->>Agent: ❌ CẮT ĐIỆN TỨC THÌ (HTTP 401 KeyBlocked / 429 BudgetExceededError)
        LiteLLM-)CH: Ghi log sự cố chặn ngân sách vào Langfuse ClickHouse
    else Trong hạn mức cho phép
        LiteLLM->>GW: 3. Chuyển tiếp Request hợp lệ
        GW->>NIM: 4. Gọi Upstream NVIDIA NIM / OpenAI
        NIM-->>GW: 5. Trả Stream Completion & Token Usage
        GW-->>LiteLLM: 6. Trả kết quả (< 3ms overhead)
        LiteLLM-->>Agent: 7. Trả kết quả cho Agent & Cộng dồn chi phí USD vào Postgres/Redis
        LiteLLM-)CH: 8. Đồng bộ Trace, Latency, Prompt & Cost USD vào ClickHouse
        UI->>CH: 9. Báo cáo FinOps, Audit Log & Kích hoạt Auto-Evals
    end
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

* ✅ **Cầu dao Cắt tiền Tự động & Thu hồi Key tức thì (LiteLLM Proxy `:4000`):** Khắc phục hoàn toàn điểm mù của Langfuse AI Gateway Beta bằng cách đặt **LiteLLM Proxy** đứng trước: ép trần ngân sách cứng (`max_budget` USD theo ngày/tháng), giới hạn RPM/TPM trên Redis, và cho phép cắt/khóa/thu hồi API Key của bất kỳ phòng ban hay nhân sự nào chỉ bằng 1 lệnh API (`/key/block`, `/key/delete`).

### Nhược điểm & Lưu ý thực tế (Cons):
* ⚠️ **Bắt buộc đi kèm ClickHouse Engine:** Langfuse v4 yêu cầu bắt buộc phải có ClickHouse để chạy. Tuy nhiên, nếu ở tầng Data Platform bên dưới công ty đã có sẵn cụm ClickHouse rồi thì cực kỳ lợi: chỉ cần tạo thêm 1 database `langfuse` chung vào cụm đó là xong (không tốn thêm RAM nuôi container mới). Chỉ khi dựng lẻ độc lập từ đầu mới phải cõng thêm container ClickHouse (~4GB RAM).

---

## 🚀 Hướng Dẫn Vận Hành: Cấp Key, Khóa Trần Tiền & Cắt/Thu Hồi API Key

### Bước 1: Khởi động toàn bộ cụm dịch vụ (8 Containers)

```bash
cd "deploy/ai-platform/02-langfuse"
docker compose up -d
```

### Bước 2: Tạo tài khoản Admin & Cấu hình Langfuse (`:3100`)
1. Mở trình duyệt truy cập: **`http://localhost:3100`** $\rightarrow$ **Sign Up** tạo tài khoản Admin.
2. Tạo Organization (`Yggdrasil-Corp`) và Project đầu tiên $\rightarrow$ lấy cặp `LANGFUSE_PUBLIC_KEY` và `LANGFUSE_SECRET_KEY` điền vào `.env`.
3. *(Tùy chọn)* Vào **AI Gateway** (`:3031`) $\rightarrow$ **Providers & Models** nạp API Key gốc của NVIDIA NIM / OpenAI.

### Bước 3: Cấp Virtual API Key kèm Trần Ngân Sách Cứng (`max_budget`) qua LiteLLM (`:4000`)
Dùng `LITELLM_MASTER_KEY` để cấp cho Phòng Kế toán 1 chiếc chìa khóa ảo giới hạn cứng **$5.00 USD / tháng** và tối đa **30 requests/phút**:

```bash
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer sk-yggdrasil-master-admin-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "key_alias": "key-agent-ke-toan",
    "team_id": "finance-department",
    "max_budget": 5.0,
    "budget_duration": "30d",
    "rpm_limit": 30,
    "tpm_limit": 50000,
    "metadata": {"department": "finance", "owner": "accountant_chief"}
  }'
# Trả về: {"key": "sk-ygg-xxxxxxxxxxxxxxxx", "max_budget": 5.0, ...}
```

### Bước 4: Cắt / Khóa Tạm Thời hoặc Thu Hồi Vĩnh Viễn API Key Trong 1 Giây
Khi phát hiện Agent bị lỗi lặp vô hạn hoặc nhân sự nghỉ việc, Admin cắt quyền truy cập ngay lập tức mà **không ảnh hưởng đến API Key gốc**:

```bash
# 1. Khóa tạm thời (Block Key ngay lập tức trên Redis/Postgres):
curl -X POST http://localhost:4000/key/block \
  -H "Authorization: Bearer sk-yggdrasil-master-admin-2026" \
  -H "Content-Type: application/json" \
  -d '{"key": "sk-ygg-xxxxxxxxxxxxxxxx"}'

# 2. Mở khóa lại Key (Unblock Key):
curl -X POST http://localhost:4000/key/unblock \
  -H "Authorization: Bearer sk-yggdrasil-master-admin-2026" \
  -H "Content-Type: application/json" \
  -d '{"key": "sk-ygg-xxxxxxxxxxxxxxxx"}'

# 3. Thu hồi & Xóa vĩnh viễn Key (Revoke / Delete Key):
curl -X POST http://localhost:4000/key/delete \
  -H "Authorization: Bearer sk-yggdrasil-master-admin-2026" \
  -H "Content-Type: application/json" \
  -d '{"keys": ["sk-ygg-xxxxxxxxxxxxxxxx"]}'
```

### Bước 5: Test gọi Model qua Chốt chặn LiteLLM (`:4000`)

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-ygg-xxxxxxxxxxxxxxxx" \
  -d '{
    "model": "yggdrasil-default-llm",
    "messages": [{"role": "user", "content": "Xin chào, kiểm tra cầu dao FinOps LiteLLM + Langfuse!"}]
  }'
```

---

## ⚡ Các Lệnh Kiểm Tra Sức Khỏe Nhanh (Smoke Test)

```bash
# 1. Kiểm tra trạng thái 8 container
docker ps --filter name=yggdrasil-

# 2. Kiểm tra LiteLLM Proxy Health (Cầu dao FinOps)
curl http://localhost:4000/health/liveliness
# Mong đợi: "I'm alive!"

# 3. Kiểm tra AI Gateway Health
curl http://localhost:3031/health
# Mong đợi: {"status":"ok"}

# 4. Kiểm tra Ingestion API của Langfuse Web
curl http://localhost:3100/api/public/health
# Mong đợi: {"status":"OK","version":"4.77.0"}

# 5. Kiểm tra ClickHouse OLAP
curl http://localhost:8123/ping
# Mong đợi: Ok.

# 6. Xem danh sách bảng ClickHouse đã khởi tạo
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
