# Yggdrasil Data Platform - Consolidated Architecture

Tài liệu này tổng hợp toàn bộ thiết kế hệ thống Yggdrasil, đồng thời phân tích và chỉ ra các điểm không nhất quán (inconsistencies) giữa các tài liệu thiết kế ban đầu để đưa ra giải pháp thống nhất.

---

## PHẦN 1: TỔNG QUAN KIẾN TRÚC HỆ THỐNG

### 1. Tuyên ngôn Cốt lõi (The 3 Pillars)
- **Decoupled Compute & Storage:** Tách biệt Tính toán (DuckDB/Polars) và Lưu trữ (MinIO + Iceberg). Dữ liệu được truy vấn tại chỗ (Zero-copy).
- **Config-Driven & Data Contracts:** Logic Transformation nằm trong Code (Polars/dbt), nhưng Luồng định tuyến (Routing) nằm trong Config. Hợp đồng dữ liệu (Data Contracts) được thực thi nghiêm ngặt ngay từ cổng Ingestion để chặn dữ liệu rác.
- **Data-Blind AI & Zero Trust:** LLM (Mimir Bot) tuyệt đối không chạm vào dữ liệu tài chính thô. Bot chỉ được truy xuất siêu dữ liệu (Metadata) và lấy dữ liệu thật thông qua cổng bảo mật (Superset) được kiểm soát bởi phân quyền RLS và JWT.

### 2. Ma Trận Công Nghệ (Tech Stack)
- **Storage:** MinIO / AWS S3 (Object Storage)
- **Table Format:** Apache Iceberg
- **Catalog:** Postgres JDBC Catalog (Single Source of Truth cho metadata)
- **Compute:** Polars (ETL) & DuckDB (OLAP - Single-Node Big Data)
- **Orchestration:** n8n (Control Plane, APIs) & Airflow 3 (Data Pipeline DAGs)
- **Serving & Security:** Apache Superset (chạy Embedded DuckDB engine)
- **Knowledge/Semantic Layer:** Obsidian (Markdown Knowledge Graph)
- **AI Gateway:** n8n đóng vai trò làm Webhook Server kết nối Zalo (Mimir Bot)

### 3. Thiết Kế Các Tầng (Layers)

**Tầng 1: Ingestion (Trích xuất)**
- **API/Event Ingestion:** Dùng `n8n` để hút dữ liệu (SaaS, Webhook) và đổ trực tiếp dữ liệu thô (JSON/CSV) xuống MinIO.
- **Database Ingestion:** Dùng `DuckDB` + `Airflow` với 2 chế độ (Feature Flags):
  - `FULL_SNAPSHOT_DIFF`: Dùng DuckDB Scanner quét và tính toán (Out-of-Core) thay đổi trực tiếp (yêu cầu hạ tầng SSD/NVMe).
  - `INCREMENTAL_CDC`: Dùng Debezium + Redpanda để đổ dữ liệu real-time trực tiếp ra định dạng Iceberg.

**Tầng 2: Storage (Hồ dữ liệu - Medallion Architecture)**
- **Bronze (Raw):** Dữ liệu thô nguyên bản (Parquet/JSON). Chia thư mục (Partition) theo Ingestion Time.
- **Silver (Cleaned):** Dữ liệu đã làm sạch. Chuẩn Apache Iceberg. Partition theo Business Time.
- **Gold (Aggregated):** Bảng OBT (One-Big-Table) trải phẳng phục vụ BI/AI. Chuẩn Apache Iceberg.
- **Bảo trì:** Chạy VACUUM định kỳ để dọn dẹp các Orphan files của Iceberg, giải phóng ổ cứng.

**Tầng 3: Serving & Security**
- **Embedded OLAP:** Superset cài thư viện `duckdb-engine`, đọc trực tiếp Parquet/Iceberg từ MinIO. Loại bỏ cụm OLAP độc lập.
- **Bảo mật (Security):** Tích hợp Row-Level Security (RLS) để phân quyền truy cập theo từng dòng dữ liệu dựa vào User Context. Xác thực qua OAuth2 hoặc JWT.
- **Caching:** Hai lớp Cache (Metadata và Query Data) để giảm tải MinIO/DuckDB với các query lặp lại.

**Tầng 4: Knowledge & Semantic Layer**
- **Tách biệt Logic:** Tính toán số học được lưu trong Native BI (Saved Metrics trong Superset). Ngữ cảnh kinh doanh (Business Glossary, Data Traps) lưu trong Obsidian.
- **Obsidian Vault:** Sử dụng liên kết [[Wikilinks]] để tạo mạng lưới đồ thị tri thức. AI duyệt đồ thị này (Graph Traversal) để nhặt ngữ cảnh chính xác tuyệt đối, thay thế RAG/Vector Database truyền thống.

