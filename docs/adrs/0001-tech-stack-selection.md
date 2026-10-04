# ADR 0001: Lựa chọn Tech Stack cốt lõi cho Yggdrasil v0.1

- **Trạng thái**: Đã phê duyệt (Approved)
- **Ngày quyết định**: 2026-10-03
- **Người ra quyết định**: Cong Anh

## Bối cảnh (Context)
Hệ thống Big Data truyền thống dựa trên Hadoop/Spark quá cồng kềnh, tốn kém chi phí duy trì cụm máy chủ và không phù hợp với triết lý "Tối giản" của Yggdrasil v0.1. Cần một giải pháp tinh gọn, tối ưu trên Single-Node nhưng vẫn đảm bảo khả năng mở rộng (Lakehouse) và bảo mật tuyệt đối. 

Dưới đây là các quyết định (Lý do đi chợ) giải thích chi tiết cho 3 mảng công nghệ cốt lõi nhất cấu thành nên nền tảng.

## Quyết định & Lập luận (Decision & Rationale)

### 1. Mâm Storage & Format: Apache Iceberg + Postgres JDBC Catalog (Loại bỏ Delta Lake)
- **Quyết định**: Sử dụng định dạng Apache Iceberg thay cho Delta Lake. Quản lý siêu dữ liệu (Metadata) thông qua Postgres JDBC Catalog thay vì Hive Metastore.
- **Lập luận**:
  - **Tại sao Iceberg?** Iceberg là chuẩn thiết kế hướng Table-Format đích thực, hoàn toàn phi tập trung (engine-agnostic). Trong khi Delta Lake vẫn mang hơi hướm "Vendor Lock-in" (phụ thuộc nhiều vào hệ sinh thái Databricks/Spark). Iceberg cho phép cắm đa dạng Compute Engine (DuckDB, Polars) vào đọc một cách trơn tru.
  - **Tại sao Postgres JDBC Catalog?** Hive Metastore yêu cầu chạy môi trường Java/JVM nặng nề và dễ lỗi. Sử dụng Postgres làm JDBC Catalog biến hệ thống trở nên siêu gọn nhẹ. Quan trọng nhất là **Tối ưu nguồn lực vận hành (Operational Efficiency)**: Các quản trị viên cơ sở dữ liệu (DBA) đã quá quen thuộc với hệ sinh thái Postgres. Do đó, có thể dễ dàng bàn giao (handover) công tác quản trị, sao lưu (backup) và gỡ lỗi mà không phát sinh thêm chi phí đào tạo công nghệ mới.
  - **Tính bất tử của hệ thống (Disaster Recovery):** Áp dụng chiến lược cứu hộ 2 lớp cực kỳ kiên cố nếu máy chủ vật lý bốc cháy:
    - *Lớp 1 (Database Level)*: Kích hoạt cơ chế **Postgres WAL Archiving**, liên tục đẩy file log (WAL) sang ổ cứng/MinIO để có thể khôi phục lại toàn vẹn cơ sở dữ liệu Postgres bất cứ lúc nào (Point-in-Time Recovery).
    - *Lớp 2 (Format Level)*: Trong trường hợp Postgres bị hủy diệt vĩnh viễn, ta tận dụng sức mạnh phi tập trung của Iceberg. Vì Iceberg lưu toàn bộ file cấu trúc (`.metadata.json`) ngay trên MinIO cùng với dữ liệu Parquet, ta chỉ cần dựng 1 máy chủ Postgres mới tinh, gọi lệnh `register_table` trỏ vào MinIO là hệ thống Catalog sẽ "hồi sinh" nguyên vẹn từ cõi chết.

### 2. Mâm Compute: Polars + DuckDB (Khai tử Apache Spark & Trino)
- **Quyết định**: Sử dụng Polars (LazyFrame) làm động cơ ETL (Bronze $\to$ Silver) và DuckDB làm động cơ truy vấn phân tích chuyên trách tại tầng Gold.
- **Lập luận**:
  - **Triết lý Single-Node Big Data**: Với tập dữ liệu dưới ngưỡng 500GB - 1TB, cụm phân tán (Spark) là một sự lãng phí tài nguyên khủng khiếp.
  - **Polars**: Được viết bằng Rust, Polars khai thác tối đa đa lõi CPU/RAM, tốc độ xử lý nhanh gấp nhiều lần Spark ở quy mô vừa, chịu trách nhiệm xử lý chuyển đổi dữ liệu nặng (Heavy-lifting ETL).
  - **DuckDB & Quản trị RAM**: DuckDB bị giới hạn cấu hình chỉ được phép truy vấn tại tầng Gold (Data Marts/OBT). Kết quả kiểm thử thực tế (Benchmark trên môi trường SSD Samsung 980 Pro NVMe 4.0) cho thấy sức mạnh tối ưu I/O khủng khiếp của Single-Node:
    - **Bare-metal EL (Disk-to-Disk thuần):** DuckDB cắm trực tiếp vào Postgres, kéo 6.8 triệu bản ghi và ghi xuống file Parquet chỉ mất **1.8 giây** (Vắt kiệt 100% băng thông ổ cứng, Zero-overhead).
    - **Orchestrated ETL (Thực chiến):** Khi bọc qua bộ điều phối Airflow (chịu thêm thuế Network, Spin-up worker, và đẩy lên MinIO qua S3 API), toàn bộ luồng hoàn tất trong **9.6 giây**.
    Với hiệu năng này, bài toán tràn RAM trên kiến trúc Single-Node được giải quyết triệt để, đồng thời tốc độ kết xuất báo cáo BI (Superset) đạt ngưỡng mili-giây. Hiệu năng thực tế khi Deploy sẽ phụ thuộc tuyến tính vào thông số IOPS của ổ cứng đích.

