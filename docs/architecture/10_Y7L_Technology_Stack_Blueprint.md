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

---

## ⚖️ Cái giá phải trả (Trade-offs & Limitations)
*Trong kiến trúc hệ thống, không có viên đạn bạc (No Silver Bullet). Đi chợ mua được "Hiệu năng" và "Sự tối giản" thì bắt buộc phải trả giá bằng 5 nhược điểm chí mạng sau:*

1. **Giới hạn Scale ngang (The Vertical Scaling Trap)**
   - *Mua:* Tốc độ xử lý sấm sét trên Single-Node, né được sự cồng kềnh, tốn kém của JVM/Cluster.
   - *Trả:* Khi dữ liệu chạm ngưỡng chục Terabytes, ta không thể "cắm thêm máy" (Scale-out) như Spark/Hadoop, mà bắt buộc phải đốt tiền nâng cấp Server vật lý mạnh hơn (RAM/CPU to hơn).

2. **Đứt gãy luồng truy vết (Dual-Engine Complexity)**
   - *Mua:* Tối ưu tài nguyên tuyệt đối, Airflow không bị chết ngạt bởi các luồng Polling chờ đợi vì đã có n8n gánh vác.
   - *Trả:* Khi một Pipeline thất bại, kỹ sư dữ liệu phải phân thân đi đọc Log ở cả 2 nền tảng: Check n8n xem đã tải file vào MinIO thành công chưa, sau đó mới qua Airflow mò xem Polars chết ở dòng nào.

3. **Tuyệt giao với Streaming thời gian thực**
   - *Mua:* Kiến trúc thuần Batch và Near Real-Time (SLA 5 phút) giữ cho cấu trúc Code và logic Hợp đồng dữ liệu (Data Contract) cực kỳ đơn giản.
   - *Trả:* Nếu nghiệp vụ yêu cầu xử lý mili-giây (ví dụ: Fraud Detection live), bộ khung này hoàn toàn bó tay. Không có cửa để nhét Kafka/Flink vào mà giữ được triết lý tối giản.

4. **Nút thắt cổ chai Postgres Catalog**
   - *Mua:* Triển khai nhanh, dễ "tầm gửi" cho các DBA vận hành, không phải học thêm cấu trúc REST Catalog mới.
   - *Trả:* Theo thời gian, khi Iceberg liên tục ghi đè và sinh ra hàng trăm ngàn Snapshots, tốc độ truy xuất Metadata của Postgres sẽ sập nguồn nếu không được dọn dẹp định kỳ (Vacuum/Expire Snapshots).

5. **Chi phí Đào tạo nhân sự (Learning Curve)**
   - *Mua:* Hiệu năng ETL vô đối của Polars (dựa trên lõi Rust) so với Python thuần.
   - *Trả:* Kỹ sư dữ liệu trên thị trường đã bị "đóng đinh" vào Pandas và PySpark. Việc ép họ chuyển sang tư duy LazyFrame và Expressions của Polars sẽ tiêu tốn thời gian và chi phí đào tạo (Onboarding) ban đầu.
