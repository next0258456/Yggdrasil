# Tầng 5: Thiết Kế Cổng Giao Tiếp AI & Điều Phối (AI Gateway & Orchestration Layer) - Mimir

## 1. Tầm Nhìn & Triết Lý Sản Phẩm (Mimir's Product Vision)
Mimir không phải là một công cụ sinh ra để thay thế nhân sự hay tự động hóa một cách máy móc. Đây là giải pháp **giải phóng sức lao động** và **trao quyền chủ động**. Việc phát triển Mimir luôn bám sát 3 định hướng cốt lõi dành cho 3 nhóm đối tượng:

> **1. Với Lãnh đạo (C-Level):** *"Mimir ra đời để Lãnh đạo có quyền chủ động nắm bắt số liệu tức thời. Bất kể là 11 giờ đêm hay ngày nghỉ, C-level không còn phải chờ đợi hay gọi điện hối thúc Kế toán trưởng chỉ vì một báo cáo doanh thu đột xuất."*

> **2. Với Khối Back-office (Kế toán / Phân tích):** *"Trả lại giá trị thực cho Kế toán: Họ là những chuyên gia phân tích tài chính và quản trị rủi ro, không phải là những 'thợ gõ Excel' hay nhân viên nhập liệu thủ công."*

> **3. Với Khối Tiền tuyến (Frontline Sales):** *"Trang bị 'vũ khí thông tin' theo thời gian thực cho Sale: Bỏ qua những cuộc gọi kiểm tra tồn kho hay hỏi công nợ rườm rà, Sale có thể chốt deal ngay lập tức khi đứng trước mặt khách hàng chỉ bằng một tin nhắn Zalo."*

**Triết lý:** Mimir đóng vai trò là "Cổng thông tin" tự động hóa mọi truy xuất. Thay vì Kế toán hay Data Analyst phải tiêu tốn hàng giờ đồng hồ để đối chiếu biểu mẫu, hay Sale phải chờ đợi kho xác nhận hàng, Mimir giải quyết tất cả trong 3 giây. Từ đó, bộ phận Kế toán/Tài chính được giải phóng để phân tích chiến lược, còn Sale được dồn 100% tốc độ cho việc mang tiền về công ty.

## 2. Tổng Quan Tầng 5
Tầng 5 là lớp tương tác trực tiếp với người dùng cuối (End-users) thông qua giao diện Chat (Zalo Official Account). Tầng này không trực tiếp lưu trữ dữ liệu mà đóng vai trò như một **AI Gateway (Cổng thông minh - Mimir)** và **Identity Broker (Người môi giới danh tính)**, chịu trách nhiệm điều phối luồng giao tiếp giữa người dùng, Tầng Ngữ nghĩa (AI Context) và Tầng Trình diễn (Superset).

### 2.1. Tại sao lại là Chat Interface (Zalo)?
Đây là sự thấu cảm sâu sắc về môi trường làm việc. Sếp và Kế toán ngồi văn phòng có PC/Laptop, họ có thể mở Superset, PowerBI, Excel bất cứ lúc nào. Nhưng **Khối Sale tiền tuyến thì chỉ có một chiếc điện thoại di động**. 
Việc bắt Sale phải mở một Dashboard PowerBI chằng chịt biểu đồ trên màn hình 6-inch giữa lúc đang đứng ở kho khách hàng là một thảm họa UX (Trải nghiệm người dùng). 
Do đó, **Chat (Zalo)** chính là giao diện tối thượng. Mimir biến những truy vấn phức tạp của Data Warehouse thành một câu trả lời ngắn gọn, hoặc một ảnh biểu đồ trực quan gửi thẳng vào Zalo – công cụ mà Sale dùng 24/7. Nó là "dặm cuối" (Last-mile) mang dữ liệu đến tận tay người ra chiến trường.

Công cụ lõi đảm nhận Tầng 5 là **n8n** (Đóng vai trò Orchestrator & Webhook Server).

