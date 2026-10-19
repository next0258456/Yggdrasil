# Yggdrasil Data Platform (v0.1 Beta)

> *"Để đáp ứng một doanh nghiệp bình thường (không phải Hyper-scaler), kiến trúc của một Data Platform có thể tối giản tới mức nào?"*

**Yggdrasil v0.1** chính là câu trả lời. Đây là nền tảng Data Lakehouse từ chối sự cồng kềnh của các cụm phân tán (Spark/Hadoop) để vắt kiệt hiệu năng trên kiến trúc Single-Node, kết hợp cùng bảo mật Zero-Trust và năng lực AI Agentic.

## 🏛️ Kiến Trúc Cốt Lõi (Architecture Stack)

- **Storage**: MinIO / S3 (Object Storage)
- **Table Format**: Apache Iceberg
- **Catalog**: Iceberg REST Catalog ([Bifrost Proxy](https://github.com/next0258456/bifrost-proxy) - Golang + Embedded DuckDB)
- **Compute & Contracts**: Polars (Gate 1: Data Cleaning) & [Valkyrie Engine](https://github.com/next0258456/valkyrie) (Gate 2: Data Contracts)
- **Orchestration**: n8n (External Integrations) & Airflow 3 (Internal Orchestrator)
- **BI & Security Gateway**: Apache Superset (Enforce RLS & JWT)
- **Agentic Analytics**: Mimir Bot với cơ chế Hybrid AI (Intent Router + Text-to-SQL Fallback)

## 🔌 Hệ Sinh Thái Repos Phụ (Ecosystem & Sub-Repositories)

Để giữ cho kiến trúc tổng luôn tinh gọn và tránh biến dự án thành một khối cồng kềnh (Monolith), các động cơ thực thi cốt lõi của Yggdrasil được phân tách thành các repository chuyên biệt:

| Repository | Công nghệ cốt lõi | Vai trò trong hệ sinh thái Yggdrasil |
| :--- | :--- | :--- |
| 🌉 [**bifrost-proxy**](https://github.com/next0258456/bifrost-proxy) | **Golang + Embedded DuckDB** | **Iceberg REST Catalog & DuckLake Sync Gateway**: Tiếp nhận luồng ghi dữ liệu chuẩn Iceberg REST (Redpanda, Spark, PyIceberg) với RAM < 300MB, đồng bộ tức thì sang Native DuckLake Catalog cho truy vấn Sub-second. |
| ⚔️ [**valkyrie**](https://github.com/next0258456/valkyrie) | **Python + DuckDB Engine** | **Data Contract & Circuit Breaker Engine**: Trình biên dịch hợp đồng dữ liệu YAML sang DuckDB SQL Single-Pass vector hóa, tự động phân tách Clean/DLQ và bảo vệ Lakehouse khỏi dữ liệu rác. |

## 🚀 Nguyên Lý Thiết Kế (The Y7L Way)

1. **Decoupled Compute & Storage**: Tách biệt hoàn toàn tính toán và lưu trữ. Storage lưu bằng chuẩn mở Iceberg, đảm bảo tính linh hoạt khi kết nối với các Engine khác nhau.
2. **Dual-Engine Orchestration**: Phân tách rõ ràng vùng lãnh thổ điều phối. n8n làm nhiệm vụ giao tiếp ngoại vi (External Integrations, webhook, thu thập dữ liệu), trong khi Airflow 3 chịu trách nhiệm điều phối lõi nội bộ (Internal Orchestrator) bằng các Parameterized DAGs.
3. **Data-Blind AI (Zero Leakage)**: AI Agent chỉ có quyền đọc siêu dữ liệu (Metadata/Schema) từ Obsidian để phân tích ngữ cảnh. Tuyệt đối không được cấp quyền đọc dữ liệu thô. Mọi truy xuất dữ liệu thực tế phải thông qua cổng bảo mật của Superset.
4. **Single-Node & Data Contracts**: Tối ưu hóa trên kiến trúc Vertical Scaling với 2 chốt chặn: Sử dụng Python/Polars (Gate 1) để lấp bẫy lỗi và dọn rác từ Bronze lên Silver thông qua Dead Letter Queue (DLQ), và [Valkyrie Engine](https://github.com/next0258456/valkyrie) (Gate 2) để thực thi Data Contracts và DAG Dependency từ Silver lên Gold.

## 📦 Cấu trúc dự án hiện tại (Project Structure)

Kho lưu trữ này đóng vai trò là **Bản thiết kế cốt lõi & Nhạc trưởng điều phối (Architecture Blueprint & Orchestration Core)**:

```text
Yggdrasil (Platform Blueprint)
├── docs/                 # Tài liệu thiết kế cốt lõi (Export từ Obsidian)
│   ├── architecture/     # Thiết kế chi tiết từng tầng (Tầng 1 -> Tầng 5)
│   ├── adrs/             # Architecture Decision Records (Lưu vết quyết định)
│   └── guides/           # Hướng dẫn thực chiến & Lập luận kỹ thuật (PoC/Benchmarks)
├── README.md             # Tuyên ngôn và Tổng quan kiến trúc
│
├── 🔗 [bifrost-proxy]    # (Sub-repo) Iceberg REST Catalog & DuckLake Sync Proxy
└── 🔗 [valkyrie]         # (Sub-repo) Data Contract & Circuit Breaker Engine
```

---
*Built with discipline for the Data Engineers who hate complexity.*
