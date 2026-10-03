# Y7L Platform: Technology Stack Blueprint (v0.1)

Tài liệu này chốt hạ bộ công cụ (Tech Stack) cho các tầng của kiến trúc Data Lakehouse Yggdrasil. Sự kết hợp này hướng tới mục tiêu: **Tối giản hóa hạ tầng, tối ưu hiệu năng Single-Node Big Data, và tích hợp AI an toàn tuyệt đối (Zero Trust).**

---

## 🏗️ Ma Trận Công Nghệ (The Architecture Stack)

| Tầng (Layer) | Công nghệ đề xuất | Lý do chọn (Tư duy Kiến trúc) |
| :--- | :--- | :--- |
| **1. Storage** (Lưu trữ) | **MinIO / AWS S3** | Object Storage linh hoạt, tương thích tốt nhất với kiến trúc Lakehouse. |
| **2. Table Format** | **Apache Iceberg** | Đảm bảo ACID transactions, Schema Evolution và Time-travel. Chuẩn mở không bị Vendor Lock-in. |
| **3. Catalog** (Metadata) | **Postgres JDBC Catalog** | Single Source of Truth cho toàn bộ metadata của Iceberg, dễ dàng triển khai và backup. |
| **4. Compute** (Động cơ) | **Polars (ETL) & DuckDB (OLAP)** | Khai tử Spark/Hadoop! Xử lý "Single-Node Big Data" cực tốc độ, tận dụng tối đa RAM/CPU mà không bị overhead của JVM hay Cụm phân tán. |
| **5. Orchestration** | **n8n & Airflow 3** | Dual-Engine Orchestration: n8n làm Control Plane xử lý giao tiếp ngoại vi (APIs, Webhooks). Airflow 3 làm Internal Orchestrator chạy các Parameterized DAGs. |
| **6. BI & Security** | **Apache Superset** | Đóng vai trò Data Gateway. Phân quyền chặt chẽ bằng Row-Level Security (RLS) và xác thực bằng JWT Token. |
| **7. LLM Semantic Router** | **Mimir Bot (Zalo / Chat)** | Áp dụng mô hình Data-Blind AI. Không cho phép LLM hoạt động tự do như một Agent. Mimir chỉ đóng vai trò "Bộ định tuyến ý định" (Intent Router), điều hướng câu hỏi thành tham số để gọi API của Superset. |
