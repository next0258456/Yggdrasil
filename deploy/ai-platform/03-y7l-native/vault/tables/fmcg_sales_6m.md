---
entity: fmcg_sales_6m
type: table
catalog: fmcg_sales_6m
rls_column: region
related:
  - "[[gold_sales_obt]]"
---

# Bảng Giao Dịch FMCG Lịch Sử 6,76 Triệu Dòng (`fmcg_sales_6m`)

Bảng dữ liệu giao dịch bán lẻ FMCG thực tế gồm **6.758.125 dòng** (Parquet ZSTD, trích xuất từ PostgreSQL `raw_db.sales`), gắn nối ngữ nghĩa cùng [[gold_sales_obt]]. Hệ thống DuckDB RLS tự động suy diễn cột `region` theo mã nhân viên bán hàng (`salesperson_id <= 12` $\to$ `'North'`, `salesperson_id > 12` $\to$ `'South'`).

## Danh mục cột

| Tên cột | Kiểu dữ liệu | Ý nghĩa | Ghi chú |
| :--- | :--- | :--- | :--- |
| `sales_id` | `BIGINT` | Mã giao dịch bán hàng | Khóa chính |
| `salesperson_id` | `BIGINT` | Mã nhân viên bán hàng (`1..23`) | `1..12` = `North`, `13..23` = `South` |
| `customer_id` | `BIGINT` | Mã khách hàng (`98.759` khách) | |
| `product_id` | `BIGINT` | Mã sản phẩm (`452` SKU) | |
| `quantity` | `BIGINT` | Số lượng bán (`1..25`) | |
| `discount` | `DOUBLE` | Tỷ lệ chiết khấu (`0.0..0.2`) | |
| `total_price` | `DOUBLE` | **CỘT LỖI — CẤM DÙNG** | Xem `DATA_TRAP` bên dưới |
| `sales_date` | `TIMESTAMP` | Thời điểm phát sinh đơn (`2018-01` – `2018-05`) | Có dòng `NULL`, xem `DATA_TRAP` |
| `transaction_number` | `VARCHAR` | Mã chứng từ 20 ký tự chữ-số | |
| `region` | `VARCHAR` | Khu vực suy diễn (`North`, `South`) | Cột lọc phân quyền dòng (RLS) |

> [!WARNING]
> **Cảnh Báo Bẫy Dữ Liệu (`DATA_TRAP`):**
> * `DATA_TRAP: total_price_zero` — Toàn bộ `6,758,125 / 6,758,125` dòng trong file gốc đều có `total_price = 0.0`. **Cấm dùng `SUM(total_price)`**; với dataset lịch sử chưa có đơn giá hãy tổng hợp sản lượng bằng `SUM(quantity)` và mức chiết khấu bình quân bằng `AVG(discount)`.
> * `DATA_TRAP: null_sales_date` — Có `67,526` dòng bị `sales_date IS NULL` (~1% dữ liệu bẩn). Bắt buộc thêm điều kiện `WHERE sales_date IS NOT NULL` khi nhóm hoặc thống kê theo ngày/tháng.
