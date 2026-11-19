# Quy Trình Thuế Nhà Thầu (FCT) & Chốt Sổ Bill AI Cuối Kỳ

> Tài liệu tổng hợp ngắn gọn giúp **Kế toán** phân loại nghĩa vụ Thuế Nhà Thầu Nước Ngoài (FCT), cài MST lấy Invoice từ **Google AI Studio / OpenAI / Anthropic** và chốt sổ cuối kỳ khớp với `AI_Token_Ledger`.

---

## 1. Bước 0 — Phân Loại FCT Qua Cổng Nhà Cung Cấp Nước Ngoài (`etaxvn.gdt.gov.vn`)

Trước khi kê khai, tra tên **đúng pháp nhân ghi trên Invoice** tại `https://etaxvn.gdt.gov.vn/nccnn/Request` (**Tra cứu thông tin NCCNN**):

| Nền tảng AI | Pháp nhân & MST NCCNN (tham chiếu) | Nghĩa vụ Thuế Nhà Thầu (FCT) | Xử lý thuế & chứng từ |
| :--- | :--- | :--- | :--- |
| **Google AI Studio / Gemini API** | `Google Asia Pacific Pte. Ltd.`<br>MST NCCNN: `9000000415` | **Không nộp thay FCT** *(nếu Invoice ghi pháp nhân đã đăng ký NCCNN)* | Lưu Invoice thương mại + chứng từ thanh toán vào chi phí được trừ TNDN; **không** khấu trừ GTGT đầu vào *(không phải hóa đơn GTGT đỏ VN)*. |
| **OpenAI API** (`platform.openai.com`) | `OpenAI OpCo, LLC`<br>MST NCCNN: `9000013118` | **Không nộp thay FCT** nếu Invoice đúng pháp nhân đã đăng ký; **khai FCT** nếu phát sinh qua pháp nhân/gateway khác chưa đăng ký | Kiểm tra dòng pháp nhân + MST trên PDF Invoice mỗi kỳ; lưu chụp màn hình tra cứu `etaxvn` kèm hồ sơ. |
| **Anthropic API** (`Anthropic, PBC`) & NCC khác *(vd: DeepSeek)* | Chưa có tên trên cổng NCCNN *(tại thời điểm tra cứu)* | **Bắt buộc kê khai & nộp thay FCT** theo mẫu `01/NTNN` | Nộp thuế thay theo TT `103/2014/TT-BTC` & `80/2021/TT-BTC` trước khi hạch toán chi phí hợp lệ. |

---

## 2. Quy Trình Tính & Nộp Thuế Nhà Thầu (Với NCC Chưa Đăng Ký NCCNN)

Áp dụng khi mua API qua thẻ doanh nghiệp (**giá NET** — bên nước ngoài nhận đủ `100%` tiền):

1. **Tỷ lệ % tính thuế tham chiếu (Dịch vụ số / API / SaaS):**
   - **Thuế TNDN:** `5%`.
   - **Thuế GTGT:** `5%` *(hoặc `0%` nếu đủ hồ sơ xác định là dịch vụ phần mềm không chịu GTGT theo khoản 21 Điều 4 TT `219/2013/TT-BTC` — Kế toán trưởng chốt theo kỳ)*.
2. **Công thức Gross-up 2 bước (TT `103/2014/TT-BTC`, Điều 12 & 13):**
   - **Bước 1 (TNDN):** `DT_TNDN = Giá NET / (1 - 5%) = Giá NET / 0.95` → `Thuế TNDN = DT_TNDN × 5%`
   - **Bước 2 (GTGT, nếu chịu `5%`):** `DT_GTGT = DT_TNDN / (1 - 5%) = Giá NET / 0.9025` → `Thuế GTGT = DT_GTGT × 5%` *(nếu không chịu GTGT thì `Thuế GTGT = 0`)*
   - *Ví dụ nhanh bill NET `1,000 USD` (5% TNDN + 5% GTGT):* `DT_TNDN = 1,052.63 USD` → **Thuế TNDN = `52.63 USD`**; `DT_GTGT = 1,108.03 USD` → **Thuế GTGT = `55.40 USD`**.
3. **Kê khai (`Mẫu 01/NTNN` trên HTKK / eTax) & Thời hạn nộp:**
   - **Theo từng lần phát sinh:** Chậm nhất **ngày thứ 10** kể từ ngày thanh toán/chuyển tiền.
   - **Đăng ký khai theo tháng** *(khuyên dùng khi quẹt thẻ nhiều lần/tháng)*: Chậm nhất **ngày 20 của tháng tiếp theo**.
   - Thời hạn nộp tiền vào NSNN trùng với thời hạn nộp tờ khai.
