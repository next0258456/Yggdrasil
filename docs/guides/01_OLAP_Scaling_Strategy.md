# Hướng dẫn 01: Lộ trình Mở rộng Hệ thống (Scalability Path) - Từ DuckDB, Redis đến ClickHouse

## 1. Triết lý Mở rộng (The Scaling Philosophy)
Trong giới Data Engineering, một "chân lý" thường bị lạm dụng là: *"Khi dữ liệu lớn lên hoặc lượng người dùng tăng cao, phải triển khai ngay các hệ thống phân tán khổng lồ như ClickHouse hay Snowflake"*. Sự vội vã này thường dẫn đến chi phí hạ tầng (Infrastructure Cost) và nợ kỹ thuật (Technical Debt) khổng lồ cho các doanh nghiệp SME.

Kiến trúc Yggdrasil từ chối sự lãng phí này. Hệ thống được thiết kế theo một **Lộ trình nâng cấp 3 Giai đoạn (3-Phase Evolution)**, vắt kiệt từng giọt hiệu năng của Single-Node trước khi buộc phải tiến hóa lên kiến trúc Phân tán (Distributed).

---

## 2. Giai đoạn 1: DuckDB In-Memory & Parquet ("Bare-Metal")
Đây là hình thái nguyên thủy và cơ bản nhất của hệ thống phục vụ các truy vấn tức thời. 

### 2.1. Lách luật Concurrency của DuckDB
DuckDB mang tiếng xấu về Concurrency (Truy cập đồng thời) do tệp .duckdb áp dụng cơ chế khóa độc quyền (Write Lock). Yggdrasil "bypass" (bỏ qua) giới hạn này bằng cách phân tách hoàn toàn Lưu trữ và Tính toán:
- **Lưu trữ tĩnh:** Dữ liệu được lưu dưới dạng Parquet (định dạng Read-only). Hệ điều hành cho phép vô số tiến trình đọc tệp Parquet mà không cần cơ chế Khóa.
- **Tính toán phi trạng thái:** Mỗi Gunicorn Worker của Superset tự khởi tạo một phiên bản DuckDB In-Memory độc lập (duckdb.connect(':memory:')), đọc tệp Parquet, tính toán rồi giải phóng RAM ngay lập tức (Stateless Compute).

### 2.2. Giải mã Hiệu năng (OS Page Cache & Vectorized)
- Tận dụng **OS Page Cache**: Khi User 1 truy vấn, hệ điều hành nạp 300MB Parquet từ ổ cứng lên RAM. Từ User 2 đến 10, dữ liệu thực chất được đọc thẳng từ RAM (Memory-mapped I/O) với tốc độ ánh sáng.
- Bằng chứng thực nghiệm (Benchmark): 10 luồng (Workers) truy vấn đồng thời 20 triệu bản ghi (300MB) chỉ mất **1.49 giây** và tiêu tốn tổng cộng **471 MB RAM** (Trung bình 47MB/Worker).

---

## 3. Giai đoạn 2: Lá chắn Redis Cache (The Shield)
Dù DuckDB xử lý dữ liệu xuất sắc, hệ thống giao diện BI (Superset) lại sinh ra một bài toán khác ở tầng Ứng dụng: **Hiệu ứng Query Bomber (Dội bom truy vấn)**.

### 3.1. Hiệu ứng Query Bomber
Một Dashboard quản trị thường chứa 20 biểu đồ. Khi 10 người dùng mở Dashboard cùng lúc (Vào giờ họp buổi sáng), hệ thống phải hứng chịu: 10 Users x 20 Charts = 200 Truy vấn SQL đồng thời. Thay vì mua máy chủ to hơn để chịu trận I/O Spike, Yggdrasil chèn thêm một lớp **Redis Cache**.

### 3.2. Chặn đứng Query Bomber bằng Cache
- **Người dùng tiên phong:** Khi User đầu tiên mở Dashboard, DuckDB thực thi 20 câu SQL mất khoảng 2-3 giây. Superset ngay lập tức nạp kết quả (JSON) vào bộ nhớ RAM của Redis, với thời gian sống (TTL) bằng thời gian cập nhật Batch (VD: 1 giờ).
- **Lá chắn kích hoạt:** Đối với 9 Users mở sau, Superset nhận diện trùng lặp và bốc thẳng dữ liệu từ Redis trả về mặt UI trong **0.01 giây**. DuckDB và Ổ cứng máy chủ hoàn toàn nằm im (Zero I/O).
- **Lợi ích kinh tế:** Chỉ tốn ~50MB RAM nuôi Redis, hệ thống đã chặn đứng hoàn toàn rủi ro sập Server, kéo dài tuổi thọ của kiến trúc DuckDB thêm 1-3 năm mà không cần nâng cấp hạ tầng.

---

## 4. Giai đoạn 3: Điểm gãy và Sự trỗi dậy của ClickHouse (The Endgame)
Bản thiết kế này sòng phẳng thừa nhận: DuckDB + Redis không phải là viên đạn bạc (Silver Bullet) cho mọi bài toán. Khả năng mở rộng chiều dọc (Vertical Scaling) có giới hạn vật lý của nó.

Yggdrasil sẽ chính thức triệu hồi **ClickHouse** bước vào kiến trúc (Thay thế động cơ DuckDB) CHỈ KHI hệ thống chạm 2 "Điểm gãy" sau:

1. **Lượng truy vấn ngẫu hứng (Ad-hoc) siêu lớn:** Khi User không xem Dashboard có sẵn (để ăn Redis Cache) mà tự kéo thả, Filter dữ liệu (Explore) liên tục với hàng trăm người cùng lúc, khiến CPU và RAM của máy chủ cạn kiệt.
2. **Quy mô Dữ liệu Khủng & Yêu cầu Real-time:** Khi bảng OBT vượt ngưỡng 100GB-500GB khiến OS Page Cache quá tải (Trượt bộ nhớ/Cache Thrashing), HOẶC nghiệp vụ yêu cầu dữ liệu phải Real-time đến từng giây (Không thể Cache bằng Redis).

**Kết luận:** Thay vì đi đường tắt tốn kém, Lộ trình 3 Giai đoạn (DuckDB $\to$ Redis $\to$ ClickHouse) của Yggdrasil đảm bảo tính thực dụng tối đa: Bào cạn kiệt giá trị của máy chủ Single-Node hiện tại trước khi chi trả đồng Dollar đầu tiên cho công nghệ Phân tán.
