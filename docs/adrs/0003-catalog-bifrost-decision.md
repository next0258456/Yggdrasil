# ADR 0003: Chuyển đổi quản lý Metadata sang chuẩn REST Catalog & Tự phát triển Bifrost Proxy

- **Trạng thái**: Đã phê duyệt (Approved)
- **Ngày quyết định**: 2026-10-10
- **Người ra quyết định**: Cong Anh
- **Tài liệu liên quan**: Thay thế một phần (Catalog Choice) của [ADR 0001](0001-tech-stack-selection.md).

## Bối cảnh (Context)
Tại thời điểm khởi tạo dự án (v0.1), [ADR 0001](0001-tech-stack-selection.md) đã thống nhất sử dụng **Postgres JDBC Catalog** làm công cụ quản lý Metadata cho Apache Iceberg. Quyết định này xuất phát từ mong muốn loại bỏ hoàn toàn các nền tảng dựa trên môi trường Java/JVM (như Hive Metastore) để tối ưu hóa bộ nhớ trên kiến trúc Single-Node, đồng thời tận dụng hệ sinh thái Postgres sẵn có.

Tuy nhiên, trong quá trình thực thi tại Tầng 3 (Serving Layer), khi kết nối Apache Superset và DuckDB vào Data Lake, hệ thống đã vấp phải những giới hạn kiến trúc nghiêm trọng:
1. **Thiếu hỗ trợ Native:** DuckDB không hỗ trợ đọc trực tiếp định dạng Iceberg thông qua giao thức JDBC Catalog.
2. **Khủng hoảng định tuyến (Metadata Routing):** Để DuckDB tìm được tệp `.metadata.json`, hệ thống buộc phải sử dụng một "Giải pháp quá độ" (Workaround): Sử dụng Jinja Macro bên trong Superset để kết nối thẳng vào Postgres, truy vấn đường dẫn vật lý trên S3, sau đó nối chuỗi URL này vào lệnh SQL cho DuckDB.
3. **Lỗ hổng trừu tượng (Abstraction Leak):** Giải pháp trên vi phạm nguyên tắc thiết kế các tầng. Lớp Trình diễn (BI Layer) bị ép buộc phải chứa logic xử lý đường dẫn vật lý của Lớp Dữ liệu. Đồng thời, toàn bộ các tác nhân (Ingestion, BI) đều yêu cầu quyền truy cập trực tiếp qua cổng 5432 của Cơ sở dữ liệu Postgres, tiềm ẩn rủi ro bảo mật khổng lồ.

## Quyết định & Lập luận (Decision & Rationale)

- **Quyết định**: 
  1. Khai tử phương thức giao tiếp trực tiếp qua Postgres JDBC Catalog. Áp dụng chuẩn **Iceberg REST Catalog** làm giao thức quản trị Metadata duy nhất cho toàn bộ hệ thống.
  2. Bác bỏ giải pháp tình thế dùng **Apache Polaris** (do chạy nền Java/Quarkus tốn 500MB - 1GB RAM, phá vỡ lời thề Zero-JVM). Hệ thống chính thức tự phát triển và triển khai **Bifrost Proxy** – một Iceberg REST Catalog siêu nhẹ viết bằng **Golang + Embedded DuckDB Engine**.
  3. Cơ sở dữ liệu Postgres hiện tại được giữ lại nhưng bị giáng cấp xuống làm Backend lưu trữ trạng thái ngầm (State Store) cho Bifrost Proxy.

