# Tầng 3: Thiết Kế Lớp Trình Diễn & Bảo Mật (Serving & Security Layer)

## 1. Tổng Quan Tầng 3
Tầng 3 (Serving & Security) đóng vai trò là điểm chạm cuối cùng của luồng dữ liệu trước khi đến tay người dùng cuối (End-users) hoặc các tác nhân AI ở Tầng 5. Trách nhiệm cốt lõi của tầng này không chỉ là cung cấp giao diện báo cáo (Dashboards) mà còn phải kiểm soát chặt chẽ quyền truy cập dữ liệu (Data Governance) ở cấp độ dòng (Row-Level Security).

Nền tảng được chọn để đảm nhận Tầng 3 là **Apache Superset**, kết hợp cùng sức mạnh truy vấn tại chỗ của **DuckDB** và cơ chế định tuyến từ **chuẩn REST Catalog**.

## 2. Kiến Trúc "Zero-JVM" Bằng Cơ Chế Embedded OLAP
Thay vì triển khai các hệ thống truy vấn phân tán nặng nề như Trino hay Presto (vốn yêu cầu cấu hình JVM phức tạp và tài nguyên lớn), kiến trúc Yggdrasil áp dụng triết lý **"Embedded OLAP"**.

### 2.1. Tích Hợp DuckDB Engine vào Superset
- **Nguyên lý hoạt động:** Apache Superset được cấu hình thư viện `duckdb-engine` (SQLAlchemy dialect cho DuckDB). Nhờ đó, Superset có thể sử dụng DuckDB như một engine truy vấn nội tại (In-process).
- **Loại bỏ xung đột (Concurrency Lock):** Thay vì kết nối vào tệp cơ sở dữ liệu dùng chung (`.db`), Superset được cấu hình bắt buộc sử dụng URI `duckdb:///:memory:`. Mỗi Gunicorn Worker của Superset sẽ tự vận hành một không gian bộ nhớ DuckDB độc lập, đảm bảo khả năng mở rộng hàng trăm kết nối đồng thời mà không bị khóa.

### 2.2. Cơ Chế Truy Vấn Tốc Độ Cực Đại Qua Native DuckLake (The DuckLake Engine)
Thay vì bắt DuckDB phải duyệt qua cây metadata JSON/Avro cồng kềnh của Iceberg (gây chậm trễ do I/O parse manifest), DuckDB bên trong Superset cắm trực tiếp vào **DuckLake Native Catalog** (do **Bifrost Proxy** âm thầm trích xuất và đồng bộ vào PostgreSQL).

- **Lệnh thiết lập môi trường (Initialization):** Trên giao diện cấu hình Database của Superset, DuckDB được nạp lệnh khởi tạo kết nối qua role chỉ đọc an toàn (`ducklake_reader`):
  ```sql
  ATTACH 'ducklake:postgres:dbname=polaris host=postgres port=5432 user=ducklake_reader password=reader_password' 
  AS lakehouse (DATA_PATH 's3://lakehouse/bronze/', OVERRIDE_DATA_PATH true, READ_ONLY true);
  ```
- **Luồng truy vấn (Query Flow):**
  1. Người dùng mở Dashboard trên Superset $\to$ Câu lệnh SQL tiêu chuẩn được phát đi (vd: `SELECT * FROM lakehouse.fmcg_sales`).
  2. DuckDB Engine đọc siêu dữ liệu tức thì từ các bảng DuckLake Catalog (`ducklake_data_file`, `ducklake_column`, `ducklake_snapshot`) trong PostgreSQL. Không tốn thời gian phân tích manifest JSON/Avro, DuckDB xác định chính xác danh sách file Parquet cần đọc và áp dụng Column Statistics để lọc file (File Pruning).
  3. DuckDB tải trực tiếp các tệp Parquet từ MinIO về bộ nhớ và thực thi truy vấn nội bộ (Vectorized execution) với tốc độ Sub-second.

