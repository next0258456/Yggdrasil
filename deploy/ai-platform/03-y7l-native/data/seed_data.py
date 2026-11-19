"""Idempotent seed script generating Parquet datasets and PBKDF2-hashed IAM users for 03-y7l-native."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path

import duckdb


def hash_password(password: str, salt: str | None = None) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 using an explicit salt."""
    effective_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        effective_salt.encode("utf-8"),
        200_000,
    ).hex()
    return f"pbkdf2_sha256$200000${effective_salt}${digest}"


def seed_all(data_dir: Path | None = None) -> dict[str, Path]:
    """Generate deterministic gold_sales_obt.parquet, dim_customers.parquet, and sample_iam_users.json."""
    target_dir = data_dir or Path(__file__).resolve().parent
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "exports").mkdir(parents=True, exist_ok=True)

    sales_path = target_dir / "gold_sales_obt.parquet"
    customers_path = target_dir / "dim_customers.parquet"
    iam_path = target_dir / "sample_iam_users.json"

    con = duckdb.connect(":memory:")
    try:
        con.execute(
            """
            CREATE TABLE dim_customers AS
            SELECT * FROM (
                VALUES
                    ('CUS_N01', 'Công ty TNHH Hà Nội Tech', 'Enterprise', 'North'),
                    ('CUS_N02', 'Đại lý Hải Phòng Mart', 'SMB', 'North'),
                    ('CUS_N03', 'Công ty CP Bắc Ninh Logistics', 'Enterprise', 'North'),
                    ('CUS_S01', 'Công ty TNHH Sài Gòn Retail', 'Enterprise', 'South'),
                    ('CUS_S02', 'Đại lý Cần Thơ Food', 'SMB', 'South'),
                    ('CUS_S03', 'Công ty CP Bình Dương Packaging', 'Retail', 'South'),
                    ('TEST_001', 'Tài khoản Kiểm thử Nội bộ', 'Internal', 'North')
            ) AS t(customer_id, customer_name, segment, region)
            """
        )

        # Every row sets total_price = 0.0 to simulate the legacy ETL DATA_TRAP,
        # and each region includes 2 soft-deleted rows (is_deleted = true).
        con.execute(
            """
            CREATE TABLE gold_sales_obt AS
            SELECT * FROM (
                VALUES
                    ('ORD_N001', DATE '2026-10-03', 'CUS_N01', 'North', 'Gói Enterprise Lakehouse', 10, 15000000.0, 5000000.0, 0.0, false),
                    ('ORD_N002', DATE '2026-10-12', 'CUS_N02', 'North', 'Thiết bị POS Mini', 25, 4200000.0, 2000000.0, 0.0, false),
                    ('ORD_N003', DATE '2026-11-05', 'CUS_N01', 'North', 'Module Mở rộng BI', 5, 12000000.0, 0.0, 0.0, false),
                    ('ORD_N004', DATE '2026-11-11', 'CUS_N03', 'North', 'Cảm biến Kho lạnh', 40, 2500000.0, 3000000.0, 0.0, false),
                    ('ORD_N005', DATE '2026-11-14', 'CUS_N02', 'North', 'Thiết bị POS Mini (Hủy)', 10, 4200000.0, 0.0, 0.0, true),
                    ('ORD_N006', DATE '2026-11-15', 'TEST_001', 'North', 'Đơn Kiểm thử Nội bộ (Hủy)', 1, 99900000.0, 0.0, 0.0, true),

                    ('ORD_S001', DATE '2026-10-08', 'CUS_S01', 'South', 'Gói Enterprise Lakehouse', 12, 15000000.0, 6000000.0, 0.0, false),
                    ('ORD_S002', DATE '2026-10-20', 'CUS_S02', 'South', 'Phần mềm Quản lý Kho', 8, 9500000.0, 1000000.0, 0.0, false),
                    ('ORD_S003', DATE '2026-11-06', 'CUS_S03', 'South', 'Thiết bị Quét Mã vạch', 50, 1800000.0, 2000000.0, 0.0, false),
                    ('ORD_S004', DATE '2026-11-16', 'CUS_S01', 'South', 'Module Mở rộng BI', 6, 12000000.0, 0.0, 0.0, false),
                    ('ORD_S005', DATE '2026-11-17', 'CUS_S02', 'South', 'Phần mềm Quản lý Kho (Hủy)', 4, 9500000.0, 0.0, 0.0, true),
                    ('ORD_S006', DATE '2026-11-18', 'CUS_S03', 'South', 'Thiết bị Quét Mã vạch (Hủy)', 15, 1800000.0, 0.0, 0.0, true)
            ) AS t(order_id, order_date, customer_id, region, product_name, quantity, unit_price, discount, total_price, is_deleted)
            """
        )

        sales_sql_path = sales_path.as_posix().replace("'", "''")
        customers_sql_path = customers_path.as_posix().replace("'", "''")
        con.execute(f"COPY gold_sales_obt TO '{sales_sql_path}' (FORMAT PARQUET)")
        con.execute(f"COPY dim_customers TO '{customers_sql_path}' (FORMAT PARQUET)")
    finally:
        con.close()

    users = [
        {
            "username": "sale_north",
            "password_hash": hash_password("north123", salt="y7l_salt_north"),
            "department": "sales",
            "region": "North",
            "role": "sales",
            "is_active": True,
        },
        {
            "username": "sale_south",
            "password_hash": hash_password("south123", salt="y7l_salt_south"),
            "department": "sales",
            "region": "South",
            "role": "sales",
            "is_active": True,
        },
        {
            "username": "accountant_01",
            "password_hash": hash_password("fin123", salt="y7l_salt_fin"),
            "department": "finance",
            "region": "*",
            "role": "analyst",
            "is_active": True,
        },
        {
            "username": "cfo_admin",
            "password_hash": hash_password("admin123", salt="y7l_salt_admin"),
            "department": "executive",
            "region": "*",
            "role": "admin",
            "is_active": True,
        },
    ]
    iam_path.write_text(json.dumps({"users": users}, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "gold_sales_obt": sales_path,
        "dim_customers": customers_path,
        "sample_iam_users": iam_path,
    }


if __name__ == "__main__":
    data_root = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent))
    outputs = seed_all(data_root)
    for name, path in outputs.items():
        print(f"Seeded {name}: {path}")
