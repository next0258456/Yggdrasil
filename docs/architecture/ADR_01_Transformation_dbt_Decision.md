# ADR 01: Quyết định Giữ dbt (Data Build Tool) - Góc nhìn Data Engineering

## 1. Ngữ cảnh (Context)
Trong kiến trúc Yggdrasil, Tầng Biến đổi (Transformation Layer) từ Bronze -> Silver -> Gold cần một công cụ quản lý. Câu hỏi đặt ra là: Có nên dùng dbt không, và mục đích cốt lõi của nó trong hệ thống này là gì?

## 2. Tại sao lại từng nghĩ đến việc BỎ dbt? (The Case Against dbt)
Việc loại bỏ \dbt\ khỏi stack đã từng được cân nhắc rất kỹ lưỡng dựa trên các nhược điểm cốt lõi sau:
1. **Tech-stack Bloat (Sự cồng kềnh):** Yggdrasil theo đuổi sự tối giản tuyệt đối (Minimalism). \dbt-core\ kéo theo một hệ sinh thái dependency Python khổng lồ, làm nặng container và đi ngược lại triết lý "nhẹ và nhanh".
2. **Overhead & Latency:** Thời gian khởi động (startup time) và biên dịch Jinja của dbt khá chậm. Khi kết hợp với một engine siêu tốc độ như DuckDB, cái "độ trễ" của dbt trở thành một nút thắt cổ chai vô duyên.
3. **Văn hóa "Spaghetti Modeling":** Hệ sinh thái dbt (Modern Data Stack) sinh ra cái văn hóa độc hại: khuyến khích chẻ nhỏ data thành hàng trăm view (staging, intermediate, mart) vô thưởng vô phạt, khiến kho dữ liệu trở thành một mớ rác không thể bảo trì.

## 3. Phân định Trách nhiệm (The Separation of Concerns)
Dù có nhiều nhược điểm, việc giữ hay bỏ dbt phụ thuộc vào cách chúng ta phân quyền. Yggdrasil **KHÔNG** dùng dbt để "trao quyền" cho Data Analyst (DA) tự build model như văn hóa MDS.

- **Gate 1 (Bronze -> Silver):** Do **Python** đảm nhiệm. Python (thông qua Polars/DuckDB/Pydantic) sẽ xử lý các tác vụ kiểm định kỹ thuật (giải mã JSON, check kiểu dữ liệu, loại bỏ rác). Đây là lãnh địa của code thuần túy, nhanh và trực tiếp.
- **Gate 2 (Silver -> Gold):** Do **dbt** đảm nhiệm. Đây là điểm chốt chặn sinh tử trước khi dữ liệu lên mâm cho End-User.

## 4. Quyết định (Decision)
**QUYẾT ĐỊNH CHÍNH THỨC: GIỮ dbt-core (kết hợp dbt-duckdb).**

## 5. Lý do thực sự (The Real Rationale)
Việc nhắm mắt làm ngơ trước sự "cồng kềnh" của dbt và giữ nó lại hoàn toàn phục vụ cho mục đích của **Data Engineer (DE)**, cụ thể là 2 nhiệm vụ tối thượng:

1. **Giữ Hợp đồng Dữ liệu (Enforce Data Contracts) tại Gate 2:**
   - dbt test được sử dụng như một chốt chặn thép. Nó đảm bảo các quy tắc nghiệp vụ (Business Rules), tính nhất quán (Consistency), và không phá vỡ logic hệ thống.
   - Nếu Data Contract bị vi phạm (vd: Doanh thu âm, Mất Foreign Key), dbt sẽ làm fail pipeline (Halt DAG) ngay lập tức, bảo vệ Tầng Gold khỏi dữ liệu bẩn. Việc tự code lại ngần này test case bằng Python thuần là tái phát minh bánh xe lãng phí.

2. **Quản lý Phụ thuộc (Dependency Management):**
   - Thay vì phải tự viết code Python cực khổ để quản lý xem "Bảng A phải chạy trước Bảng B", dbt tự động biên dịch và xây dựng Đồ thị Phụ thuộc (DAG) cho các file SQL.
   - DE dùng dbt để duy trì trật tự execution, đảm bảo luồng data chảy từ Silver lên Gold không bị đứt gãy hay race condition.

## 6. Hệ quả (Consequences)
- dbt là công cụ nằm trong tay DE, dùng để bảo vệ hệ thống, **không phải** là công cụ mở rộng tràn lan cho DA tự do xào nấu Data Model.
- Chấp nhận trade-off: Chịu một chút overhead lúc compile Jinja, đổi lấy sự yên tâm tuyệt đối về Data Quality và Dependency.
