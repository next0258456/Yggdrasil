# 🏗️ Lớp Lưu Trữ Hồ Dữ Liệu (Storage Layer & Lakehouse)

Tài liệu này quy định kiến trúc vật lý và chiến lược quản lý dữ liệu tại **Tầng 2** của nền tảng Yggdrasil. Đây là lớp bền vững (Persistent Layer), nơi chứa toàn bộ tài sản dữ liệu của doanh nghiệp dưới dạng Data Lakehouse, với mục tiêu: **Chi phí lưu trữ rẻ nhất (Object Storage)** nhưng mang lại **hiệu năng truy vấn ngang ngửa Data Warehouse truyền thống**.

---

## 1. Phân Trách Nhiệm Lưu Trữ & Quản Trị (Storage & Governance)

Để đảm bảo khả năng mở rộng và bảo mật tuyệt đối, Tầng 2 chia cắt rõ ràng ba thành phần: Lưu trữ vật lý, Quản trị siêu dữ liệu (Metadata), và Lưu trữ trạng thái ngầm.

### 1.1. MinIO (Hồ Dữ Liệu - Object Storage)
- **Vai trò:** Đóng vai trò lưu trữ vật lý cốt lõi, thay thế Amazon S3 / Google Cloud Storage cho môi trường On-Premise/Local.
- **Dữ liệu được phép lưu:** Các tệp dữ liệu thô (Raw Data), tệp dữ liệu phân tích định dạng `Parquet`, và các tệp cấu trúc `.metadata.json` của chuẩn Apache Iceberg.
- **Quy tắc:** Mọi tương tác đọc/ghi phân tích của Tầng 3 (DuckDB) hoặc các hệ thống Ingestion (Spark/Redpanda) đều phải nhắm thẳng vào MinIO thông qua giao thức S3 (S3 API).

### 1.2. Trung tâm Quản trị Metadata (REST Catalog)
- **Vai trò:** Đóng vai trò "Nhạc trưởng" (Stateless API Gateway) tuân thủ nghiêm ngặt chuẩn **Iceberg REST Catalog**. *(Hệ thống sử dụng **Bifrost Proxy** – REST Catalog siêu nhẹ viết bằng Golang + Embedded DuckDB làm công cụ thực thi)*.
- **Cơ chế hoạt động:** 
  - **Luồng Ghi (Write):** Các hệ thống Ingestion (ví dụ: Redpanda) sau khi ghi tệp Parquet lên MinIO sẽ gửi HTTP POST đến REST Catalog (`http://<REST_ENDPOINT>:8080`) để khai báo phiên bản metadata mới nhất.
  - **Luồng Đọc (Read):** Đối với các Client bên ngoài cần đọc chuẩn Iceberg, Proxy trả về đường dẫn tệp `.metadata.json` hiện hành. **Riêng đối với Engine Phân tích nội bộ (DuckDB / Superset):** Hệ thống bypass hoàn toàn chi phí parse Iceberg manifest bằng cách đọc trực tiếp qua **Native DuckLake Catalog** (kết nối PostgreSQL với role chỉ đọc `ducklake_reader`) để đạt tốc độ truy vấn Sub-second.
- **Lợi ích kiến trúc:** Độc lập hoàn toàn với Engine phân tích. Cung cấp khả năng bảo mật phân quyền (RBAC) và cấp phát Token truy cập (Credential Vending) mà không để lộ thông tin hạ tầng gốc.

### 1.3. PostgreSQL (Cơ sở Dữ liệu Nội Bộ - Internal Backend)
- **Vai trò:** Hệ quản trị trạng thái (State Management) nội bộ.
- **Quy định thiết kế (Zero Direct Access):** Khác với kiến trúc cũ (phơi cổng 5432 làm JDBC Catalog), Postgres giờ đây bị "giấu" hoàn toàn khỏi các Engine phân tích. Nó lùi về phía sau làm backend tĩnh để lưu trữ:
  - Bản ghi trạng thái (Namespaces, Table pointers, Roles) cho riêng thằng REST Catalog.
  - Trạng thái chạy Job của Airflow (Metadata DB).
  - Cấu hình hệ thống, IAM của n8n.
- **Quy tắc:** Cấm tuyệt đối việc các hệ thống phân tích (như DuckDB) kết nối trực tiếp vào Postgres bằng giao thức JDBC để đọc/ghi dữ liệu nghiệp vụ.

---

## 2. Quy Hoạch Data Lakehouse (Medallion Architecture)

Cấu trúc Bucket trong MinIO được quy hoạch nghiêm ngặt theo mô hình 3 lớp (Huy chương), cấm các luồng dữ liệu nhảy cóc (Ví dụ: Cấm Tầng 1 ghi thẳng vào Gold).

### 🥉 Lớp Bronze (Raw Data / Landing Zone)
- **Mục đích:** Hứng dữ liệu thô nguyên bản từ Tầng Ingestion nhanh nhất có thể. Không biến đổi dữ liệu.
- **Định dạng file:** `Parquet` (Ưu tiên), `JSON` (Cho luồng API).
- **Chiến lược Partition:** Bắt buộc chia thư mục theo thời gian lấy dữ liệu (Ingestion Time) để dễ gỡ lỗi.

### 🥈 Lớp Silver (Cleaned & Conformed Data)
- **Mục đích:** Dữ liệu đã được **Python (Polars) làm sạch** (Lọc NULL, chuẩn hóa kiểu ngày tháng). Đây là Single-Source-of-Truth cho Data Scientists và Analysts.
- **Định dạng vật lý:** `Parquet`. **Định dạng bảng (Table Format):** `Apache Iceberg` (Bắt buộc) - Quản lý bởi REST Catalog.
- **Tính năng:** Cung cấp cơ chế Time-Travel để quay lui phiên bản dữ liệu nếu có lỗi logic từ luồng Ingestion.

### 🥇 Lớp Gold (Aggregated / One-Big-Table)
- **Mục đích:** Phục vụ trực tiếp cho BI Dashboards và cung cấp Context cho hệ thống AI (RAG). Bảng ở đây thường được Flatten (Trải phẳng) thành OBT bởi **dbt (Gate 2)** để tránh JOIN phức tạp lúc truy vấn.
- **Định dạng vật lý:** `Parquet`. **Định dạng bảng (Table Format):** `Apache Iceberg` (Quản lý bởi REST Catalog).

---

## 3. Bảo Trì & Dọn Dẹp (Data Vacuuming)

Bản chất của kiến trúc Iceberg (như MVCC) là không xóa file Parquet cũ ngay lập tức khi chạy lệnh `UPDATE/DELETE` hoặc Ghi đè (Overwrite), nhằm phục vụ tính năng quay ngược thời gian (Time Travel). Điều này dẫn đến nguy cơ đầy ổ đĩa MinIO.

**Quy tắc Vận hành:**
- Phải có một Job trong Airflow chạy định kỳ để thực thi lệnh `VACUUM` hoặc thao tác dọn dẹp các Snapshots đã quá hạn (Expire Snapshots) trên các bảng Iceberg thông qua REST API của Catalog.
- Lệnh này sẽ xóa các file Parquet mồ côi (Orphan files) không còn nằm trong cây Metadata, trả lại dung lượng vật lý cho đĩa cứng.