4. **Hạch toán:** Thuế GTGT nhà thầu đã nộp (có giấy nộp tiền NSNN) được kê khai **khấu trừ đầu vào**; tiền API NET + phần thuế TNDN nộp thay được tính vào **chi phí được trừ TNDN**.

---

## 3. Quy Trình Cài MST & Tải Bill/Invoice Cuối Kỳ

> [!IMPORTANT]
> Phải cập nhật **Tên công ty, Địa chỉ ĐKKD và Mã số thuế (Tax ID)** trước khi đóng chu kỳ hóa đơn — hệ thống nước ngoài thường không sửa ngược lại Invoice của tháng đã phát hành.

| Nền tảng | Cài MST 1 lần (trước khi quẹt thẻ / chốt tháng) | Tải Bill cuối kỳ (ngày 1–5 tháng sau) |
| :--- | :--- | :--- |
| **Google AI Studio (Gemini API)**<br>*(qua Google Cloud Console)* | `https://console.cloud.google.com` → **Billing** (chọn đúng Billing Account của project AI Studio) → **Account management** / **Payments profile** → **Tax info (Vietnam)** → điền Tên công ty, Địa chỉ, **Tax ID (MST)** → **Save**. *(Có thể vào **Payment settings → Payments profile → Document language preference** chọn **Tiếng Việt** cho kỳ hóa đơn tiếp theo.)* | **Billing** → **Documents** (hoặc **Invoices**) tải PDF **Monthly Statement / Invoice**; vào **Transactions** tải **Payment Receipt** từng lần trừ thẻ. |
| **OpenAI API**<br>*(tách riêng với `chatgpt.com`)* | `https://platform.openai.com` → **Settings** → **Billing** → **Billing information** → nhập Tên công ty, Địa chỉ, **Tax ID (MST)**. | **Settings** → **Billing** → **Billing history** → tải PDF **Invoice** & **Receipt** từng giao dịch nạp/chốt tháng. |
| **Anthropic API** | `https://console.anthropic.com` → **Settings** → **Billing** → cập nhật Organization Name, Địa chỉ, **Tax / VAT ID**. | **Settings** → **Billing** → tải PDF **Invoice / Credit Purchase Receipt** (hoặc lấy từ email billing đã đăng ký). |

> [!TIP]
> **Dịch hóa đơn tiếng Anh (Khoản 5 Điều 5 Nghị định `174/2016/NĐ-CP`):** Doanh nghiệp **không bắt buộc công chứng dịch thuật**; chỉ cần tự dịch các nội dung chủ yếu (tên chứng từ, ngày, bên bán/bên mua, MST, dịch vụ, số tiền), người dịch ký rõ họ tên + công ty ký đóng dấu xác nhận và kẹp kèm PDF Invoice gốc.

---

## 4. Checklist 5 Chứng Từ Chốt Sổ Cuối Kỳ (`AI_Token_Ledger` ↔ Bill Thật)

Mỗi tháng (trước ngày `10`), Kế toán tập hợp đủ **5 chứng từ** cho từng nhà cung cấp:
1. **PDF Invoice / Statement** từ Google Cloud / OpenAI / Anthropic (hiển thị đủ Tên, Địa chỉ, MST công ty; kèm bản tự dịch tiếng Việt có ký đóng dấu doanh nghiệp nếu hóa đơn là tiếng Anh).
2. **Chứng từ thanh toán không dùng tiền mặt:** Sao kê thẻ tín dụng doanh nghiệp / UNC ngân hàng khớp số USD và tỷ giá quy đổi VNĐ thực tế.
3. **Bằng chứng hoàn thành nghĩa vụ thuế:** Ảnh chụp tra cứu hợp lệ trên `etaxvn.gdt.gov.vn` *(Google/OpenAI đã đăng ký NCCNN)* **HOẶC** Tờ khai `01/NTNN` + Giấy nộp tiền NSNN *(Anthropic / NCC nộp thay FCT)*.
4. **Bảng đối chiếu `FinOps_Dashboard` (`WF-06`):** Xuất Excel từ Google Sheet `AI_Token_Ledger`, đối khớp tổng tiền ước tính theo phòng ban/model với Bill thật (ghi chú chênh lệch làm tròn hoặc phí chuyển đổi ngoại tệ).
5. **Hồ sơ chứng minh phục vụ SXKD:** Tờ trình phê duyệt ngân sách AI & tài liệu vận hành nội bộ ([`03-y7l-native/HUONG_DAN_NGHIEP_VU.md`](./03-y7l-native/HUONG_DAN_NGHIEP_VU.md)).

*Lưu ý: Tài liệu mang tính tổng hợp quy trình vận hành nội bộ; Kế toán trưởng cần đối chiếu lại trạng thái NCCNN trên `etaxvn.gdt.gov.vn` và hướng dẫn của cơ quan thuế quản lý trực tiếp tại kỳ quyết toán.*