**Tầng 5: AI Gateway & Orchestration (Mimir Bot)**
- **Giao diện:** Tương tác qua Chat (Zalo Official Account) phục vụ C-level và Sale tiền tuyến trên điện thoại di động.
- **Xác thực:** Dùng kiến trúc Zalo-Webview (Out-of-band Authentication) nhập form an toàn. Đổi lấy token JWT từ Superset, ánh xạ với ID của Zalo để duy trì định danh và RLS.
- **IAM Auto-Provisioning:** Tự động tạo/phân quyền User trên Superset thông qua file cấu hình trung tâm (Google Sheets).

---

## PHẦN 2: CÁC ĐIỂM KHÔNG NHẤT QUÁN (INCONSISTENCIES FOUND)

Qua quá trình rà soát toàn bộ tài liệu thiết kế (từ file `00` đến `10` và `ADR_01`), kiến trúc hiện tại đang tồn tại 2 sự mâu thuẫn cốt lõi cần được quy hoạch lại:

### 🔴 Mâu thuẫn 1: Phân mảnh công cụ Transformation (Polars vs dbt vs DuckDB)
- **Tài liệu `00_Data_Engineering_Manifesto` & `10_Y7L`:** Khẳng định "Logic chuyển đổi (Transformations) nằm trong mã nguồn (**Polars**)".
- **Tài liệu `02_Storage_Layer_Design`:** Ghi chú ở lớp Silver rằng dữ liệu "đã được **DuckDB** làm sạch", chưa phản ánh vai trò của Polars hay dbt.
- **Tài liệu `ADR_01_Transformation_dbt_Decision`:** Quyết định **giữ dbt (kèm dbt-duckdb)** cho việc biến đổi dữ liệu từ lớp Silver lên Gold, và giao **Python (Polars/DuckDB/Pydantic)** làm sạch từ Bronze lên Silver.
=> **Kết luận:** Tài liệu `00`, `02` và `10` chưa cập nhật theo quyết định ở `ADR_01`, dẫn đến sự nhầm lẫn về việc công cụ nào thực sự đảm nhiệm lớp nào.

### 🔴 Mâu thuẫn 2: Cơ chế hoạt động của Bot Mimir (Sinh SQL hay Gọi API?)
- **Tài liệu `10_Y7L_Technology_Stack_Blueprint` & `05_AI_Gateway_Layer_Design`:** Mimir (Bot AI) tuân thủ nguyên lý *Data-Blind AI* và đóng vai trò như một **Intent Router** (Bộ định tuyến ý định). Mimir **không sinh câu lệnh SQL** mà sử dụng Tool Calling (chuyển câu hỏi thành tham số) để gọi API của Superset.
- **Tài liệu `04_Knowledge_Semantic_Layer_Design`:** Ở phần 3 lại viết: *"Mimir ghép nội dung Markdown... và **sinh ra câu lệnh SQL chính xác 100%** nhờ né được các 'Data Traps'"*.
=> **Kết luận:** Việc Mimir tự sinh SQL thô trực tiếp đọc Database đi ngược hoàn toàn với nguyên tắc Zero Trust và phá vỡ quy hoạch đẩy phần Logic Toán học vào "Superset Saved Metrics".

---

## PHẦN 3: ĐỀ XUẤT CHUẨN HÓA (PROPOSED RESOLUTIONS)

Để hệ thống nhất quán từ triết lý đến triển khai, các tài liệu thiết kế (`00`, `02`, `04`, `10`) nên được điều chỉnh theo các quy chuẩn sau:

### ✅ 1. Làm rõ Pipeline Transformation (Resolve Mâu thuẫn 1)
Chấp thuận kiến trúc chia làm 2 chốt chặn (Gates) theo `ADR_01`:
- **Gate 1 (Bronze -> Silver - Data Cleaning):** Thuộc lãnh địa của **Python (Polars)**. Sử dụng cơ chế `LazyFrame` của Polars kết hợp với các thao tác `filter` và `drop` để làm sạch dữ liệu (lọc NULL, ép kiểu, loại bỏ rác). Quá trình này hoàn toàn được xử lý dưới tầng Rust (Vectorized execution), đảm bảo tốc độ cực cao và không gặp hiện tượng thắt cổ chai như xử lý từng dòng.
- **Gate 2 (Silver -> Gold - Business Modeling):** Thuộc lãnh địa của **dbt (dbt-duckdb)**. dbt đảm nhận quản lý sự phụ thuộc (DAG dependency) giữa các bảng và thực hiện các Business Rules testing. Tầng này sử dụng DuckDB engine để xử lý SQL nhanh chóng.
- *Cần sửa các câu chữ trong `00_Manifesto` và `02_Storage` để làm rõ sự phân tách này.*

