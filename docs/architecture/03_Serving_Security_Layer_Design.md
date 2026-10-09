# Tầng 3: Thiết Kế Lớp Trình Diễn & Bảo Mật (Serving & Security Layer)

## 1. Tổng Quan Tầng 3
Tầng 3 (Serving & Security) đóng vai trò là điểm chạm cuối cùng của luồng dữ liệu trước khi đến tay người dùng cuối (End-users) hoặc các tác nhân AI ở Tầng 5. Trách nhiệm cốt lõi của tầng này không chỉ là cung cấp giao diện báo cáo (Dashboards) mà còn phải kiểm soát chặt chẽ quyền truy cập dữ liệu (Data Governance) ở cấp độ dòng (Row-Level Security).

Nền tảng được chọn để đảm nhận Tầng 3 là **Apache Superset**, kết hợp cùng sức mạnh truy vấn tại chỗ của **DuckDB**.

## 2. Kiến Trúc "Zero-JVM" Bằng Cơ Chế Embedded OLAP
Thay vì triển khai các hệ thống truy vấn phân tán nặng nề như Trino hay Presto (vốn yêu cầu cấu hình JVM phức tạp và tài nguyên lớn), kiến trúc Yggdrasil áp dụng triết lý **"Embedded OLAP"**.

### 2.1. Tích Hợp DuckDB Engine vào Superset
- **Nguyên lý hoạt động:** Apache Superset được cấu hình để cài đặt thêm thư viện `duckdb-engine` (SQLAlchemy dialect cho DuckDB). Nhờ đó, Superset có thể sử dụng DuckDB như một engine truy vấn nội tại (In-process).
- **Luồng truy vấn:**
  1. Người dùng mở Dashboard trên Superset.
  2. Superset kích hoạt DuckDB Engine bên trong chính container của nó.
  3. DuckDB sử dụng thư viện `httpfs` và `iceberg` để đọc trực tiếp các tệp Parquet/Iceberg từ MinIO (Tầng 2) thông qua kết nối S3 API.
  4. DuckDB xử lý dữ liệu (Vectorized execution) và trả kết quả về bộ nhớ của Superset để render biểu đồ.
- **Ưu điểm:** Loại bỏ hoàn toàn chi phí bảo trì một cụm OLAP độc lập. Khai thác tối đa tốc độ của DuckDB trên một Single-Node.

### 2.2. Chuỗi Kết Nối (Connection String) Tiêu Chuẩn
Để kết nối Superset với MinIO thông qua DuckDB, hệ thống sử dụng Connection String SQLAlchemy như sau:
```text
duckdb:////app/superset_home/superset_duckdb.db
```
Và cấu hình "Engine Parameters" trên giao diện Superset để DuckDB tải các phần mở rộng cần thiết:
```json
{
  "connect_args": {
    "preload_extensions": ["httpfs", "iceberg"],
    "config": {
      "s3_endpoint": "minio:9000",
      "s3_access_key_id": "admin",
      "s3_secret_access_key": "password",
      "s3_use_ssl": "false",
      "s3_url_style": "path"
    }
  }
}
```

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

## 4. Cơ Chế Bộ Đệm Phục Vụ (Caching)
Để giảm tải cho mạng và MinIO, đặc biệt khi các biểu đồ được xem lại nhiều lần bởi nhiều người dùng, Superset được cấu hình hai lớp Cache:
1. **Metadata Cache:** Lưu trữ cấu trúc bảng (Schema), tên cột.
2. **Query Data Cache:** Lưu trữ kết quả (Dataframe) của các câu truy vấn phức tạp bằng Redis hoặc Caching nội bộ. Nếu một câu truy vấn tương đồng được gọi lại trong vòng 15 phút (có thể cấu hình), Superset sẽ trả kết quả trực tiếp từ Cache thay vì bắt DuckDB quét lại file Parquet từ MinIO.

## 5. Tổng Kết Kiến Trúc Tầng 3
Tầng 3 cung cấp một giải pháp BI (Business Intelligence) siêu tinh gọn. Bằng cách gộp chung Giao diện Trình diễn (Superset) và Động cơ Truy vấn (DuckDB) thành một khối duy nhất, hệ thống tiết kiệm được đáng kể tài nguyên RAM/CPU, đồng thời duy trì khả năng kiểm soát truy cập dữ liệu mạnh mẽ, tạo tiền đề hoàn hảo để phục vụ dữ liệu cho Tầng 4 (Metadata) và Tầng 5 (AI) tiếp theo.
