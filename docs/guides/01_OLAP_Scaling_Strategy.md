# Hướng dẫn 01: Lộ trình Mở rộng Hệ thống (Scalability Path) - Từ DuckDB, Redis đến ClickHouse

## 1. Triết lý Mở rộng (The Scaling Philosophy)
Trong kỹ thuật dữ liệu (Data Engineering), việc triển khai sớm các hệ thống phân tán (như ClickHouse, Snowflake) khi quy mô dữ liệu chưa đạt ngưỡng thường dẫn đến lãng phí tài nguyên hạ tầng và gia tăng nợ kỹ thuật (Technical Debt).

Kiến trúc Yggdrasil được thiết kế theo **Lộ trình nâng cấp 3 Giai đoạn (3-Phase Evolution)**. Nguyên tắc cốt lõi là tối ưu hóa triệt để hiệu năng của kiến trúc Single-Node trước khi chuyển đổi sang kiến trúc Phân tán (Distributed).

---

## 2. Giai đoạn 1: Tối ưu Hóa Lớp Truy vấn (DuckDB & Iceberg)
Giai đoạn 1 tập trung giải quyết các bài toán về hiệu năng và quản lý Metadata tại lớp lưu trữ nội bộ (Single-Node) để phục vụ cho nhu cầu phân tích.

### 2.1. Xử lý giới hạn truy cập đồng thời (Concurrency Bottleneck)
DuckDB áp dụng cơ chế khóa độc quyền (Write Lock) cấp độ tệp. Khi Superset thiết lập kết nối đến tệp vật lý (`duckdb:////app/data/duckdb.db`), xử lý đồng thời từ nhiều Gunicorn Workers sẽ dẫn đến xung đột khóa (Conflicting lock).

**Giải pháp:** Phân tách hoàn toàn Lưu trữ (Storage) và Tính toán (Compute).
- Khai báo SQLAlchemy URI trên Superset: **`duckdb:///:memory:`**
- Thay vì truy xuất một tệp cơ sở dữ liệu chung, mỗi Gunicorn Worker tự khởi tạo một phiên bản DuckDB ảo (In-Memory) độc lập. Dữ liệu được truy vấn trực tiếp từ các tệp Parquet/Iceberg định dạng Read-only, loại bỏ hoàn toàn cơ chế khóa.

### 2.2. Hạn chế trong định tuyến Metadata (Metadata Routing)
Khi hệ thống nâng cấp từ tệp Parquet thô sang chuẩn **Apache Iceberg**, việc truy xuất gặp thách thức trong việc định tuyến tệp `.metadata.json`.
- *Vấn đề quét dữ liệu (Directory Scanning):* Nếu cấu hình DuckDB tự động suy đoán phiên bản Iceberg (`unsafe_enable_version_guessing = true`), thao tác quét thư mục S3/MinIO sẽ gây cạn kiệt tài nguyên mạng (Throttling) dưới tải cao.
- *Giải pháp quá độ (Workaround):* Hệ thống ban đầu sử dụng Jinja Macro trên Superset để truy vấn cơ sở dữ liệu Postgres (JDBC Catalog) nhằm lấy đường dẫn S3 tĩnh. Dù giải quyết được độ trễ, phương pháp này tạo ra lỗ hổng kiến trúc (Abstraction Leak), khiến tầng BI (Superset) bị phụ thuộc vào logic của tầng Data.

### 2.3. Chuẩn hóa kiến trúc với Bifrost Proxy (Iceberg REST Catalog)
Để khắc phục triệt để lỗ hổng kiến trúc ở bước 2.2 mà không phải rước sự nặng nề của các runtime JVM (như Apache Polaris), **Bifrost Proxy** (viết bằng Golang + Embedded DuckDB) được triển khai làm thành phần cốt lõi của Giai đoạn 1.
- **Chiến lược phân tách Đọc/Ghi:** Bifrost Proxy tiếp nhận luồng ghi qua chuẩn Iceberg REST, sau đó tự động đồng bộ (stream) metadata sang **Native DuckLake Catalog** lưu trong PostgreSQL.
- **Truy vấn cực tốc:** DuckDB trong Superset kết nối trực tiếp vào Native DuckLake thông qua tài khoản an toàn `ducklake_reader`:
  `ATTACH 'ducklake:postgres:dbname=polaris host=postgres port=5432 user=ducklake_reader password=reader_password' AS lakehouse ...;`
  giúp bypass hoàn toàn chi phí I/O phân tích manifest JSON/Avro của Iceberg, đưa độ trễ truy vấn về mức dưới 1 giây mà không ngốn RAM (< 300MB).

