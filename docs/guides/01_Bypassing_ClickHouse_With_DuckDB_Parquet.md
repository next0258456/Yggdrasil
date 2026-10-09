# Guide 01: Lập luận Kiến trúc - Lách luật Concurrency của DuckDB để thay thế ClickHouse

## 1. Lời nói đầu: Cuộc đối đầu giữa Định kiến và Thực chiến
Trong giới Data Engineering, một "chân lý" luôn được truyền miệng: *"DuckDB chỉ dành cho Single-player (phân tích cá nhân), nếu muốn làm Dashboard cho nhiều người dùng (High Concurrency) thì bắt buộc phải dựng ClickHouse"*.

Kiến trúc Yggdrasil chính thức **bác bỏ** nhận định này đối với quy mô doanh nghiệp SME/Mid-market. Bằng cách thay đổi cơ chế tương tác giữa Compute (DuckDB) và Storage (Parquet), chúng ta hoàn toàn có thể "bypass" (bỏ qua) nhu cầu sử dụng ClickHouse mà vẫn đạt được hiệu năng tương đương, với chi phí hạ tầng giảm 90%.

## 2. Giải phẫu định kiến: Tại sao DuckDB bị chê là kém Concurrency?
DuckDB mang tiếng xấu về Concurrency (Truy cập đồng thời) là do người dùng lưu trữ dữ liệu vào định dạng tệp gốc của nó (tệp .duckdb). 
- Tệp .duckdb áp dụng cơ chế khóa độc quyền (Exclusive Lock) tương tự SQLite. 
- Khi một tiến trình (Process A) mở file .duckdb để đọc/ghi, nó khóa toàn bộ tệp. Nếu Process B (ví dụ: một User khác mở Dashboard) cố gắng truy vấn, nó sẽ bị từ chối với lỗi IO Error: Database is locked.

👉 **Kết luận:** Lỗi không nằm ở động cơ tính toán (Compute Engine) của DuckDB, mà lỗi nằm ở **Định dạng lưu trữ vật lý có tính năng Khóa (Stateful Storage)**.

## 3. Lời giải Yggdrasil: Kiến trúc "Máy xay sinh tố" (Stateless In-Memory)
Để lách luật giới hạn Concurrency, Yggdrasil áp dụng triết lý Decoupled Compute & Storage cực đoan:

1. **Storage (Iceberg/Parquet):** Dữ liệu Lớp Gold được lưu dưới dạng Apache Iceberg (thực chất là các tệp Parquet). Tệp Parquet là định dạng **Tĩnh (Read-only)**. Hệ điều hành (OS) cho phép vô số tiến trình đọc cùng một tệp Parquet mà không cần bất kỳ cơ chế Khóa (Lock) nào.
2. **Compute (In-Memory DuckDB):** Khi Superset (giao diện BI) nhận một câu truy vấn, nó không kết nối vào tệp .duckdb. Thay vào đó, mỗi Gunicorn Worker của Superset sẽ tự khởi tạo một "Lõi DuckDB Ảo" trên RAM bằng lệnh duckdb.connect(':memory:'). 
3. **Thực thi:** Lõi ảo này lập tức lao xuống ổ cứng, đọc tệp Parquet, thực thi lệnh GROUP BY / SUM, trả kết quả cho User, và **tự hủy**.

DuckDB lúc này không còn là một Database Server. Nó bị biến thành một "Hàm tính toán" (Stateless Function) hay một "Cái máy xay sinh tố". Cứ có 10 Users vào Dashboard, Superset tạo ra 10 cái máy xay độc lập, cùng xay chung một đống trái cây (Parquet). Không ai cản đường ai!

## 4. Bằng chứng Thực nghiệm (Benchmark Concurrency)
Để bảo vệ lập luận này trước các Data Architect, hệ thống đã chạy một bài kiểm thử mô phỏng 10 Workers (Tiến trình) truy vấn hoàn toàn độc lập vào một tệp Parquet.

- **Dữ liệu:** 20.000.000 dòng (300 MB Parquet).
- **Môi trường:** 10 luồng Multi-process (độc lập bộ nhớ).
- **Truy vấn:** Đọc toàn bộ bảng, chạy GROUP BY và SUM (Buộc phải quét toàn bộ tệp).

**Kết quả:**
`	ext
Tổng thời gian hoàn thành (cả 10 luồng): 1.49 giây
Thông lượng (Throughput): ~6.7 truy vấn siêu nặng / giây
Mức RAM Hệ thống dội lên (Peak RAM Spike): 471.16 MB
👉 Trung bình mỗi Worker "ăn" đúng: ~47.12 MB RAM
`

## 5. Giải mã Kết quả: Tại sao lại nhanh và ít tốn RAM đến vậy?
Thay vì ngốn hàng Gigabytes RAM như Pandas hay Spark, kiến trúc này tối ưu nhờ 2 cơ chế vật lý:
1. **OS Page Cache (Ăn gian bộ nhớ):** Khi User 1 truy vấn, hệ điều hành (Linux/Windows) phải tốn công kéo 300MB Parquet từ ổ cứng SSD lên RAM. Nhưng với User 2 đến User 10, hệ điều hành nhận ra tệp này đang nằm sẵn trong Page Cache (RAM). 9 User sau thực chất đang truy vấn trực tiếp từ RAM với tốc độ ánh sáng (Memory-mapped I/O).
2. **Vectorized Streaming:** Lõi DuckDB không tải toàn bộ 300MB vào bộ nhớ của riêng nó. Nó hút dữ liệu theo từng lô nhỏ (Vector Batches), cộng dồn kết quả, và nhả RAM ra ngay lập tức. Do đó, chi phí RAM cho mỗi tiến trình chỉ quanh quẩn ở mức 40-50MB để duy trì bộ đệm tính toán (Buffer).

## 6. Điểm Gãy (When does it break?)
Bài lập luận này không nhằm mục đích tôn vinh DuckDB là giải pháp thay thế ClickHouse trong **mọi trường hợp**. Nó chỉ chứng minh rằng: **ClickHouse là sự dư thừa tốn kém đối với mô hình SME/Mid-market**.

Kiến trúc DuckDB + Parquet sẽ chính thức gãy (cần nâng cấp lên ClickHouse) CHỈ KHI:
- **Lượng Concurrency thực tế quá lớn:** Từ 100 - 500 người dùng nhấn F5 Dashboard *cùng một giây* (Rất hiếm ở B2B nội bộ).
- **Quy mô dữ liệu quá khủng:** Bảng OBT vượt ngưỡng 100GB - 500GB, khiến OS Page Cache không thể chứa nổi, dẫn đến hiện tượng trượt bộ nhớ đệm (Cache Thrashing) và nghẽn Disk I/O liên tục.

Trừ phi doanh nghiệp của bạn đạt tới 2 "Điểm gãy" trên, việc giữ lại kiến trúc DuckDB + Parquet sẽ tiết kiệm hàng nghìn đô la chi phí máy chủ và bảo trì mỗi năm so với việc nuôi một cụm ClickHouse.
