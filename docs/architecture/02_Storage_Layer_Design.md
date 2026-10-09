# 🏗️ Lớp Lưu Trữ Hồ Dữ Liệu (Storage Layer & Lakehouse)

Tài liệu này quy định kiến trúc vật lý và chiến lược quản lý dữ liệu tại **Tầng 2** của nền tảng Yggdrasil. Đây là lớp bền vững (Persistent Layer), nơi chứa toàn bộ tài sản dữ liệu của doanh nghiệp dưới dạng Data Lakehouse, với mục tiêu: **Chi phí lưu trữ rẻ nhất (Object Storage)** nhưng mang lại **hiệu năng truy vấn ngang ngửa Data Warehouse truyền thống**.

---

## 1. Phân Trách Nhiệm Lưu Trữ (Postgres vs MinIO)

Để tránh hiện tượng "phình to" Database dẫn đến chi phí bảo trì đắt đỏ, Tầng 2 chia cắt hoàn toàn vai trò của CSDL Quan hệ và Hệ thống lưu trữ File:

### 1.1. PostgreSQL (Siêu dữ liệu - Metadata Storage)
- **Vai trò:** Hệ quản trị trạng thái (State Management).
- **Dữ liệu được phép lưu:** 
  - Trạng thái chạy Job của Airflow (Metadata DB).
  - Cấu hình hệ thống, thông tin User, phân quyền (IAM) của n8n.
  - Sổ tay ghi chép (Watermark) của các tiến trình CDC.
- **Quy tắc:** Cấm tuyệt đối việc lưu trữ dữ liệu phân tích (Analytical Data), Log hệ thống dạng text, hoặc lịch sử giao dịch kinh doanh vào Postgres. Postgres phải được giữ ở trạng thái "nhỏ, nhẹ, và cực nhanh".

### 1.2. MinIO (Hồ Dữ Liệu - Object Storage)
- **Vai trò:** Đóng vai trò thay thế Amazon S3 / Google Cloud Storage cho môi trường On-Premise/Local.
- **Dữ liệu được phép lưu:** Toàn bộ dữ liệu nghiệp vụ, bản Snapshot của Database nguồn, lịch sử CDC, và các bảng báo cáo phục vụ BI (Metabase).
- **Quy tắc:** Mọi tương tác đọc/ghi phân tích của Tầng 3 (DuckDB) đều phải nhắm thẳng vào MinIO thông qua giao thức S3 (S3 API).

---

## 2. Quy Hoạch Data Lakehouse (Medallion Architecture)

Cấu trúc Bucket trong MinIO được quy hoạch nghiêm ngặt theo mô hình 3 lớp (Huy chương), cấm các luồng dữ liệu nhảy cóc (Ví dụ: Cấm Tầng 1 ghi thẳng vào Gold).

### 🥉 Lớp Bronze (Raw Data / Landing Zone)
- **Mục đích:** Hứng dữ liệu thô nguyên bản từ Tầng Ingestion (API Webhook, DuckDB Snapshot, Redpanda CDC) nhanh nhất có thể. Không biến đổi dữ liệu.
- **Định dạng file:** `Parquet` (Ưu tiên), `JSON` (Cho luồng API).
- **Chiến lược Partition:** Bắt buộc chia thư mục theo thời gian lấy dữ liệu (Ingestion Time) để dễ gỡ lỗi.
  - *Ví dụ:* `s3://datalake/bronze/erp_sales/year=2026/month=10/day=05/`
- **Vòng đời (Lifecycle):** Dữ liệu ở Bronze có thể được thiết lập chính sách tự động xóa (TTL) sau 30-90 ngày để tiết kiệm ổ cứng, vì dữ liệu này có thể lấy lại từ DB nguồn.

### 🥈 Lớp Silver (Cleaned & Conformed Data)
- **Mục đích:** Dữ liệu đã được **Python (Polars) làm sạch ở Gate 1** (Lọc NULL, chuẩn hóa kiểu ngày tháng, ép kiểu). Các dòng dữ liệu vi phạm cấu trúc (Data Contract) sẽ bị ném vào **Dead Letter Queue (DLQ)** thay vì đẩy vào Silver. Đây là Single-Source-of-Truth cho Data Scientists và Analysts.
- **Định dạng vật lý:** `Parquet`. **Định dạng bảng (Table Format):** `Apache Iceberg` (Bắt buộc).
- **Chiến lược Partition:** Chia theo thời gian nghiệp vụ (Business Time - ví dụ: `created_at`) để tối ưu hóa truy vấn lọc thời gian.
- **Tính năng:** Cung cấp cơ chế Time-Travel để quay lui phiên bản dữ liệu nếu có lỗi logic từ luồng Ingestion.

### 🥇 Lớp Gold (Aggregated / One-Big-Table)
- **Mục đích:** Phục vụ trực tiếp cho BI Dashboards (Metabase) và cung cấp Context cho hệ thống AI (RAG). Bảng ở đây thường được Flatten (Trải phẳng) thành OBT bởi **dbt (Gate 2)** để tránh JOIN phức tạp lúc truy vấn. Lớp này là Data Contracts cuối cùng phục vụ BI/AI.
- **Định dạng vật lý:** `Parquet`. **Định dạng bảng (Table Format):** `Apache Iceberg` (Để đồng nhất hệ sinh thái).
- **Tần suất cập nhật:** Được Airflow lên lịch tính toán (Aggregated) định kỳ từ lớp Silver (Hourly/Daily).

---

## 3. Bảo Trì & Dọn Dẹp (Data Vacuuming)

Bản chất của kiến trúc Iceberg (như MVCC) là không xóa file Parquet cũ ngay lập tức khi chạy lệnh `UPDATE/DELETE` hoặc Ghi đè (Overwrite), nhằm phục vụ tính năng quay ngược thời gian (Time Travel). Điều này dẫn đến nguy cơ đầy ổ đĩa MinIO.

**Quy tắc Vận hành:**
- Phải có một Job trong Airflow chạy định kỳ (Ví dụ: Chủ nhật hàng tuần) để thực thi lệnh `VACUUM` hoặc thao tác dọn dẹp các Snapshots đã quá hạn (Expire Snapshots) trên các bảng Iceberg.
- Lệnh này sẽ xóa các file Parquet mồ côi (Orphan files) không còn nằm trong cây Metadata, trả lại dung lượng vật lý cho đĩa cứng.