## 3. Kiến Trúc Xác Thực Zalo - Superset (Zalo-Webview Pattern)
Vấn đề cốt lõi của Tầng 5 là làm sao ánh xạ (mapping) được người dùng Zalo với danh tính người dùng trong cơ sở dữ liệu Superset một cách bảo mật tuyệt đối, đảm bảo tuân thủ Row-Level Security (RLS).

### 3.1. Hạn Chế Của Nền Tảng Chat
Theo đặc tính của Zalo Open API, Zalo Official Account không có quyền xóa hoặc thu hồi tin nhắn do người dùng gửi tới. Việc yêu cầu người dùng gõ Mật khẩu (Password) hoặc OTP trực tiếp vào khung chat sẽ dẫn đến nguy cơ lộ lọt thông tin vĩnh viễn trên thiết bị.

### 3.2. Giải Pháp Authentication Bằng Webhook Webview
Hệ thống sử dụng cơ chế "Out-of-band Authentication" (Xác thực ngoài luồng) qua In-App Browser của Zalo:
1. **Kiểm tra Session:** Khi người dùng Zalo ra lệnh truy vấn dữ liệu, n8n kiểm tra token (JWT) gắn với \Zalo_User_ID\. Nếu Token hết hạn hoặc chưa tồn tại, luồng bị chặn.
2. **Gửi Interactive Button:** n8n gọi Zalo API gửi một tin nhắn dạng Template kèm nút bấm (CTA Button): \[ 🔑 Bấm vào đây để Đăng Nhập ]\.
3. **Mở Webview Kín:** Nút bấm chứa đường link trỏ về một endpoint Webhook của n8n (VD: \https://n8n.domain.com/webhook/login-form?uid=<Zalo_User_ID>\). Zalo sẽ mở link này bằng trình duyệt nội bộ (In-App Browser) lướt đè lên khung chat.
4. **Nhập liệu An toàn:** n8n Webhook trả về một giao diện HTML Form tiêu chuẩn. Người dùng nhập \Username\ và \Password\ của hệ thống Superset. Giao diện này mã hóa password (\***\).
5. **Trao đổi Token (Token Exchange):** Form submit dữ liệu qua HTTPS POST về một Webhook xử lý của n8n.
   - n8n cầm Username/Password gõ cửa API \/api/v1/security/login\ của Superset.
   - Superset trả về \Access Token\ và \Refresh Token\.
   - n8n **hủy bỏ Password ngay lập tức**, chỉ lưu trữ Token và ánh xạ nó với \Zalo_User_ID\ vào Database bảo mật (Postgres hoặc Redis).
6. **Đóng Webview:** n8n trả về giao diện HTML thông báo thành công. Người dùng tắt trình duyệt và quay lại chat bình thường.

## 4. Luồng Cấp Phát Tài Khoản (IAM Provisioning) & Cơ Chế Kill Switch

Phân quyền tập trung và khả năng thu hồi quyền truy cập khẩn cấp là cốt lõi của Zero Trust.

### 4.1. Cấp Phát Tài Khoản (Tuyệt đối không lưu Password ở Google Sheet)
Hệ thống sử dụng một Master IAM (Google Sheet hoặc HR System) CHỈ ĐỂ quản lý định danh nhân sự (Ví dụ: Số điện thoại -> Phòng ban).
- Khi có nhân sự mới, n8n phát hiện bản ghi mới.
- n8n tự động sinh một mật khẩu ngẫu nhiên trên RAM (In-memory).
- n8n gọi API Superset tạo User mới và truyền mật khẩu này vào.
- n8n bắn thẳng mật khẩu này qua Zalo/Email cho nhân viên dưới dạng tin nhắn **One-Time (Dùng 1 lần để login qua Webview)**.
- **Ràng buộc Sinh tử:** Ngay sau khi bắn tin nhắn, n8n TIÊU HỦY mật khẩu khỏi RAM. Mật khẩu không bao giờ được ghi xuống bất kỳ Database hay Google Sheet nào. Bản đồ ánh xạ giữa Zalo_User_ID và Superset_Token sẽ được n8n lưu vào **Redis hoặc Postgres**, nghiêm cấm lưu trữ Token/Mật khẩu trên Google Sheet (vì nguy cơ rò rỉ bảo mật nội bộ).

### 4.2. Cơ chế Kill Switch (Khóa Khẩn Cấp)
Để đối phó với tình huống nhân viên nghỉ việc hoặc làm mất điện thoại, hệ thống có một công tắc tử thần (Kill Switch):
1. **Kích hoạt:** HR chuyển trạng thái nhân sự thành Inactive trên Master IAM.
2. **Cắt cầu Mimir:** n8n ngay lập tức vô hiệu hóa Zalo_User_ID trong danh sách trắng (Whitelist). Mimir Bot từ chối mọi tin nhắn từ thiết bị này.
3. **Cắt cầu Superset:** n8n gọi API Superset đổi trạng thái is_active = False của tài khoản đó, đồng thời xóa sạch Token đang lưu trong Redis.
Toàn bộ quá trình cắt quyền diễn ra dưới 1 phút, đảm bảo kẻ xấu cầm điện thoại cũng không thể tương tác với Data Platform.
## 5. Kiến Trúc "Hybrid AI" Trong Xử Lý Truy Vấn (Query Orchestration)
Để giải quyết bài toán mâu thuẫn giữa "Độ chính xác tuyệt đối" (BI) và "Khả năng linh hoạt" (AI), Mimir hoạt động theo cơ chế **Lai (Hybrid)**. Hệ thống không ép LLM phải chọn một phương pháp duy nhất mà kết hợp cả hai:

### 5.1. Luồng Ưu Tiên (Happy Path): Intent Router (Bộ định tuyến ý định)
- **Kích hoạt khi:** Câu hỏi liên quan đến các chỉ số kinh doanh cốt lõi (KPI, Doanh thu thuần, Công nợ, Tỷ lệ chuyển đổi) đã được Data Analyst chuẩn hóa thành các **Saved Metrics** trong giao diện Superset.
- **Hoạt động:** Mimir (LLM) đối chiếu ý định của người dùng với thư viện công cụ (Tool Calling). Khi phát hiện trùng khớp, nó KHÔNG sinh ra câu lệnh SQL. Nó chỉ biên dịch các tham số (Ví dụ: Thời gian = Tháng 10, Khu vực = Miền Bắc) và gọi thẳng API của Superset để lấy biểu đồ/số liệu.
- **Ưu điểm:** Đảm bảo Source of Truth chính xác 100%, không bao giờ có hiện tượng Ảo giác (Hallucination) do AI tự chế công thức.

### 5.2. Luồng Linh Hoạt (Fallback Path): Text-to-SQL (Tự sinh truy vấn)
- **Kích hoạt khi:** Người dùng hỏi những câu mang tính chất khám phá, ngẫu hứng (Ad-hoc) mà đội Data chưa kịp xây dựng sẵn Metric trên Superset.
- **Hoạt động:** Mimir sẽ chọc vào Tầng 4 (Obsidian) để lôi ra các định nghĩa, cạm bẫy dữ liệu (Data Traps) và lược đồ bảng (OBT Layer Gold). Dựa vào ngữ cảnh này, LLM tự động viết ra câu lệnh truy vấn SQL thô.
- **Bảo mật tuyệt đối (Zero Trust):** Câu lệnh SQL do AI sinh ra KHÔNG ĐƯỢC CHẠY TRỰC TIẾP vào CSDL. n8n sẽ đẩy câu lệnh SQL này qua cổng API **SQL Lab của Superset**, đính kèm theo JWT Token của chính người dùng đó. Superset sẽ tự động kẹp luật Row-Level Security (RLS) vào trước khi giao cho DuckDB tính toán. Nhờ vậy, AI không bao giờ vượt quyền được danh tính của người dùng thực.

