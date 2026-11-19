---
entity: gold_sales_obt
type: table
catalog: gold_sales_obt
rls_column: region
related:
  - "[[dim_customers]]"
  - "[[Doanh_Thu_Thuan]]"
---

# Bảng Doanh Số Hợp Nhất (`gold_sales_obt`)

Bảng One-Big-Table tầng Gold lưu toàn bộ đơn hàng bán ra đã qua kiểm định hợp đồng dữ liệu. Liên kết chiều khách hàng qua [[dim_customers]] và định nghĩa nghiệp vụ [[Doanh_Thu_Thuan]].

## Danh mục cột

| Tên cột | Kiểu dữ liệu | Ý nghĩa | Ghi chú |
| :--- | :--- | :--- | :--- |
| `order_id` | `VARCHAR` | Mã đơn hàng | Khóa chính |
| `order_date` | `DATE` | Ngày ghi nhận đơn | Định dạng `YYYY-MM-DD` |
| `customer_id` | `VARCHAR` | Mã khách hàng | Khóa ngoại nối [[dim_customers]] |
| `region` | `VARCHAR` | Khu vực kinh doanh (`North`, `South`) | Cột lọc phân quyền dòng (RLS) |
| `product_name` | `VARCHAR` | Tên sản phẩm | |
| `quantity` | `BIGINT` | Số lượng bán | Đơn vị chiếc/gói |
| `unit_price` | `DOUBLE` | Đơn giá bán (VNĐ) | Chưa trừ chiết khấu |
| `discount` | `DOUBLE` | Chiết khấu đơn hàng (VNĐ) | |
| `total_price` | `DOUBLE` | **CỘT LỖI — CẤM DÙNG** | Xem cảnh báo `DATA_TRAP` bên dưới |
| `is_deleted` | `BOOLEAN` | Cờ đơn hàng đã hủy | Xem cảnh báo `DATA_TRAP` bên dưới |

> [!WARNING]
> **Cảnh Báo Bẫy Dữ Liệu (`DATA_TRAP`):**
> * `DATA_TRAP: total_price_zero` — Cột `total_price` bị lỗi hệ thống đồng bộ cũ nên chứa toàn số `0.0`. **Cấm dùng `SUM(total_price)`**; bắt buộc tính doanh thu bằng `SUM(quantity * unit_price)` và doanh thu thuần bằng `SUM(quantity * unit_price) - SUM(discount)`.
> * `DATA_TRAP: soft_delete` — Bảng lưu cả đơn hàng đã hủy (`is_deleted = true`). Bắt buộc luôn có điều kiện `WHERE is_deleted = false` trong mọi câu truy vấn thống kê doanh số.
