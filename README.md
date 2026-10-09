# Yggdrasil Data Platform (v0.1 Beta)

> *"Để đáp ứng một doanh nghiệp bình thường (không phải Hyper-scaler), kiến trúc của một Data Platform có thể tối giản tới mức nào?"*

**Yggdrasil v0.1** chính là câu trả lời. Đây là nền tảng Data Lakehouse từ chối sự cồng kềnh của các cụm phân tán (Spark/Hadoop) để vắt kiệt hiệu năng trên kiến trúc Single-Node, kết hợp cùng bảo mật Zero-Trust và năng lực AI Agentic.

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

## 📦 Cấu trúc dự án hiện tại (Project Structure)

Kho lưu trữ này hiện tại đang đóng vai trò là **Bản thiết kế cốt lõi (Architecture & Blueprint Repository)**. Các thư mục mã nguồn thực tế (như dbt, Airflow, Polars) sẽ được khởi tạo trong giai đoạn Triển khai (Implementation).

```	ext
Yggdrasil/
├── docs/                 # Tài liệu cốt lõi (Export từ Obsidian)
│   ├── architecture/     # Thiết kế chi tiết các tầng (Tầng 1 -> Tầng 5)
│   ├── adrs/             # Architecture Decision Records (Lưu vết quyết định)
│   └── guides/           # Hướng dẫn thực chiến & Lập luận kỹ thuật (PoC/Benchmarks)
└── README.md             # Tuyên ngôn và Tổng quan kiến trúc
```

---
*Built with discipline for the Data Engineers who hate complexity.*

