# Yggdrasil Data Platform (v0.1 Beta)

> **Minimalist Single-Node Lakehouse powered by Generative BI & Agentic Analytics.**

Yggdrasil v0.1 là nền tảng Data Lakehouse được thiết kế tối giản, loại bỏ sự cồng kềnh của các cụm phân tán (Spark/Hadoop) để tối ưu hiệu năng trên Single-Node, kết hợp với bảo mật Zero-Trust và năng lực AI Agentic.

## 🏛️ Kiến Trúc Cốt Lõi (Architecture Stack)

- **Storage**: MinIO / S3 (Object Storage)
- **Table Format**: Apache Iceberg
- **Catalog**: Postgres JDBC Catalog (Single Source of Truth)
- **Compute Engine**: Polars (Gate 1: Data Cleaning) & dbt-duckdb (Gate 2: Business Modeling)
- **Orchestration**: n8n (External Integrations) & Airflow 3 (Internal Orchestrator)
- **BI & Security Gateway**: Apache Superset (Enforce RLS & JWT)
- **Agentic Analytics**: Mimir Bot với cơ chế Hybrid AI (Intent Router + Text-to-SQL Fallback)

## 🚀 Nguyên Lý Thiết Kế (The Y7L Way)

1. **Decoupled Compute & Storage**: Tách biệt hoàn toàn tính toán và lưu trữ. Storage lưu bằng chuẩn mở Iceberg, đảm bảo tính linh hoạt khi kết nối với các Engine khác nhau.
2. **Dual-Engine Orchestration**: Phân tách rõ ràng vùng lãnh thổ điều phối. n8n làm nhiệm vụ giao tiếp ngoại vi (External Integrations, webhook, thu thập dữ liệu), trong khi Airflow 3 chịu trách nhiệm điều phối lõi nội bộ (Internal Orchestrator) bằng các Parameterized DAGs.
3. **Data-Blind AI (Zero Leakage)**: AI Agent chỉ có quyền đọc siêu dữ liệu (Metadata/Schema) từ Obsidian để phân tích ngữ cảnh. Tuyệt đối không được cấp quyền đọc dữ liệu thô. Mọi truy xuất dữ liệu thực tế phải thông qua cổng bảo mật của Superset.
4. **Single-Node & Data Contracts**: Tối ưu hóa trên kiến trúc Vertical Scaling với 2 chốt chặn: Sử dụng Python/Polars (Gate 1) để lấp bẫy lỗi và dọn rác từ Bronze lên Silver thông qua Dead Letter Queue (DLQ), và dbt-duckdb (Gate 2) để thực thi Data Contracts và DAG Dependency từ Silver lên Gold.

## 📦 Cấu trúc dự án (Project Structure)

`	ext
Yggdrasil/
├── dags/          # Airflow Parameterized DAGs (Internal Orchestrator)
├── dbt_models/    # Mã nguồn dbt (Gate 2 - Silver to Gold Modeling)
├── n8n/           # Workflows JSON của n8n (External Integrations)
├── scripts/       # Polars ETL & Dead Letter Queue handlers (Gate 1)
├── docs/          # Thiết kế kỹ thuật & ADR (Export từ Obsidian)
│   ├── adrs/      # Architecture Decision Records
│   ├── guides/    # Hướng dẫn thực chiến & Lập luận kỹ thuật (PoC/Benchmarks)
├── .agents/       # Tiêu chuẩn và bộ kỹ năng Agentic Software Engineering
└── README.md
`

---
*Built with discipline for the Data Engineers who hate complexity.*
