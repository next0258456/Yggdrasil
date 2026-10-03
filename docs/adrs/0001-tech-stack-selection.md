# ADR 0001: Lựa chọn Tech Stack cho Yggdrasil v0.1

- **Trạng thái**: Đã phê duyệt (Approved)
- **Ngày quyết định**: 2026-10-03
- **Người ra quyết định**: Kratos (Tech Lead)

## Bối cảnh (Context)
Hệ thống Big Data truyền thống dựa trên Hadoop/Spark quá cồng kềnh, tốn kém chi phí duy trì cụm máy chủ và không phù hợp với quy mô hiện tại của doanh nghiệp. Cần một giải pháp tinh gọn, tối ưu trên Single-Node nhưng vẫn đảm bảo khả năng mở rộng (Lakehouse).

## Quyết định (Decision)
Chúng tôi quyết định áp dụng 스택 kiến trúc sau:
1. **Format**: Apache Iceberg (thay vì Delta Lake).
2. **Catalog**: Postgres JDBC Catalog.
3. **ETL**: Polars LazyFrame.
4. **OLAP/Query**: DuckDB.

## Hậu quả (Consequences)
- **Điểm tích cực**: Tốc độ xử lý cực nhanh, tốn ít RAM, không cần duy trì cluster (giảm 80% chi phí hạ tầng). Quản lý dễ dàng trên 1 máy chủ duy nhất.
- **Điểm hạn chế**: Nếu dữ liệu phình to lên mức Petabytes vượt quá khả năng xử lý của ổ cứng/RAM trên Single-Node, sẽ phải kiến trúc lại phần Compute.
