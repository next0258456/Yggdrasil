# Data Engineering Manifesto (Tuyên ngôn Yggdrasil)

Đây là "Hiến pháp" của Data Team. Bất kỳ công cụ hay luồng xử lý nào được thêm vào hệ thống đều phải tuân thủ tuyệt đối 3 nguyên tắc cốt lõi (The 3 Pillars) sau đây:

---

## 1. Decoupled Compute & Storage (Tách biệt Tính toán và Lưu trữ)
*Không bao giờ để dữ liệu bị giam cầm trong một Engine duy nhất.*

- Dữ liệu thô và đã xử lý phải được lưu trữ ở định dạng mở (Apache Iceberg trên MinIO).
- Bất kỳ Compute Engine nào (Polars, DuckDB, hay sau này là các engine khác) cũng có thể cắm vào và truy vấn dữ liệu mà không cần di chuyển (Zero-copy).

## 2. Configuration-Driven Pipelines (Cấu hình hóa luồng dữ liệu)
*Data Engineering ở quy mô lớn là Software Engineering. Giảm thiểu việc viết mã lặp lại.*

- **Tách rời Config và Code:** Logic chuyển đổi cốt lõi (Transformations) nằm trong mã nguồn (Polars), nhưng Luồng chạy (Pipeline Routing) nằm trong siêu dữ liệu định tuyến (n8n/Google Sheets).
- Thay vì viết 100 file Python cho 100 bảng, chúng ta viết **1 Parameterized DAG** duy nhất trên Airflow và nạp cấu hình vào để chạy.

## 3. Data-Blind AI & Zero Trust (Trí tuệ nhân tạo mù dữ liệu)
*Bảo mật là tối thượng. AI là công cụ, không phải là chủ nhân của dữ liệu.*

- LLM (Mimir Bot) tuyệt đối **không** được cấp quyền đọc dữ liệu tài chính/nghiệp vụ thô. 
- LLM chỉ được cấp Schema và Metadata (thông qua Knowledge Vault) để phân tích ý định (Intent).
- Mọi truy xuất dữ liệu thực tế bắt buộc phải đi qua cổng bảo mật (Apache Superset) với JWT Token có thời hạn và bị giới hạn bởi Row-Level Security (RLS).