### 3. Mâm Orchestration: n8n kết hợp Airflow 3 (Dual-Engine)
- **Quyết định**: Áp dụng mô hình điều phối kép (Dual-Engine Orchestration). Tách biệt rạch ròi hai vùng lãnh thổ: n8n đảm nhận Giao tiếp ngoại vi (External Integrations) và Airflow 3 đóng vai trò Điều phối nội bộ (Internal Orchestrator).
- **Lập luận**:
  - **Tại sao phải phân tách làm hai (Sự tiến hóa kiến trúc)?** Ban đầu, nền tảng được thiết kế thuần túy chỉ dùng Airflow điều phối mọi thứ, và n8n chỉ dùng làm nền tảng Chatbot AI. Tuy nhiên, việc ép Airflow xử lý các luồng Polling API hay lắng nghe Webhook dẫn đến việc sinh ra các tác vụ treo (Long-running tasks), giam cầm các Worker Container liên tục một cách lãng phí và kém tối ưu. Phân tầng điều phối là giải pháp triệt để để gỡ bỏ nút thắt này.
  - **Tại sao chọn n8n (Bộ ngoại giao)?** n8n xử lý các tác vụ Event-driven, Webhook và Polling tối ưu tài nguyên hơn rất nhiều so với Airflow. Hơn thế nữa, giao diện Low-code trực quan của nó cho phép các phòng ban phi kỹ thuật (Non-tech departments) dễ dàng tự cấu hình và tích hợp các nguồn dữ liệu của họ.
  - **Tại sao chọn Airflow 3 (Loại bỏ Dagster/Prefect/Cron)?** Mặc dù có nhiều đối thủ hiện đại, Airflow vẫn duy trì vị thế Tiêu chuẩn công nghiệp. Sự lựa chọn này dựa trên 3 trụ cột: (1) Nguồn nhân sự dồi dào (dễ tuyển người duy trì), (2) Giao diện giám sát (UI) quen thuộc, trực quan, và (3) Khả năng "Cloud-ready" - có thể dễ dàng chuyển dịch toàn bộ luồng sang các dịch vụ Managed Cloud (như AWS MWAA hay GCP Cloud Composer) bất cứ lúc nào mà không cần đập đi viết lại.
  - **Giao thức Handoff n8n $\to$ Airflow (Điều phối theo Nhiệt độ Dữ liệu - SLA Driven):** Việc n8n kích hoạt Airflow hoàn toàn phụ thuộc vào "độ nóng" của dữ liệu:
    - *Dữ liệu nguội (Batch T+1)*: n8n kéo dữ liệu thả vào MinIO (Landing Zone). Airflow sẽ tự động chạy theo lịch (Cron) để xử lý mẻ lớn (Batch) bằng Polars vào giờ thấp điểm.
    - *Dữ liệu nóng (Near Real-time / 5 phút)*: n8n thả dữ liệu vào MinIO, ngay lập tức gọi REST API kích hoạt (Event-driven Trigger) Airflow chạy ngay lập tức Parameterized DAG để cập nhật báo cáo nóng cho sếp. Dù nóng hay nguội, Data Payload tuyệt đối không được truyền qua API mà phải giao tiếp qua MinIO.

### 4. Mâm BI & Security Gateway: Apache Superset (Zero-Trust)
- **Quyết định**: Sử dụng Apache Superset không chỉ làm công cụ vẽ biểu đồ (BI Dashboard) truyền thống, mà đóng vai trò là "Cửa khẩu dữ liệu bảo mật" (Security Gateway) duy nhất cho toàn bộ hệ thống, đặc biệt là phục vụ AI.
- **Lập luận**:
  - **Free API Backend & JWT**: Việc tự code một API Backend riêng (bằng FastAPI/NodeJS) để Bot chọc vào Lakehouse là lãng phí. Superset có sẵn REST API cực mạnh với cơ chế xác thực JWT. AI Bot (Mimir) chỉ cần cầm Token đến gọi API, hết hạn là mất quyền.
  - **Row-Level Security (RLS)**: Bức tường thép bảo vệ dữ liệu. Khi AI xin dữ liệu, Superset áp đặt luật RLS để che giấu hoàn toàn dữ liệu nhạy cảm (Data-Blind AI). Bot chỉ thấy được những gì nó được phép thấy.
  - **Semantic Layer hợp nhất**: Cả Con người (xem Dashboard) và AI (gọi API) đều đi qua lớp Semantic của Superset. Tránh tuyệt đối tình trạng "Người tính ra một số, Bot tính ra một số khác".

