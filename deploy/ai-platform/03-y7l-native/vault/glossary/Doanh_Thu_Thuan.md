---
entity: Doanh_Thu_Thuan
type: glossary
owner: ke_toan_truong
related:
  - "[[gold_sales_obt]]"
  - "[[dim_customers]]"
---

# Doanh Thu Thuần (Net Revenue)

## Định nghĩa nghiệp vụ
**Doanh thu thuần** là tổng giá trị bán hàng sau khi trừ chiết khấu thương mại, tính trên các đơn hàng hợp lệ chưa bị hủy.

## Công thức chuẩn
```sql
SUM(quantity * unit_price) - SUM(discount)
```
Với điều kiện bắt buộc:
- `WHERE is_deleted = false`
- Bảng nguồn: [[gold_sales_obt]]
- Bảng khách hàng liên kết: [[dim_customers]]

## Ghi chú cho AI
- Không được lấy cột `total_price` vì cột này đang bị lỗi hệ thống (toàn số `0`).
- Phải để Superset / DuckDB tự áp dụng Row-Level Security theo cột `region` của người dùng đăng nhập.