### ✅ 2. Củng cố Kiến trúc Hybrid (Intent Router + SQL Fallback) cho Mimir (Resolve Mâu thuẫn 2)
Để giải quyết mâu thuẫn giữa `04` và `10`, hệ thống áp dụng cơ chế **Hybrid (Lai)**, vừa bảo vệ tính toàn vẹn (Governance) vừa giữ được sự linh hoạt (Self-service). Mimir sẽ không gọi thẳng database mà luôn qua Superset.
- **Luồng xử lý chuẩn hóa của Mimir:**
  1. **Hiểu ý định & Duyệt tri thức (Tầng 4):** Người dùng đặt câu hỏi. Mimir duyệt đồ thị Obsidian để đối chiếu ý định.
  2. **Luồng Ưu tiên (Happy Path - Có sẵn Metric):** Nếu câu hỏi liên quan đến chỉ số cốt lõi (KPI, Doanh thu...), Mimir hoạt động như một **Intent Router**. Nó tìm thấy Metric đã khai báo sẵn, sau đó gọi API (Tool Calling) truyền tham số để Superset tính toán. Điều này đảm bảo Source of Truth luôn chính xác 100%.
  3. **Luồng Linh hoạt (Ad-hoc Query - Fallback SQL):** Nếu câu hỏi mang tính chất khám phá ngẫu hứng mà đội Data chưa làm sẵn Metric, Mimir kích hoạt khả năng **Text-to-SQL**. Nó tự viết lệnh SQL thô dựa vào định nghĩa (Metadata) trên Obsidian, sau đó đẩy câu lệnh này qua API SQL Lab của Superset.
  4. **An toàn bảo mật tuyệt đối:** Ở cả 2 luồng, Mimir luôn gửi request qua Superset kèm theo JWT Token của người dùng. Superset sẽ tự động bọc luật Row-Level Security (RLS) vào truy vấn trước khi thực thi trên DuckDB, đảm bảo AI không bao giờ bypass được ranh giới bảo mật.

---

## PHẦN 4: KIỂM TOÁN KIẾN TRÚC & LÝ DO TỪ CHỐI CÁC OLAP HẠNG NẶNG (CLICKHOUSE)

Trong quá trình thiết kế, bài toán **Truy cập đồng thời (High Concurrency)** khi nhúng DuckDB vào Superset đã được mổ xẻ kỹ lưỡng. Tuy nhiên, hệ thống quyết định **NÓI KHÔNG** với các OLAP Server hạng nặng như ClickHouse, dựa trên 3 lập luận thực tiễn sau:

### 1. Phân bổ lưu lượng người dùng (Traffic Distribution) thực tế
- **Luồng Sale (Đám đông):** Hàng trăm người dùng truy vấn qua Zalo Bot (Mimir). Các truy vấn này rất nhỏ, thường chỉ trả về 1 con số hoặc vài chục dòng (Point-queries). DuckDB xử lý trong chớp mắt, không gây áp lực RAM.
- **Luồng Back-office (Thiểu số):** Chỉ có khoảng chục máy tính tại văn phòng (C-level, Kế toán) sử dụng Dashboard nặng. Theo Benchmark thực tế, DuckDB Embedded hoàn toàn gánh vác mượt mà 10 truy vấn nặng cùng lúc (tốn < 0.8 giây và ~400MB RAM).

### 2. Sức mạnh của Tiền tổng hợp (dbt Pre-aggregation)
- Người dùng không bao giờ truy vấn trực tiếp vào bảng Raw 50 triệu dòng. Ở Gate 2, `dbt` đã tổng hợp sẵn dữ liệu thành các bảng OBT (One-Big-Table) tại Lớp Gold. DuckDB ở Superset chỉ việc đọc các file Parquet siêu nhỏ đã được làm sạch, triệt tiêu rủi ro OOM (Out of memory).

### 3. Redis Cache - Giải pháp hoàn hảo thay thế ClickHouse
Thay vì tốn 4GB - 16GB RAM để duy trì một cụm ClickHouse nhằm giải quyết I/O Bottleneck khi nhiều người mở chung một Dashboard, hệ thống dùng **Redis Cache (50MB - 100MB RAM)** bọc ngoài Superset:
- Bản chất Dashboard tạo ra hàng tá truy vấn SQL (Query Bomber) mỗi lần tải trang, nhưng dữ liệu Lớp Gold thường chỉ cập nhật theo Batch (Ngày/Giờ). 
- Redis sẽ lưu lại Dataframe của người mở Dashboard đầu tiên. Hàng chục truy vấn sau đó sẽ lấy thẳng từ RAM của Redis (0.01 giây) mà DuckDB không hề phải nhúc nhích.
- **Kết luận:** Redis đóng vai trò là "Lá chắn" bảo vệ đĩa cứng (Disk I/O) với chi phí phần cứng rẻ mạt, hoàn toàn đập tan nhu cầu phải sở hữu một CSDL cồng kềnh như ClickHouse.

