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
- **Chiến lược:** Sử dụng **Config-Driven Ingestion Modes (Chế độ Trích xuất qua Cấu hình)**. Thay vì cố chấp áp dụng một mô hình duy nhất, Data Engineer sẽ bật/tắt Cờ (Feature Flag) để thích ứng với hạ tầng mạng và quy mô dữ liệu:

---

## Chi tiết Luồng Database Ingestion (Chế độ Cờ Bật/Tắt)

Dựa trên giới hạn Vật lý (Network Bandwidth) và dung lượng dữ liệu (Data Size), hệ thống áp dụng các cờ (Feature Flag) `SYNC_MODE` tương ứng:

### 🚩 Chế độ 1: `SYNC_MODE = 'FULL_SNAPSHOT_DIFF'` (Out-of-Core Batching)
- **Điều kiện kích hoạt:** 
  - Hệ thống Nguồn và Data Lake nằm chung mạng tốc độ cao (Ví dụ: Loopback, LAN 10Gbps+).
  - Dung lượng bảng ở mức Vừa đến Lớn (Lên tới **100 - 200 triệu bản ghi** đối với bảng liền khối, hoặc **Hàng tỷ bản ghi** nếu DB gốc đã chia Partition).
- **Cơ chế hoạt động:** 
  - Sử dụng **DuckDB Scanner** cắm trực tiếp vào DB Nguồn, cào phân vùng dữ liệu và ghi thẳng xuống đĩa thành file Parquet (Cơ chế Streaming).
  - Áp dụng công nghệ **Out-of-Core**: DuckDB sử dụng SQL `EXCEPT` hoặc `Hash Join` giữa Snapshot hiện tại và trước đó trực tiếp trên ổ cứng. (Theo Benchmark: Tính Diff 100M dòng mất ~8s, tiêu thụ < 300MB RAM).
  - **Tối ưu với Partitioning:** Nếu DB nguồn được cắt vách (Monthly/Daily Partition), DuckDB chỉ cần quét và tính Diff trên phân vùng "Hot Data" (Ví dụ: 5M dòng của tháng hiện tại), đưa thời gian xử lý xuống < 2s.
- **Ưu / Nhược điểm:** 
  - **Chi phí phần cứng:** Tiêu thụ tài nguyên theo dạng On-Demand (Chỉ dùng khi chạy Job). Theo Benchmark trên bảng 100 triệu dòng: Quá trình quét và tính Diff tiêu thụ tối đa ~250 MB RAM, hoàn thành trong ~40 giây, sau đó giải phóng toàn bộ tài nguyên. Thích hợp cho các máy chủ có cấu hình RAM giới hạn.
  - **Mức độ can thiệp:** Cắm trực tiếp và đọc, không yêu cầu cấu hình thêm trên Database nguồn (Không cần Replication Slot).
  - **Độ chính xác:** Đảm bảo toàn vẹn trạng thái dữ liệu tại thời điểm chụp (Bao gồm cả Hard Delete). File Parquet lưu tại Bronze có thể dùng làm Cold Backup.
  - **Nhược điểm (RPO > 0):** Quá trình đồng bộ phụ thuộc vào chu kỳ thời gian (Ví dụ: 30 phút/lần). Dữ liệu phát sinh giữa 2 chu kỳ chưa kịp đồng bộ sẽ bị mất nếu DB Nguồn gặp sự cố.

### 🚩 Chế độ 2: `SYNC_MODE = 'INCREMENTAL_CDC'` (Log-based Streaming)
- **Điều kiện kích hoạt:**
  - Hạ tầng mạng yếu, chi phí Egress Data cao.
  - Yêu cầu nghiệp vụ bắt buộc **Độ trễ bằng 0 (Real-time)** hoặc **Zero Data Loss**.
- **Cơ chế hoạt động (Debezium + Redpanda CDC):** 
  - Bật tính năng ghi log mức độ logic của Database Nguồn (`wal_level = logical`).
  - **Debezium:** Đóng vai trò là Connector cắm trực tiếp vào Database để hứng luồng sự kiện (Insert/Update/Delete) theo thời gian thực (Real-time).
  - **Redpanda:** Nền tảng Streaming (Kafka-compatible) làm lõi trung chuyển. Bằng cách kích hoạt tính năng **Native Iceberg Sink**, Redpanda sẽ tự động gộp (batch) và dump thẳng dữ liệu sự kiện xuống MinIO (định dạng Parquet/Iceberg) mà không cần bất kỳ script Python trung gian nào.