- **Lập luận bảo vệ quyết định (Rationale)**:
  1. **Khôi phục Lời thề "Zero-JVM" & Tối ưu Tài nguyên Tuyệt đối:**
     - Loại bỏ hoàn toàn sự hiện diện của Java/JVM trên Single-Node. Bifrost Proxy viết bằng Golang biên dịch ra file nhị phân tĩnh (Native Binary), nhúng trực tiếp DuckDB In-process qua CGO.
     - Mức tiêu thụ tài nguyên cực thấp: Bộ nhớ RAM **< 300MB (Hard Limit)** khi đóng gói Docker.
     - Tốc độ phản hồi vượt bậc: Cold Start `< 15ms`, Ping trung bình `< 2ms`, và Tail Latency `< 10ms` (vượt trội hoàn toàn so với mức tải nặng nề của Apache Polaris).
  2. **Chuẩn hóa Giao thức Ghi (The Iceberg REST Standard):**
     - Bifrost Proxy tuân thủ 100% Iceberg REST OpenAPI Catalog Specification (`/v1/oauth/tokens`, `/v1/namespaces/{ns}/tables/{table}` cho cả metadata query lẫn Compare-And-Swap commit).
     - Cho phép các công cụ Ingestion chuẩn mở (Redpanda Native Iceberg Sink, PyIceberg, Spark) tự do cào dữ liệu, ghi file Parquet và commit metadata qua REST mà không đòi hỏi viết custom pipeline.
  3. **Chiến lược "Treo đầu dê Iceberg, bán thịt chó DuckLake" (The Rosetta Stone Strategy):**
     - **Vòng ngoài (The Trickster - Ingestion):** Tiếp nhận luồng ghi Iceberg REST từ Redpanda/PyIceberg, cập nhật con trỏ metadata Iceberg để đảm bảo tính mở và khả năng tương thích hệ sinh thái.
     - **Vòng trong (The Core Engine - Storage Sync):** Bifrost Proxy nhúng DuckDB trích xuất manifest và đồng bộ tức thì sang **Native DuckLake Catalog** (lưu trữ trong PostgreSQL).
     - **Tầng Trình diễn (Serving Path - Superset/DuckDB):** DuckDB trong Superset **KHÔNG** đọc qua giao thức Iceberg REST chậm chạp, mà cắm thẳng vào Native DuckLake:
       ```sql
       ATTACH 'ducklake:postgres:dbname=polaris host=postgres port=5432 user=ducklake_reader password=reader_password' 
       AS lakehouse (DATA_PATH 's3://lakehouse/bronze/', OVERRIDE_DATA_PATH true, READ_ONLY true);
       ```
       Nhờ đó, tốc độ truy vấn phân tích đạt ngưỡng mili-giây (Sub-second), tận dụng triệt để năng lực File Pruning và Column Statistics mà không tốn chi phí parse manifest JSON/Avro.
  4. **Kiến trúc Khép kín (Zero Trust Data Layer):**
     - Bifrost Proxy hoạt động như một Stateless API Gateway. Che giấu hoàn toàn cổng 5432 của Postgres và thông tin S3 Credentials khỏi mạng bên ngoài.

## ⚖️ Hậu quả & Đánh đổi (Consequences & Trade-offs)

- **Nhận lại (Lợi ích Kiến trúc & Hạ tầng):**
  - **Giữ trọn vẹn lời hứa Zero-JVM:** Giữ đúng tinh thần tối giản Single-Node của ADR 0001 mà không phải nhân nhượng cho bất kỳ runtime Java nào.
  - **Độ trễ và Băng thông tối ưu:** Giảm độ trễ giao tiếp xuống mức micro/mili-giây, giải phóng RAM quý giá cho các tác vụ phân tích nặng của DuckDB và Polars.
  - **Bảo vệ ranh giới kiến trúc:** Trả lại sự trong sạch cho Lớp Trình diễn (Superset) và Lớp Dữ liệu (Iceberg), triệt tiêu các thủ thuật chắp vá Jinja macro cũ.
- **Trả giá (Gánh nặng Bảo trì Mã nguồn):**
  - Thay vì dùng một giải pháp Turnkey có sẵn của cộng đồng như Polaris, đội ngũ kỹ thuật phải tự sở hữu và bảo trì codebase Golang của Bifrost Proxy (xử lý concurrency lock, Goroutine backpressure, quản lý CGO memory giữa Go và DuckDB).
  - Tuy nhiên, với phạm vi nghiệp vụ Single-Node và bộ testsuite E2E hoàn chỉnh, chi phí bảo trì này hoàn toàn nằm trong tầm kiểm soát và mang lại ROI vượt trội so với việc nuôi cụm JVM.
