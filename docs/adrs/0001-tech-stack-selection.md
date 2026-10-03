# ADR 0001: Lựa chọn Tech Stack cốt lõi cho Yggdrasil v0.1

- **Trạng thái**: Đã phê duyệt (Approved)
- **Ngày quyết định**: 2026-10-03
- **Người ra quyết định**: Kratos (Tech Lead)

## Bối cảnh (Context)
Hệ thống Big Data truyền thống dựa trên Hadoop/Spark quá cồng kềnh, tốn kém chi phí duy trì cụm máy chủ và không phù hợp với triết lý "Tối giản" của Yggdrasil v0.1. Cần một giải pháp tinh gọn, tối ưu trên Single-Node nhưng vẫn đảm bảo khả năng mở rộng (Lakehouse) và bảo mật tuyệt đối. 

Dưới đây là các quyết định (Lý do đi chợ) giải thích chi tiết cho 3 mảng công nghệ cốt lõi nhất cấu thành nên nền tảng.

## Quyết định & Lập luận (Decision & Rationale)

### 1. Mâm Storage & Format: Apache Iceberg + Postgres JDBC Catalog (Loại bỏ Delta Lake)
- **Quyết định**: Sử dụng định dạng Apache Iceberg thay cho Delta Lake. Quản lý siêu dữ liệu (Metadata) thông qua Postgres JDBC Catalog thay vì Hive Metastore.
- **Lập luận**:
  - **Tại sao Iceberg?** Iceberg là chuẩn thiết kế hướng Table-Format đích thực, hoàn toàn phi tập trung (engine-agnostic). Trong khi Delta Lake vẫn mang hơi hướm "Vendor Lock-in" (phụ thuộc nhiều vào hệ sinh thái Databricks/Spark). Iceberg cho phép cắm đa dạng Compute Engine (DuckDB, Polars) vào đọc một cách trơn tru.
  - **Tại sao Postgres JDBC Catalog?** Hive Metastore yêu cầu chạy môi trường Java/JVM nặng nề và dễ lỗi. Sử dụng Postgres làm JDBC Catalog biến hệ thống trở nên siêu gọn nhẹ, đảm bảo ACID transactions tuyệt đối, đồng thời dễ dàng dùng SQL query trực tiếp vào catalog để debug khi hệ thống có sự cố.

### 2. Mâm Compute: Polars + DuckDB (Khai tử Apache Spark & Trino)
- **Quyết định**: Sử dụng Polars (LazyFrame) làm động cơ ETL (Data Transformation) và DuckDB làm động cơ truy vấn phân tích (OLAP). Loại bỏ hoàn toàn Spark và Trino.
- **Lập luận**:
  - **Triết lý Single-Node Big Data**: Với tập dữ liệu dưới ngưỡng 500GB - 1TB, cụm phân tán (Spark) là một sự lãng phí tài nguyên khủng khiếp do chi phí hao phí (overhead) của JVM và Network Shuffle giữa các node.
  - **Polars**: Được viết bằng Rust, Polars khai thác tối đa đa lõi CPU và RAM trên một máy tính duy nhất, tốc độ xử lý nhanh gấp nhiều lần Spark ở quy mô vừa, cú pháp biểu thức mạnh mẽ.
  - **DuckDB**: Đóng vai trò là "SQLite for Analytics". Không cần thiết lập Server dài dòng, truy vấn trực tiếp vào Parquet/Iceberg trên MinIO cực tốc độ, hoàn hảo để làm lớp Semantic/Serving cho các báo cáo BI.

### 3. Mâm Orchestration: n8n kết hợp Airflow 3 (Dual-Engine)
- **Quyết định**: Tách biệt luồng điều phối thành 2 vùng lãnh thổ: n8n làm External Integrations và Airflow 3 làm Internal Orchestrator.
- **Lập luận**:
  - Các hệ thống đơn lẻ (như Dagster hay Prefect) khó có thể làm xuất sắc cả hai việc: Giao tiếp với thế giới hỗn loạn bên ngoài và duy trì kỷ luật Data nội bộ.
  - **n8n**: Đảm nhận vai trò "Bộ ngoại giao". Lắng nghe Webhook, gọi API, kết nối với Zalo/Telegram (AI Mimir Bot), cào dữ liệu Google Sheets cực kỳ nhanh chóng bằng tư duy Low-code.
  - **Airflow 3**: Đóng vai trò "Bộ nội vụ". Nó nhận tín hiệu từ n8n để kích hoạt 1 *Parameterized DAG* (cối xay thịt) duy nhất, phân bổ tài nguyên để chạy Polars/DuckDB khắt khe, tuân thủ nghiêm ngặt Hợp đồng dữ liệu (Data Contract).

### 4. Mâm BI & Security Gateway: Apache Superset (Zero-Trust)
- **Quyết định**: Sử dụng Apache Superset không chỉ làm công cụ vẽ biểu đồ (BI Dashboard) truyền thống, mà đóng vai trò là "Cửa khẩu dữ liệu bảo mật" (Security Gateway) duy nhất cho toàn bộ hệ thống, đặc biệt là phục vụ AI.
- **Lập luận**:
  - **Free API Backend & JWT**: Việc tự code một API Backend riêng (bằng FastAPI/NodeJS) để Bot chọc vào Lakehouse là lãng phí. Superset có sẵn REST API cực mạnh với cơ chế xác thực JWT. AI Bot (Mimir) chỉ cần cầm Token đến gọi API, hết hạn là mất quyền.
  - **Row-Level Security (RLS)**: Bức tường thép bảo vệ dữ liệu. Khi AI xin dữ liệu, Superset áp đặt luật RLS để che giấu hoàn toàn dữ liệu nhạy cảm (Data-Blind AI). Bot chỉ thấy được những gì nó được phép thấy.
  - **Semantic Layer hợp nhất**: Cả Con người (xem Dashboard) và AI (gọi API) đều đi qua lớp Semantic của Superset. Tránh tuyệt đối tình trạng "Người tính ra một số, Bot tính ra một số khác".

## Hậu quả (Consequences)
- **Điểm tích cực**: Giảm 80% chi phí hạ tầng, loại bỏ hoàn toàn sự phức tạp của JVM/Cluster. Tốc độ phát triển (Developer Velocity) siêu tốc, thời gian query giảm xuống mức millisecond. Quản trị viên chỉ cần tập trung bảo trì 1 máy chủ vật lý mạnh mẽ.
- **Điểm hạn chế**: Hệ thống bị giới hạn bởi sức mạnh vật lý của một Node duy nhất (Vertical Scaling). Nếu một ngày dữ liệu phình to lên mức nhiều Petabytes, phần Compute sẽ phải cấu trúc lại để scale ngang. Tuy nhiên, nhờ nguyên tắc **Decoupled Compute & Storage**, việc vứt bỏ Polars để thay bằng Engine phân tán trong tương lai là hoàn toàn khả thi và không gây mất mát dữ liệu.
