"""Unit tests for Safety Relay guardrails: PII masking, SQL guard, and DATA_TRAP auditing."""

from __future__ import annotations

import pytest

from y7l_tools.guard import (
    SQLSecurityError,
    audit_data_traps,
    mask_pii,
    validate_readonly_sql,
)


def test_mask_pii_vietnamese_entities() -> None:
    text = (
        "Khách Nguyễn Văn A, CCCD 001099012345, SĐT 0912345678 hoặc +84987654321, "
        "email ketoan@yggdrasil.vn, STK 1903344556677."
    )
    masked, types = mask_pii(text)

    assert "001099012345" not in masked
    assert "0912345678" not in masked
    assert "+84987654321" not in masked
    assert "ketoan@yggdrasil.vn" not in masked
    assert "1903344556677" not in masked
    assert "[REDACTED_CCCD]" in masked
    assert "[REDACTED_PHONE]" in masked
    assert "[REDACTED_EMAIL]" in masked
    assert "[REDACTED_BANK_ACCOUNT]" in masked
    assert set(types) == {"bank_account", "email", "phone", "cccd"}


def test_validate_readonly_sql_allows_select_and_with() -> None:
    sql_select = "```sql\nSELECT region, SUM(quantity * unit_price) FROM gold_sales_obt WHERE is_deleted = false GROUP BY region;\n```"
    clean = validate_readonly_sql(sql_select)
    assert clean.startswith("SELECT region")
    assert not clean.endswith(";")

    sql_cte = "WITH agg AS (SELECT customer_id, SUM(quantity * unit_price) AS rev FROM gold_sales_obt WHERE is_deleted = false GROUP BY 1) SELECT * FROM agg"
    assert validate_readonly_sql(sql_cte).startswith("WITH agg")


def test_validate_readonly_sql_ignores_keywords_inside_literals() -> None:
    sql = "SELECT * FROM gold_sales_obt WHERE product_name != 'DROP TABLE' AND is_deleted = false"
    assert validate_readonly_sql(sql).startswith("SELECT * FROM gold_sales_obt")


@pytest.mark.parametrize(
    "bad_sql",
    [
        "",
        "DROP TABLE gold_sales_obt",
        "DELETE FROM gold_sales_obt WHERE 1=1",
        "UPDATE gold_sales_obt SET total_price = 100",
        "INSERT INTO dim_customers VALUES ('X', 'Y', 'SMB', 'North')",
        "SELECT * FROM read_parquet('/etc/passwd')",
        "COPY gold_sales_obt TO '/tmp/leak.csv'",
        "SELECT 1; DROP TABLE gold_sales_obt",
        "PRAGMA show_tables",
    ],
)
def test_validate_readonly_sql_blocks_mutations_and_escapes(bad_sql: str) -> None:
    with pytest.raises(SQLSecurityError):
        validate_readonly_sql(bad_sql)


def test_audit_data_traps_flags_violations() -> None:
    warnings = audit_data_traps("SELECT SUM(total_price) FROM gold_sales_obt")
    assert any("total_price_zero" in w for w in warnings)
    assert any("soft_delete" in w for w in warnings)

    clean_warnings = audit_data_traps(
        "SELECT SUM(quantity * unit_price) - SUM(discount) FROM gold_sales_obt WHERE is_deleted = false"
    )
    assert clean_warnings == []
