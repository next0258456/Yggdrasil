# Hướng dẫn 01: Lập luận Kiến trúc - Tối ưu hóa Concurrency với DuckDB In-Memory và Parquet

## 1. Đặt vấn đề (Problem Statement)
Trong các hệ thống Data Engineering, kiến trúc OLAP truyền thống thường khuyến nghị sử dụng các hệ quản trị cơ sở dữ liệu phân tán (như ClickHouse, Apache Druid) để giải quyết bài toán truy cập đồng thời (High Concurrency). Ngược lại, DuckDB thường bị nhầm tưởng là công cụ chỉ phù hợp cho phân tích cá nhân (Single-player) do những hạn chế về khóa ghi (Write Lock) ở định dạng lưu trữ mặc định.

Tài liệu này trình bày lập luận kỹ thuật (Technical Justification) của nền tảng Yggdrasil: Bằng cách phân tách hoàn toàn lớp tính toán (Compute) và lưu trữ (Storage), hệ thống có thể sử dụng DuckDB để đáp ứng tải trọng truy vấn đồng thời cao mà không cần đến sự cồng kềnh của ClickHouse, tối ưu hóa đáng kể chi phí hạ tầng cho phân khúc doanh nghiệp SME.

## 2. Phân tích nguyên nhân thắt cổ chai của DuckDB (Root Cause Analysis)
Khớp nghẽn truy cập đồng thời (Concurrency Bottleneck) của DuckDB không xuất phát từ engine tính toán, mà bắt nguồn từ định dạng lưu trữ có trạng thái (Stateful Storage). 

- Khi sử dụng định dạng gốc .duckdb, hệ thống áp dụng cơ chế khóa tệp độc quyền (Exclusive File Lock) tương tự SQLite để đảm bảo tính toàn vẹn (ACID).
- Khi Tiến trình A (Process A) đang thực hiện thao tác đọc/ghi, Tiến trình B cố gắng truy cập sẽ bị hệ thống từ chối với ngoại lệ IO Error: Database is locked.

👉 **Kết luận:** Giới hạn nằm ở lớp lưu trữ vật lý, không phải ở tốc độ xử lý của động cơ tính toán.

## 3. Kiến trúc Đề xuất: Phân tách lưu trữ và tính toán (Stateless In-Memory Compute)
Để giải quyết triệt để nút thắt trên, Yggdrasil áp dụng mô hình kiến trúc Decoupled Compute & Storage:

1. **Lớp Lưu trữ (Storage - Apache Iceberg / Parquet):** 
   Dữ liệu tại lớp Gold được lưu trữ dưới định dạng cột Parquet (được quản lý bởi Iceberg). Đây là định dạng lưu trữ bất biến (Immutable/Read-only). Hệ điều hành (OS) cho phép vô số tiến trình đọc cùng một tệp Parquet mà không kích hoạt bất kỳ cơ chế khóa (Locking) nào.
   
2. **Lớp Tính toán (Compute - DuckDB In-Memory):** 
   Khi tầng BI (Superset) tiếp nhận truy vấn, hệ thống không kết nối vào tệp cơ sở dữ liệu tĩnh. Thay vào đó, mỗi Gunicorn Worker khởi tạo một phiên bản DuckDB hoàn toàn độc lập trên bộ nhớ ảo (In-Memory) thông qua chuỗi kết nối duckdb.connect(':memory:'). 
   
3. **Tiến trình Thực thi (Execution Flow):** 
   Các phiên bản DuckDB độc lập này hoạt động như các "Hàm tính toán phi trạng thái" (Stateless Compute Nodes). Chúng song song đọc dữ liệu từ tệp Parquet, thực thi tính toán (Aggregation) và giải phóng bộ nhớ ngay khi trả về kết quả. Không tồn tại tình trạng tranh chấp tài nguyên (Resource Contention) giữa các luồng.

## 4. Chứng minh Thực nghiệm (Benchmark Proof)
Để kiểm chứng năng lực đáp ứng, một bài kiểm thử cường độ cao (Stress Test) đã được thực hiện với các thông số sau:
- **Khối lượng dữ liệu:** 20.000.000 bản ghi (Tệp Parquet dung lượng ~300 MB).
- **Môi trường:** 10 Gunicorn Workers (Multi-process) hoạt động đồng thời và độc lập.
- **Loại truy vấn:** Full Table Scan kết hợp GROUP BY và SUM.

**Kết quả đạt được:**
`	ext
- Tổng thời gian hoàn thành (Toàn bộ 10 luồng): 1.49 giây
- Thông lượng trung bình (Throughput): ~6.7 truy vấn phân tích / giây
- Tổng tài nguyên RAM phát sinh (Peak RAM Spike): 471.16 MB
- Phân bổ RAM trung bình trên mỗi Worker: ~47.12 MB
`

## 5. Giải mã Hiệu năng: Tối ưu I/O và Bộ nhớ
Khả năng duy trì hiệu năng cao với lượng RAM tối thiểu (chỉ 47MB mỗi tiến trình cho 20 triệu dòng) đến từ hai cơ chế kỹ thuật cốt lõi:

1. **Tận dụng OS Page Cache (Bộ nhớ đệm Hệ điều hành):** 
   Khi Worker đầu tiên truy vấn, hệ điều hành (OS) sẽ nạp tệp Parquet từ ổ cứng (SSD) vào Page Cache. Đối với 9 Workers tiếp theo, truy vấn thực chất được thực hiện trực tiếp trên RAM (Memory-mapped I/O) với độ trễ (Latency) gần như bằng không.
   
2. **Động cơ Vectorized Streaming:** 
   DuckDB không tải toàn bộ 300MB dữ liệu vào bộ nhớ cấp phát của riêng nó. Engine thực hiện đọc luồng (Streaming) theo từng lô dữ liệu nhỏ (Vector Batches), tính toán và lập tức giải phóng bộ nhớ (Garbage Collection). Cơ chế này giữ cho bộ đệm (Buffer) luôn ở mức tối thiểu.

## 6. Giới hạn Hệ thống (System Limitations & Capacity Planning)
Tài liệu này xác nhận kiến trúc DuckDB + Parquet là giải pháp thay thế ClickHouse hoàn hảo về mặt hiệu năng/chi phí đối với phân khúc SME/Mid-market. Tuy nhiên, kiến trúc này sẽ bộc lộ giới hạn (Threshold) và cần chuyển dịch sang ClickHouse khi hệ thống chạm ngưỡng sau:

- **Tần suất truy cập cực cao (Ultra-High Concurrency):** Vượt quá ngưỡng 100 - 500 truy vấn phân tích *đồng thời trong cùng một giây* (Rất hiếm gặp ở các hệ thống Dashboard B2B nội bộ).
- **Quy mô Dữ liệu Siêu lớn (Massive Dataset Scale):** Khi kích thước bảng One-Big-Table (OBT) vượt quá dung lượng RAM vật lý của máy chủ (ví dụ: > 100GB). Lúc này, cơ chế OS Page Cache sẽ bị quá tải (Cache Thrashing), buộc hệ thống phải liên tục đọc/ghi ổ đĩa, làm suy giảm hiệu năng nghiêm trọng.

**Tổng kết:** Khi duy trì dưới ngưỡng giới hạn trên, Yggdrasil đảm bảo hiệu suất truy vấn ở mức mili-giây với tổng chi phí sở hữu hạ tầng (TCO) thấp hơn nhiều so với việc duy trì một cụm OLAP Server chuyên dụng.
