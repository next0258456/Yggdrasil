---
entity: quy_trinh_hoan_don
type: sop
doc_code: SOP-FIN-001
department: finance
---

# Quy Trình Xử Lý Hoàn Đơn & Trả Hàng (`SOP-FIN-001`)

## 1. Thời hạn tiếp nhận (SLA)
- Khách hàng được quyền yêu cầu hoàn đơn hoặc trả hàng trong vòng **7 ngày** kể từ ngày xuất hóa đơn (SLA tiếp nhận và phản hồi tối đa 7 ngày).
- Yêu cầu quá 7 ngày phải có xác nhận ngoại lệ từ Giám đốc Kinh doanh khu vực.

## 2. Thẩm quyền phê duyệt theo giá trị
- Đơn hoàn có giá trị **từ 5.000.000 VNĐ trở xuống**: Trưởng nhóm Sale khu vực phê duyệt trên hệ thống và chuyển Kế toán viên đối soát.
- Đơn hoàn có giá trị **trên 5.000.000 VNĐ (> 5,000,000 VND)**: **Bắt buộc phải có phê duyệt của Kế toán trưởng (Chief Accountant)** kèm biên bản xác nhận nhập kho trước khi giải ngân hoàn tiền.

## 3. Lưu ý hạch toán
- Mọi đơn hoàn được phê duyệt sẽ đánh dấu cờ `is_deleted = true` trong bảng `gold_sales_obt` ở kỳ đối soát cuối ngày.