## 3. Thiết Kế Cơ Chế Bảo Mật (Security & Governance)

Bảo mật ở Tầng 3 được chia làm hai cấp độ chính để đảm bảo an toàn dữ liệu khi cung cấp cho con người và AI.

### 3.1. Row-Level Security (RLS) - Phân Quyền Cấp Độ Dòng
Superset cung cấp tính năng RLS tích hợp sẵn. Hệ thống sẽ áp dụng các bộ lọc tự động dựa trên ngữ cảnh (Context) của người dùng đang đăng nhập.
- **Kịch bản áp dụng:** Một Dataset về "Doanh số FMCG toàn quốc" được chia sẻ chung.
- **Cấu hình RLS:**
  - `User = Giám đốc Vùng miền Bắc` $\rightarrow$ Superset tự động chèn thêm mệnh đề `WHERE region = 'North'` vào truy vấn DuckDB.
  - `User = Bot AI (Tầng 5)` $\rightarrow$ Chỉ được phép truy cập vào các bản ghi đã được gắn cờ `is_public = True` hoặc theo quyền hạn của người dùng đang chat với Bot.

### 3.2. Cấu Trúc Xác Thực (Authentication)
- Hệ thống hỗ trợ tích hợp SSO (Single Sign-On) qua OAuth2 (Google/Microsoft) cho nhân viên nội bộ.
- Đối với luồng API gọi từ Tầng 5 (n8n/AI Gateway), hệ thống sử dụng **JWT (JSON Web Token)**. Các tác nhân AI sẽ sử dụng Service Account với bộ quyền (Role) bị giới hạn nghiêm ngặt theo tiêu chuẩn Principle of Least Privilege.

## 4. Lá Chắn Bộ Đệm (Redis Cache) - Ngăn Chặn Query Bomber
Dù kiến trúc REST Catalog và DuckDB có khả năng truy xuất độc lập cực nhanh, việc hàng chục người dùng tải cùng một Dashboard (mỗi Dashboard chứa hàng chục biểu đồ) vẫn sẽ tạo ra nút thắt cổ chai cục bộ (I/O Spike) trên máy chủ Single-Node. Hệ thống giải quyết bằng lớp **Redis Cache** hoạt động như một lá chắn vòng ngoài:

1. **Metadata Cache:** Lưu trữ cấu trúc bảng (Schema), tên cột để tăng tốc độ phản hồi giao diện.
2. **Data Cache (Query Results):** Khi truy vấn phân tích lần đầu tiên được xử lý bởi DuckDB, kết quả (JSON) sẽ được Superset đóng băng và lưu trữ trực tiếp vào RAM của cụm Redis (TTL mặc định: 24 giờ). 
3. Kể từ người dùng thứ hai tải lại biểu đồ đó, REST API của Superset (được điều hướng qua Endpoint `/api/v1/chart/data`) sẽ xuất thẳng kết quả từ Redis trong chưa tới **0.001 giây**, vô hiệu hóa hoàn toàn tải tính toán (Zero Compute Overhead) đối với cụm DuckDB và Storage phía dưới.

## 5. Tổng Kết Kiến Trúc Tầng 3
Tầng 3 cung cấp một giải pháp BI (Business Intelligence) siêu tinh gọn. Bằng cách gộp chung Giao diện Trình diễn (Superset) và Động cơ Truy vấn (DuckDB) thành một khối duy nhất, kết hợp hoàn hảo với **chuẩn giao tiếp REST Catalog** và **Lá chắn Redis Cache**, hệ thống tiết kiệm được đáng kể tài nguyên RAM/CPU. Cấu trúc này không chỉ duy trì khả năng kiểm soát truy cập dữ liệu mạnh mẽ mà còn tạo tiền đề hoàn hảo để phục vụ dữ liệu cho Tầng 4 (Metadata) và Tầng 5 (AI) tiếp theo.
