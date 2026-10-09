# Y7L Platform: Technology Stack Blueprint (v0.1)

Tài liệu này chốt hạ bộ công cụ (Tech Stack) cho các tầng của kiến trúc Data Lakehouse Yggdrasil. Sự kết hợp này hướng tới mục tiêu: **Tối giản hóa hạ tầng, tối ưu hiệu năng Single-Node Big Data, và tích hợp AI an toàn tuyệt đối (Zero Trust).**

---

## 🏗️ Ma Trận Công Nghệ Đồng Bộ Theo 5 Tầng Kiến Trúc (The Architecture Stack)

Để tránh tình trạng "tàng hình" hoặc chồng chéo, bộ công nghệ dưới đây được ánh xạ chính xác 1:1 với 5 Tầng kiến trúc cốt lõi của hệ thống.

| Tầng Kiến Trúc | Công nghệ đề xuất | Vai trò & Lý do chọn (Tư duy Kiến trúc) |
| :--- | :--- | :--- |
| **Tầng 1: Ingestion** (Trích xuất & Thu thập) | **n8n & Airflow 3** | **n8n** đóng vai trò Control Plane hút dữ liệu linh hoạt từ ngoại vi (API, Webhooks). **Airflow 3** điều phối các Parameterized DAGs bên trong để hút từ Database. |
| **Tầng 2: Storage & Compute** (Hồ dữ liệu & Động cơ) | **MinIO + Iceberg + Postgres** <br> **Polars + dbt-duckdb** | - **Lưu trữ:** MinIO (S3 Object Storage) làm lõi vật lý. Iceberg làm Table Format. Postgres làm JDBC Catalog tập trung.<br>- **Tính toán (2 Gates):** Python/Polars (Gate 1) dọn rác tốc độ cao từ Bronze lên Silver. dbt-duckdb (Gate 2) quản lý Data Contracts từ Silver lên Gold. |
| **Tầng 3: Serving & Security** (Truy vấn & Phân quyền) | **Apache Superset + Redis** <br> *(Nhúng DuckDB)* | **Superset** làm Data Gateway độc tôn. Nhúng thẳng lõi DuckDB In-Memory để đọc Parquet (không cần OLAP Server như ClickHouse). Sử dụng **Redis** Cache để chống truy vấn dội bom. Ép bảo mật bằng Row-Level Security (RLS) và JWT Token. |
| **Tầng 4: Knowledge & Semantic** (Lớp Ngữ nghĩa) | **Obsidian** (Markdown Graph) | Tách khối Toán học (Superset lo) ra khỏi khối Ngữ cảnh kinh doanh. Dùng cấu trúc thư mục Markdown và liên kết đồ thị (Wikilinks) của Obsidian làm bộ nhớ dài hạn, rà soát Bẫy dữ liệu (Data Traps) cho AI đọc hiểu chuẩn tuyệt đối. |
| **Tầng 5: AI Gateway** (Cổng giao tiếp tự động) | **Mimir Bot (Zalo) + n8n** | Áp dụng mô hình Data-Blind AI (Zero Trust). **Mimir** tương tác với người dùng qua Zalo. Hoạt động theo cơ chế **Hybrid (Lai)**: Vừa làm Intent Router gọi API Superset (Happy path), vừa sinh Text-to-SQL (Ad-hoc path) kẹp RLS. **n8n** đứng giữa làm Webhook xử lý luồng xác thực Zalo-Webview an toàn. |

