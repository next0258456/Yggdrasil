# 🏗️ Lớp Trích Xuất Dữ Liệu (Ingestion Layer) & Chiến Lược CDC

Tài liệu này quy định chi tiết cách hệ thống Yggdrasil trích xuất dữ liệu từ các Nguồn bên ngoài xuống Data Lake (Tầng Bronze). Dựa trên bản chất của Nguồn, lớp Ingestion được chia làm 2 luồng hoàn toàn biệt lập:

## Phân Luồng Ingestion (DB vs API)

### 1. Luồng API & Event Ingestion (Dành cho SaaS, Webhook, Google Sheets)
- **Công cụ phụ trách:** `n8n`
- **Đặc thù:** Giao tiếp với các hệ thống Cloud (CRM, ERP, Google Sheets) hoặc hứng dữ liệu Real-time.
- **Chiến lược:** 
  - Khắc phục các bài toán mà Database không có: Pagination (Phân trang), Rate-limiting (Giới hạn gọi API), và OAuth/Token Authentication.
  - `n8n` đóng vai trò là Cổng gác (API Gateway), tự động gọi API, hứng Webhook, và dump thẳng dữ liệu thô (Raw JSON/CSV) xuống MinIO (Bronze Layer) mà không cần viết code Python phức tạp.

### 2. Luồng Database Ingestion (DB to Lake)
- **Công cụ phụ trách:** `DuckDB` + `Airflow`
- **Đặc thù:** Kéo khối lượng dữ liệu khổng lồ (Bulk Load) từ các hệ quản trị CSDL quan hệ (Postgres, MySQL...).
- **Chiến lược:** Sử dụng **Config-Driven Ingestion Modes (Chế độ Trích xuất qua Cấu hình)**. Thay vì cố chấp áp dụng một mô hình duy nhất, Data Engineer sẽ bật/tắt Cờ (Feature Flag) để thích ứng với hạ tầng mạng:

---

## Chi tiết Luồng Database Ingestion (Chế độ Cờ Bật/Tắt)

Dựa trên giới hạn Vật lý (Network Bandwidth) và dung lượng dữ liệu (Data Size), Data Engineer sẽ cấu hình cờ (Feature Flag) `SYNC_MODE` tương ứng:

### 🚩 Chế độ 1: `SYNC_MODE = 'FULL_SNAPSHOT_DIFF'` (Chế độ Bạo lực học)
- **Điều kiện kích hoạt:** 
  - Hệ thống Nguồn và Data Lake nằm chung mạng tốc độ cao (Ví dụ: Loopback, LAN 10Gbps+).
  - Hoặc dung lượng bảng nhỏ (< 10 triệu bản ghi, ~150MB).
- **Cơ chế hoạt động:** 
  - Sử dụng **DuckDB Scanner** cắm trực tiếp vào DB Nguồn, cào toàn bộ bảng (Full Table) và ghi thẳng xuống ổ cứng thành file Parquet (Tốc độ có thể đạt ~2 giây cho 6.8 triệu dòng nếu dùng NVMe).
  - Dùng CPU của Data Lake để chạy `FULL OUTER JOIN` hoặc `EXCEPT` giữa Snapshot hôm nay và hôm qua nhằm tự chắt lọc ra các dòng Insert, Update, Delete.
- **Ưu điểm tối thượng:** 
  - **Zero-Touch:** Không cần động chạm bất kỳ cấu hình nào vào DB Nguồn (Không Index, không Replication Slot). Coi DB Nguồn như một nơi chứa data ngu ngốc.
  - **Độ chính xác 100%:** Tuyệt đối không bao giờ bị rớt data do lệch múi giờ hay mất kết nối giữa chừng như các giải pháp Watermark.

### 🚩 Chế độ 2: `SYNC_MODE = 'INCREMENTAL_CDC'` (Chế độ Tiết kiệm Băng thông)
- **Điều kiện kích hoạt:**
  - Hạ tầng mạng yếu (VPN 1Gbps, Cloud Network giới hạn băng thông), có tính phí Egress Data.
  - Dữ liệu phình to vượt ngưỡng (Chi phí kéo Full Load mất > 1 phút).