- **Ưu / Nhược điểm:**
  - **Mức độ an toàn dữ liệu (RPO = 0):** Giải quyết triệt để rủi ro mất dữ liệu, độ trễ tiệm cận Real-time. Hỗ trợ bắt được lịch sử của từng giao dịch (thay vì chỉ lấy trạng thái cuối cùng như Snapshot).
  - **Chi phí phần cứng:** Yêu cầu cấp phát bộ nhớ liên tục (Always-on). Cụm Debezium (JVM) và Redpanda (Seastar) yêu cầu phân bổ cố định khoảng 3GB - 4GB RAM duy trì 24/7 để làm bộ đệm streaming, bất kể lưu lượng dữ liệu hiện tại đang cao hay thấp.
  - **Nhược điểm:** Tăng độ phức tạp vận hành của hệ thống. Có rủi ro gây tràn dung lượng ổ cứng chứa WAL/Binlog trên Database nguồn nếu luồng tiêu thụ (Sink) bị gián đoạn hoặc ngắt kết nối.

---

## 3. Năng lực đọc trực tiếp của DuckDB Scanner

Để phục vụ chế độ `FULL_SNAPSHOT_DIFF`, DuckDB đóng vai trò là cỗ máy I/O tối thượng. Nhờ các **Scanner Extensions** được viết bằng C++, DuckDB không cần đi qua lớp ORM của Python, mà đọc trực tiếp vào Page Memory hoặc Binary Protocol của hệ quản trị cơ sở dữ liệu Nguồn:

1. **PostgreSQL (`postgres_scanner`):** Đọc song song (Parallel read) trực tiếp từ Postgres, bypass hoàn toàn giới hạn của `psycopg2`.
2. **MySQL (`mysql_scanner`):** Tương tự như Postgres, cắm thẳng vào MySQL để hốt data.
3. **SQLite (`sqlite_scanner`):** Đọc trực tiếp file `.sqlite` hoặc `.db` từ đĩa mà không cần khởi động engine SQLite.
4. **Parquet/CSV/JSON:** Đọc và truy vấn trực tiếp trên S3 (MinIO) không cần tải file về local.

*Lưu ý Quan trọng về Giới hạn Phần cứng (Hardware Bottleneck):*
- Sức mạnh I/O của DuckDB (đặc biệt là tính năng Out-of-Core) phụ thuộc **tuyến tính vào tốc độ (IOPS & Throughput) của ổ cứng**.
- **Lợi thế SSD/NVMe:** Benchmark 100 triệu dòng trong ~40s đạt được là nhờ băng thông khổng lồ của ổ SSD/NVMe (có thể lến tới hàng GB/s). Ở môi trường này, DuckDB "mượn" ổ cứng làm RAM cực kỳ hiệu quả.
- **Điểm chết HDD:** Nếu triển khai trên hạ tầng sử dụng ổ cứng cơ (HDD) hoặc Network Storage giá rẻ (Low IOPS), DuckDB sẽ bị thắt cổ chai (I/O Bound) trầm trọng. Lúc này, hiệu năng sẽ sụt giảm thê thảm, và bắt buộc phải dùng RAM để xử lý (In-Memory) hoặc chuyển sang dùng CDC Streaming (Xử lý trên RAM).

*Lưu ý Vận hành: Hiện tượng che dấu giới hạn vật lý (RAM Caching Effect):*
Trong quá trình vận hành thực tế và Benchmark, các Kỹ sư cần cẩn trọng với các "Ảo giác hiệu năng" do Bộ nhớ đệm (RAM) của Hệ điều hành và Database tạo ra:
1. **Biến thiên Tốc độ Trích xuất (Cold Cache vs Warm Cache):** Tốc độ hút dữ liệu từ DB nguồn có thể chênh lệch tới 40%. Nếu dữ liệu vừa được hệ thống truy xuất trước đó (Warm Cache), DB sẽ ném trực tiếp từ RAM sang DuckDB mà không chạm vào đĩa, tạo ra tốc độ trích xuất cực nhanh.
2. **Ảo giác OS Page Cache:** Khi hệ thống có lượng RAM nhàn rỗi lớn, OS (Linux/Windows) sẽ tự động nạp các file Parquet vừa được DuckDB ghi ra vào RAM. Khi DuckDB thực hiện tính Diff (Out-of-core), tốc độ thực tế đo được là tốc độ RAM, che giấu hoàn toàn sự chậm chạp của ổ cứng vật lý.
3. **Khuyến nghị:** Trong môi trường Production, khi Server phải chia sẻ RAM cho nhiều dịch vụ (N8n, Airflow, DB), OS Cache sẽ không đủ dung lượng để "đỡ đạn" cho ổ cứng. Lúc này, hiệu năng sẽ tụt về đúng giới hạn vật lý của đĩa. Do đó, **Không được dùng cấu hình RAM lớn để bù đắp cho ổ cứng HDD/Low-IOPS**, hạ tầng SSD/NVMe vẫn là quy chuẩn bắt buộc cho chế độ `FULL_SNAPSHOT_DIFF`.
