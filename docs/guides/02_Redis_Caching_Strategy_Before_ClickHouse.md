# Hướng dẫn 02: Chiến lược dùng Redis Cache làm lá chắn chặn họng ClickHouse

## 1. Vấn đề thực tiễn: Hiệu ứng "Query Bomber"
Dù kiến trúc DuckDB In-Memory + Parquet giải quyết cực tốt bài toán truy vấn song song (Đọc Hướng dẫn 01), hệ thống BI (Superset) vẫn tồn tại một rủi ro tiềm ẩn ở cấp độ Giao diện người dùng (UI), được gọi là hiệu ứng **Query Bomber (Dội bom truy vấn)**.

- **Bản chất của Dashboard:** Một Dashboard quản trị thông thường không chỉ có 1 biểu đồ. Nó thường chứa từ 10 đến 20 biểu đồ (Charts) khác nhau.
- **Vấn đề:** Khi một người dùng (User A) mở Dashboard này lên, Superset không gửi 1 truy vấn, mà nó bắn **ĐỒNG THỜI 20 câu truy vấn SQL** xuống tầng Database.
- **Hiệu ứng số nhân:** Nếu vào lúc 8:00 sáng, có 10 nhân sự phòng ban cùng đăng nhập và mở cái Dashboard đó. Chỉ trong 1 giây, hệ thống phải hứng chịu: 10 Users x 20 Charts = 200 Truy vấn SQL đồng thời.

Nếu để 200 truy vấn này đánh thẳng vào ổ cứng (Disk I/O) hoặc CPU của máy chủ, dù là DuckDB hay bất kỳ Database nào cũng sẽ bị nghẽn cục bộ (Spike). Giải pháp thông thường của giới Data là: *"Hệ thống quá tải rồi, phải chi tiền mua cụm ClickHouse hoặc Snowflake để gánh dội bom thôi!"*

## 2. Giải pháp Cứu cánh (The Lifesaver): Redis Cache
Yggdrasil từ chối việc ném tiền qua cửa sổ cho ClickHouse chỉ để giải quyết một khoảnh khắc "dội bom" vài giây. Thay vào đó, chúng ta thiết lập một chốt chặn bộ nhớ đệm (Caching Layer) bằng **Redis** ngay bên trong Apache Superset.

### Cơ chế hoạt động (How it works)
Lớp dữ liệu Gold của chúng ta thường chỉ được cập nhật theo Batch (Mỗi giờ, hoặc mỗi ngày 1 lần qua Airflow). Do đó, dữ liệu trên Dashboard là **Dữ liệu tĩnh (Static Data) trong khoảng thời gian giữa 2 lần cập nhật**.

1. **Người dùng tiên phong (The Pioneer):** Khi User A (người mở sớm nhất lúc 8:00) truy cập Dashboard, Superset sẽ đẩy 20 câu SQL xuống DuckDB tính toán. Quá trình này mất khoảng 2-3 giây.
2. **Lưu trữ kết quả (Caching):** Ngay khi DuckDB trả về kết quả (dạng JSON hoặc Dataframe), Superset sẽ lưu ngay 20 kết quả này vào RAM của Redis, gắn kèm với mã Hash của câu SQL và thiết lập thời gian sống (TTL - Time to live) bằng đúng thời gian chờ đến lần chạy Airflow tiếp theo.
3. **Lá chắn kích hoạt (The Shield):** Khi User B, C... cho đến User 10 mở Dashboard, Superset nhận ra các câu SQL này giống hệt câu SQL của User A. Nó **KHÔNG ĐẨY** xuống DuckDB nữa, mà bốc thẳng kết quả từ RAM của Redis trả về giao diện.
4. **Tốc độ:** Thời gian phản hồi từ Redis chỉ mất **0.01 giây**. CPU và ổ cứng (Disk I/O) của máy chủ hoàn toàn nằm im không hề nhúc nhích.

## 3. Lợi ích Kinh tế (ROI) & Độ trễ kiến trúc
Việc chèn thêm một lớp Redis (chỉ tiêu tốn vỏn vẹn khoảng 50MB - 100MB RAM) mang lại giá trị chiến lược khổng lồ:

- **Kéo dài tuổi thọ của Single-Node:** Redis giúp kiến trúc DuckDB + Parquet sống sót qua các đợt "Traffic Spike" nội bộ. Nó trì hoãn thời điểm doanh nghiệp bắt buộc phải đập đi xây lại hạ tầng để lên ClickHouse thêm từ 1 đến 3 năm.
- **Tối ưu chi phí tuyệt đối:** Nuôi một Container Redis tốn chưa tới 1 USD/tháng tiền điện và RAM. Trong khi duy trì một cụm ClickHouse tốn từ vài trăm đến hàng nghìn USD chi phí Cloud và nhân sự bảo trì.

## 4. Kết luận
Chỉ khi nào **Dữ liệu phân tích quá lớn (Hàng trăm GB)** khiến DuckDB quét quá lâu cho dù là người dùng tiên phong, HOẶC **Yêu cầu Real-time tuyệt đối** (dữ liệu biến động từng giây, không thể Cache), thì lúc đó Yggdrasil mới chính thức thừa nhận giới hạn và cấp phép cho ClickHouse bước vào kiến trúc. 
Còn đối với 90% bài toán báo cáo B2B, **DuckDB + Redis** là một cặp khiên - giáo bất khả chiến bại.
