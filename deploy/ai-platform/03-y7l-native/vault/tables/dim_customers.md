---
entity: dim_customers
type: table
catalog: dim_customers
rls_column: region
related:
  - "[[gold_sales_obt]]"
---

# Bảng Chiều Khách Hàng (`dim_customers`)

Danh mục khách hàng doanh nghiệp & đại lý theo khu vực, dùng để nối với bảng [[gold_sales_obt]] theo khóa `customer_id`.

## Danh mục cột

| Tên cột | Kiểu dữ liệu | Ý nghĩa | Ghi chú |
| :--- | :--- | :--- | :--- |
| `customer_id` | `VARCHAR` | Mã khách hàng | Khóa chính |
| `customer_name` | `VARCHAR` | Tên công ty / đại lý | |
| `segment` | `VARCHAR` | Phân khúc (`Enterprise`, `SMB`, `Retail`) | |
| `region` | `VARCHAR` | Khu vực quản lý (`North`, `South`) | Cột lọc phân quyền dòng (RLS) |

> [!WARNING]
> **Cảnh Báo Bẫy Dữ Liệu (`DATA_TRAP`):**
> * `DATA_TRAP: test_accounts` — Hệ thống có bản ghi kiểm thử nội bộ với tiền tố `TEST_` (ví dụ `TEST_001`). Khi báo cáo khách hàng thực tế, bắt buộc lọc `customer_id NOT LIKE 'TEST_%'`.
