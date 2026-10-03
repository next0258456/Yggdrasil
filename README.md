# Yggdrasil Data Platform (v0.1 Beta)

> **Minimalist Single-Node Lakehouse powered by Generative BI & Agentic Analytics.**

Yggdrasil v0.1 là nền tảng Data Lakehouse được thiết kế tối giản, loại bỏ sự cồng kềnh của các cụm phân tán (Spark/Hadoop) để tối ưu hiệu năng trên Single-Node, kết hợp với bảo mật Zero-Trust và năng lực AI Agentic.

## 🏛️ Kiến Trúc Cốt Lõi (Architecture Stack)

- **Storage**: MinIO / S3 (Object Storage)
- **Table Format**: Apache Iceberg
- **Catalog**: Postgres JDBC Catalog (Single Source of Truth)
- **Compute Engine**: Polars LazyFrame (ETL) & DuckDB (OLAP)
- **Orchestration**: n8n (Configurator) trigger Airflow 3 (Parameterized DAG)
- **BI & Security Gateway**: Apache Superset (Enforce RLS & JWT)
- **Agentic Analytics**: Mimir Bot tích hợp Obsidian Local REST API

## 🚀 Nguyên Lý Thiết Kế (The Y7L Way)

1. **Decoupled Compute & Storage**: Tách biệt hoàn toàn tính toán và lưu trữ. Storage lưu bằng chuẩn mở Iceberg, đảm bảo tính linh hoạt khi kết nối với các Engine khác nhau.
2. **Configuration-Driven Pipelines**: Áp dụng mô hình điều phối phân tầng (Decoupled Orchestration). Người dùng chỉ cần khai báo metadata, n8n đảm nhiệm vai trò Control Plane để gọi REST API và kích hoạt một Parameterized DAG tập trung trên Airflow. Giảm thiểu việc duy trì mã nguồn Python/YAML thủ công cho từng luồng dữ liệu.
3. **Data-Blind AI (Zero Leakage)**: AI Agent chỉ có quyền đọc siêu dữ liệu (Metadata/Schema) để phân tích ngữ cảnh (Intent). Tuyệt đối không được cấp quyền đọc dữ liệu thô. Mọi truy xuất dữ liệu thực tế phải thông qua cổng bảo mật của Superset (JWT).
4. **Single-Node Optimization**: Tối ưu hóa trên kiến trúc Vertical Scaling. Sử dụng Polars để xử lý và chuyển đổi dữ liệu thô (Bronze $\to$ Silver) và DuckDB để phục vụ truy vấn OLAP tốc độ cao, thay thế cho các kiến trúc phân tán phức tạp.

## 📦 Cấu trúc dự án (Project Structure)

```text
Yggdrasil/
├── dags/          # Airflow Parameterized DAGs (Xử lý tập trung)
├── n8n/           # Workflows JSON của n8n (Control Plane / Orchestrator)
├── scripts/       # Polars ETL & DuckDB execution scripts
├── docs/          # Thiết kế kỹ thuật & ADR (Export từ Obsidian)
├── .agents/       # Tiêu chuẩn và bộ kỹ năng Agentic Software Engineering
└── README.md
```

---
*Built with discipline for the Data Engineers who hate complexity.*
