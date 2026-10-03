# Yggdrasil Data Platform (v2.0)
Lakehouse tối giản tích hợp Generative BI.

## 🏛️ Architecture Stack
- **Storage**: MinIO / S3
- **Format**: Apache Iceberg
- **Compute**: Polars & DuckDB
- **Ingestion**: n8n (Configurator) & Python
- **Orchestration**: Airflow (Parameterized DAG)
- **BI & Security**: Apache Superset (RLS & JWT)
