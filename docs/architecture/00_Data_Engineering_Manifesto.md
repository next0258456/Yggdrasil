# Data Engineering Manifesto (Tuyên ngôn Yggdrasil)

Đây là "Hiến pháp" của Data Team. Bất kỳ công cụ hay luồng xử lý nào được thêm vào hệ thống đều phải tuân thủ tuyệt đối 3 nguyên tắc cốt lõi (The 3 Pillars) sau đây:

---

## 1. Decoupled Compute & Storage (Tách biệt Tính toán và Lưu trữ)
*Không bao giờ để dữ liệu bị giam cầm trong một Engine duy nhất.*

- Dữ liệu thô và đã xử lý phải được lưu trữ ở định dạng mở (Apache Iceberg trên MinIO).
- Bất kỳ Compute Engine nào (Polars, DuckDB, hay sau này là các engine khác) cũng có thể cắm vào và truy vấn dữ liệu mà không cần di chuyển (Zero-copy).

## 2. Configuration-Driven & Data Contracts (Cấu hình hóa & Hợp đồng dữ liệu)
*Data Engineering ở quy mô lớn là Software Engineering. Giảm thiểu mã lặp và siết chặt kỷ luật.*

- **Tách rời Config và Code:** Logic chuyển đổi (Transformations) nằm trong mã nguồn (Polars), nhưng Luồng chạy (Pipeline Routing) nằm trong cấu hình định tuyến (n8n/Google Sheets). Sử dụng 1 Parameterized DAG duy nhất trên Airflow để xử lý.
- **Hợp đồng dữ liệu (Data Contract):** Chính các file cấu hình này sẽ đóng vai trò là Hợp đồng dữ liệu (Data Contract). Dữ liệu từ nguồn (Upstream) bắt buộc phải thõa mãn Schema và các ràng buộc (Constraints) khai báo trong Config trước khi được nạp vào Iceberg. Nguyên tắc "Garbage in, Garbage out" phải bị chặn đứng ngay từ vòng gửi xe.

## 3. Data-Blind AI & Zero Trust (Trí tuệ nhân tạo mù dữ liệu)
*Bảo mật là tối thượng. AI là công cụ, không phải là chủ nhân của dữ liệu.*

- LLM (Mimir Bot) tuyệt đối **không** được cấp quyền đọc dữ liệu tài chính/nghiệp vụ thô. 
- LLM chỉ được cấp Schema và Metadata (thông qua Knowledge Vault) để phân tích ý định (Intent).
- Mọi truy xuất dữ liệu thực tế bắt buộc phải đi qua cổng bảo mật (Apache Superset) với JWT Token có thời hạn và bị giới hạn bởi Row-Level Security (RLS).