---

## 3. Giai đoạn 2: Tối ưu Tầng Ứng dụng với Redis Cache
Sau khi Giai đoạn 1 hoàn thiện, Lớp Dữ liệu đã đạt hiệu năng tối ưu. Tuy nhiên, hệ thống cần xử lý rủi ro từ phía người dùng cuối tại Tầng Ứng dụng.

### 3.1. Hiện tượng quá tải truy vấn (Query Bomber)
Một Dashboard quản trị điển hình chứa khoảng 20 biểu đồ. Khi 10 người dùng tải Dashboard cùng lúc, hệ thống phải xử lý đồng thời 200 truy vấn SQL độc lập. Để bảo vệ Lớp Dữ liệu khỏi các đợt tăng tải đột biến (I/O Spike), Yggdrasil triển khai **Redis Cache**.

### 3.2. Cơ chế Bộ đệm (Caching Mechanism)
- **Truy vấn lần đầu (Cache Miss):** Khi người dùng đầu tiên truy cập, chuỗi xử lý (Superset $\to$ Bifrost Proxy $\to$ DuckDB) thực thi trong khoảng dưới 1 giây. Kết quả (JSON) ngay lập tức được lưu trữ vào RAM của Redis.
- **Truy vấn lặp lại (Cache Hit):** Đối với các người dùng tiếp theo, Superset truy xuất dữ liệu trực tiếp từ Redis trong **0.001 giây**. Lớp Cơ sở dữ liệu bên dưới hoàn toàn không chịu tải.

**Cấu hình kỹ thuật (`superset_config.py`):**
```python
from cachelib.redis import RedisCache

DATA_CACHE_CONFIG = {
    'CACHE_TYPE': 'RedisCache',
    'CACHE_DEFAULT_TIMEOUT': 86400, # TTL: 24 giờ
    'CACHE_KEY_PREFIX': 'superset_data_cache_',
    'CACHE_REDIS_URL': 'redis://redis:6379/1'
}
```

---

## 4. Giai đoạn 3: Mở rộng ngang với ClickHouse (The Endgame)
Kiến trúc thiết kế xác định rõ: Cụm `Bifrost Proxy + DuckDB + Redis` không thể đáp ứng mọi tình huống vô hạn. Hệ thống sẽ tiến hóa sang Giai đoạn 3 (Sử dụng hệ thống phân tán **ClickHouse**) chỉ khi chạm 2 "Điểm gãy" kỹ thuật:

1. **Tải phân tích phi cấu trúc (Ad-hoc Queries) siêu lớn:** Khi lượng lớn người dùng thao tác trực tiếp (Filter, Slice & Dice) liên tục. Cơ chế Redis Cache mất tác dụng, toàn bộ tải tính toán dồn trực tiếp lên DuckDB (In-Memory).
2. **Quy mô dữ liệu vượt ngưỡng:** Khi bảng OBT (One Big Table) vượt giới hạn vật lý của OS Page Cache (100GB - 500GB) dẫn đến hiện tượng trượt bộ nhớ (Cache Thrashing), hoặc khi nghiệp vụ đòi hỏi truy vấn dữ liệu thời gian thực (Real-time Streaming) không cho phép độ trễ của Cache.

**Kết luận:** Lộ trình 3 Giai đoạn của Yggdrasil đảm bảo hiệu quả đầu tư tối đa (ROI). Hệ thống khai thác triệt để tiềm năng của máy chủ Single-Node trước khi dịch chuyển sang các giải pháp phân tán phức tạp và tốn kém hơn.