### ✅ Rủi ro 2: Dung lượng xử lý của `n8n` (API Ingestion)
- **Đánh giá:** Ban đầu có lo ngại `n8n` sẽ bị tràn RAM nếu xử lý các API có payload khổng lồ (VD: 100.000 dòng/lần). Tuy nhiên, đối với quy mô thực tế của doanh nghiệp (SMEs/Mid-market), dữ liệu từ các nền tảng SaaS/Google Sheets hiếm khi đạt tới ngưỡng này. Do đó, `n8n` là một lựa chọn **cực kỳ xuất sắc và thực dụng** vì khả năng kéo thả nhanh, đáp ứng Agility.
- **Chiến lược khắc phục (Bảo vệ Postgres):** Để `n8n` chạy mượt mà nhiều năm không lỗi, **bắt buộc phải tắt tính năng lưu lịch sử chạy** (`Save Execution Progress = false`) trong cài đặt Workflow. Điều này ngăn `n8n` bơm hàng GB dữ liệu log rác vào Postgres, giữ cho DB luôn nhẹ và sạch đúng như Tuyên ngôn kiến trúc.

---

## PHẦN 5: CHIẾN LƯỢC CI/CD CHO DATA CONTRACTS (HỢP ĐỒNG DỮ LIỆU)

Data Contract trong hệ thống Yggdrasil không chỉ là lý thuyết mà là các chốt chặn vật lý. Để đảm bảo tính toàn vẹn của dữ liệu từ nguồn đến đích, việc tích hợp CI/CD cho Data Contract cần được tổ chức thành 2 giai đoạn:

### 1. CI/CD Thời điểm phát triển (Build-Time / Pull Request)
Mục tiêu là kiểm tra xem các thay đổi cấu trúc mã nguồn có phá vỡ Hợp đồng Dữ liệu hay không trước khi được gộp (Merge) vào nhánh Production.
- **Lưu trữ tập trung:** Mọi định nghĩa Data Contract (cấu trúc Schema mong muốn của Polars, file YAML của dbt tests) phải được lưu trữ trong Git Repository.
- **CI Pipeline (Tự động kiểm tra):** Khi có một Pull Request (PR) thay đổi cấu trúc bảng hoặc công thức tính:
  - Github Actions (hoặc Gitlab CI) sẽ khởi tạo một môi trường DuckDB/Polars tạm thời (Ephemeral Environment).
  - Bơm một tập dữ liệu mẫu (Dummy Data) vào môi trường này.
  - Chạy các lệnh `dbt test` và kịch bản `Polars filter`. Nếu có lỗi vi phạm Data Contract (VD: Xóa nhầm cột `revenue`, đổi kiểu dữ liệu `id` từ chuỗi sang số), CI sẽ báo đỏ (Fail) và chặn không cho phép Merge PR.

### 2. CI/CD Thời điểm vận hành (Runtime Enforcement & DLQ)
Dù CI/CD đã test kỹ, nhưng ở môi trường thực tế (Production), Upstream (bên cung cấp dữ liệu API/Database nguồn) có thể đơn phương thay đổi cấu trúc (Schema Drift) mà không báo trước.
- **Dead Letter Queue (DLQ):** Khi luồng Airflow chạy, nếu Polars (Gate 1) phát hiện các dòng dữ liệu vi phạm cấu trúc (Null ở các trường bắt buộc, sai định dạng ngày tháng):
  - KHÔNG làm sập toàn bộ Pipeline (Tránh việc mất luôn dữ liệu đúng).
  - Tách các dòng vi phạm đó ra và đẩy vào một thư mục riêng trên MinIO gọi là **Dead Letter Queue (Thùng rác kiểm duyệt)**.
  - Các dòng đúng vẫn được đẩy lên Lớp Silver.
- **Alerting (Báo động):** Ngay khi có dữ liệu rơi vào DLQ, hệ thống tự động bắn cảnh báo (Alert) qua Zalo/Slack cho Data Engineer kèm theo "Bằng chứng vi phạm hợp đồng" (Chỉ rõ dòng nào sai, sai ở trường nào) để yêu cầu đối tác/dev sửa lỗi.