### 5. Giao thức AI: Mimir Bot (LLM Semantic Router & Data-Blind)
- **Quyết định**: Định hình Mimir Bot là một **"LLM Semantic Router"** hoạt động theo nguyên lý "Mù dữ liệu" (Data-Blind), thay vì một Agent tự trị.
- **Lập luận**:
  - **Data-Blind Text-to-SQL (Viết Code nhưng Bịt mắt)**: Mimir Bot VẪN ĐƯỢC CẤP QUYỀN tư duy, tự do viết câu lệnh SQL, tạo Template hoặc điền tham số (Parameters). **Tuy nhiên**, nó bị "bịt mắt" hoàn toàn khỏi dữ liệu thực. Não bộ của LLM chỉ được cung cấp Cấu trúc bảng (Schema) và Siêu dữ liệu (Metadata) để sinh ra luồng xử lý. Nó tuyệt đối không được cấp quyền `SELECT` để nhìn thấy dữ liệu thô.
  - **Deterministic Execution (Thực thi tất định)**: LLM đóng vai trò người "viết kịch bản" (Router/Template Generator). Còn người "diễn" (Thực thi SQL, áp dụng RLS, render kết quả) là hệ thống Engine phía sau (Superset/DuckDB). Điều này loại bỏ hoàn toàn rủi ro AI bịa số liệu (Hallucination) hoặc làm rò rỉ dữ liệu nhạy cảm.

#
## ⚖️ Hậu quả & Đánh đổi (Consequences & Trade-offs)
*Trong kiến trúc hệ thống, không có viên đạn bạc (No Silver Bullet). Mua được "Hiệu năng" và "Sự tối giản" thì nền tảng phải chấp nhận trả giá bằng 5 nhược điểm chí mạng sau:*

1. **Giới hạn Scale ngang (The Vertical Scaling Trap)**
   - *Mua:* Tốc độ xử lý sấm sét trên Single-Node, né được sự cồng kềnh, tốn kém của JVM/Cluster.
   - *Trả:* Khi dữ liệu chạm ngưỡng chục Terabytes, ta không thể "cắm thêm máy" (Scale-out) như Spark/Hadoop, mà bắt buộc phải đốt tiền nâng cấp Server vật lý mạnh hơn (RAM/CPU to hơn).

2. **Đứt gãy luồng truy vết (Dual-Engine Complexity)**
   - *Mua:* Tối ưu tài nguyên tuyệt đối, Airflow không bị giam cầm bởi các luồng Polling chờ đợi vì đã có n8n gánh vác ở ranh giới ngoại vi.
   - *Trả:* Khi một Pipeline thất bại, Data Engineer phải phân thân đi truy vết (Trace log) ở cả 2 nền tảng: Check n8n xem đã tải file vào MinIO thành công chưa, sau đó mới qua Airflow mò xem Polars chết ở dòng nào.

3. **Vấn nạn "Mảnh vỡ file nhỏ" (The Small Files Problem)**
   - *Mua:* Khả năng trích xuất dữ liệu liên tục thành các mẻ nhỏ (Mini-batch) qua n8n để đáp ứng SLA.
   - *Trả:* Khi Iceberg bị băm thành hàng ngàn file Parquet vài KB, việc ép Polars quét (Scan) lượng file khổng lồ trên Single-Node sẽ gây phân mảnh RAM cực nặng và bóp nghẹt CPU. Hệ thống bắt buộc phải gánh thêm chi phí tài nguyên để chạy các luồng Compaction (Gom file) định kỳ.

4. **Thiết kế Độc đạo (No Reverse Data Flow)**
   - *Mua:* Loại bỏ hoàn toàn rủi ro xung đột ghi đồng thời (Concurrency Writes) và bảo vệ tuyệt đối tính toàn vẹn dữ liệu. Dữ liệu chỉ chảy một chiều duy nhất từ Bronze $\to$ Silver $\to$ Gold $\to$ BI.
   - *Trả:* Triệt tiêu sự linh hoạt. Khi người dùng Business phát hiện sai số trên báo cáo (Superset), họ tuyệt đối không thể sửa hoặc ghi đè (Write-back) trực tiếp vào Lakehouse. Mọi sai sót bắt buộc phải quay về sửa tận gốc ở hệ thống Nguồn (Source) và chờ Pipeline chạy lại từ đầu.

5. **Khấu hao hiệu năng giao thức (Object Storage Overhead)**
   - *Mua:* Dùng chuẩn S3 API (MinIO) ngay trên máy Local để đảm bảo Code luôn ở trạng thái "Cloud-Ready", dễ dàng bốc lên AWS S3 mà không bị khóa chặt (Lock-in) vào ổ cứng vật lý.
   - *Trả:* Dù MinIO chạy tại Local, việc Polars/DuckDB đọc file phải đi qua giao thức HTTP/S3 API thay vì đọc thẳng từ đĩa (Local NVMe) sẽ gây hao phí CPU cho việc đóng/mở gói mạng (Serialization). Tốc độ I/O thực tế sẽ bị suy hao một khoản nhất định so với truy xuất File System thuần túy.