- **Cơ chế hoạt động:** 
  - Chuyển sang trích xuất Delta (Chỉ lấy phần dữ liệu mới thay đổi).
  - Yêu cầu cấu trúc lại hoặc can thiệp vào DB Nguồn. (Chi tiết xem tại Mục 3).

---

## 2. Năng lực đọc trực tiếp của DuckDB Scanner

Để phục vụ chế độ `FULL_SNAPSHOT_DIFF`, DuckDB đóng vai trò là cỗ máy I/O tối thượng. Nhờ các **Scanner Extensions** được viết bằng C++, DuckDB không cần đi qua lớp ORM của Python, mà đọc trực tiếp vào Page Memory hoặc Binary Protocol của hệ quản trị cơ sở dữ liệu Nguồn:

1. **PostgreSQL (`postgres_scanner`):** Đọc song song (Parallel read) trực tiếp từ Postgres, bypass hoàn toàn giới hạn của `psycopg2`.
2. **MySQL (`mysql_scanner`):** Tương tự như Postgres, cắm thẳng vào MySQL để hốt data.
3. **SQLite (`sqlite_scanner`):** Đọc trực tiếp file `.sqlite` hoặc `.db` từ đĩa mà không cần khởi động engine SQLite.
4. **Parquet/CSV/JSON:** Đọc và truy vấn trực tiếp trên S3 (MinIO) không cần tải file về local.

*Lưu ý: Sức mạnh I/O của DuckDB phụ thuộc tuyến tính vào IOPS của ổ cứng lưu trữ Nguồn. Nếu ổ cứng Nguồn là NVMe, tốc độ cào data sẽ nhanh tương đương tốc độ copy file nội bộ.*

---

## 3. Các Phương Án cho Chế Độ INCREMENTAL_CDC (Poor Man's CDC)

Khi hệ thống buộc phải bật cờ `INCREMENTAL_CDC`, việc chọn phương án nào dưới đây phụ thuộc vào kết quả đo đạc tải thực tế (Capacity Planning) của Database khách hàng:

### Option A: Đánh Index cột `updated_at` & Query thẳng Master DB (Watermarking)
- *Cách làm:* Airflow lưu lại mốc thời gian (Watermark) của lần chạy trước. Lần sau chạy câu lệnh `SELECT ... WHERE updated_at > mốc_cũ`.
- *Ưu điểm:* Code cực kỳ dễ, quen thuộc với mọi DE.
- *Nhược điểm:* **Index Write Penalty**. Ép DBA đánh index trên một cột biến động cao (updated_at) sẽ làm tăng tải Ghi (I/O) của DB Prod. Phải xử lý thủ công rủi ro "Late Commit" (Dữ liệu bị sót do độ trễ transaction).

### Option B: Query Watermark vào Read-Replica DB
- *Cách làm:* Giống Option A nhưng trỏ chuỗi kết nối sang con máy chủ phụ (Replica).
- *Ưu điểm:* Vẫn giữ được sự đơn giản của SQL. Bảo vệ Master DB tuyệt đối khỏi các rủi ro sập do Full Table Scan.
- *Nhược điểm:* Khách hàng phải tốn tiền duy trì DB Replica. Dữ liệu kéo về Lakehouse có thể bị trễ do `Replication Lag`. DB Master Nguồn vẫn phải gánh Write Penalty của cái Index `updated_at`.

### Option C: Postgres Logical Replication (Zero-Index CDC)
- *Cách làm:* Đỉnh cao của Data Engineering. Bật `wal_level = logical` trên DB Nguồn và dùng Python hút trực tiếp các sự kiện (Insert/Update/Delete) từ Replication Slot.
- *Ưu điểm:* **Không cần đánh Index, không Table Scan, không tốn tải Update của Master DB**. Bắt được cả lệnh Hard Delete. 
- *Nhược điểm:* Yêu cầu quyền Root/Admin của DB Nguồn. Rủi ro tràn ổ cứng DB Prod nếu luồng Airflow chết quá lâu (Slot không được xả, WAL phình to). Code xử lý giải mã WAL phức tạp hơn SQL thông thường.
