"""Safety Relay: Vietnamese PII masking, read-only SQL guard, and DATA_TRAP auditing."""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_BANK_ACCOUNT_RE = re.compile(
    r"(?i)\b(stk|số\s+tài\s+khoản|so\s+tai\s+khoan|tài\s+khoản|tai\s+khoan|account(?:\s+no\.?|\s+number)?)\s*([:#\-]?)\s*(\d{9,16})\b"
)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+84|0)(?:3|5|7|8|9)\d{8}(?!\d)")
_CCCD_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")

_FORBIDDEN_SQL_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "COPY",
    "ATTACH",
    "DETACH",
    "INSTALL",
    "LOAD",
    "PRAGMA",
    "EXPORT",
    "READ_PARQUET",
    "READ_CSV",
    "READ_CSV_AUTO",
    "READ_JSON",
    "READ_JSON_AUTO",
    "GLOB",
    "HTTPFS",
    "CALL",
    "SET",
    "VACUUM",
    "MERGE",
    "REPLACE",
}


class SQLSecurityError(ValueError):
    """Raised when generated or supplied SQL violates read-only or single-statement policy."""


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Mask Vietnamese PII (bank accounts, emails, phone numbers, 12-digit CCCD)."""
    masked_types: list[str] = []

    def _mask_bank(match: re.Match[str]) -> str:
        masked_types.append("bank_account")
        prefix = match.group(1)
        sep = match.group(2)
        spacer = " " if not sep else f"{sep} "
        return f"{prefix}{spacer}[REDACTED_BANK_ACCOUNT]"

    result = _BANK_ACCOUNT_RE.sub(_mask_bank, text)

    if _EMAIL_RE.search(result):
        masked_types.append("email")
        result = _EMAIL_RE.sub("[REDACTED_EMAIL]", result)

    if _PHONE_RE.search(result):
        masked_types.append("phone")
        result = _PHONE_RE.sub("[REDACTED_PHONE]", result)

    if _CCCD_RE.search(result):
        masked_types.append("cccd")
        result = _CCCD_RE.sub("[REDACTED_CCCD]", result)

    # Deduplicate while preserving order.
    unique_types = list(dict.fromkeys(masked_types))
    return result, unique_types


def _strip_sql_fences(sql: str) -> str:
    cleaned = sql.strip()
    fence_match = re.match(r"^```(?:sql)?\s*(.*?)\s*```$", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    return cleaned


def _strip_comments_and_literals(sql: str) -> tuple[str, str]:
    """Return (comment-stripped SQL, uppercase code with string literals blanked out)."""
    out_raw: list[str] = []
    out_unquoted: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        # Line comment
        if ch == "-" and nxt == "-":
            while i < n and sql[i] != "\n":
                i += 1
            out_raw.append(" ")
            out_unquoted.append(" ")
            continue

        # Block comment
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            out_raw.append(" ")
            out_unquoted.append(" ")
            continue

        # Single-quoted string literal
        if ch == "'":
            start = i
            i += 1
            while i < n:
                if sql[i] == "'" and i + 1 < n and sql[i + 1] == "'":
                    i += 2
                    continue
                if sql[i] == "'":
                    i += 1
                    break
                i += 1
            out_raw.append(sql[start:i])
            out_unquoted.append(" '' ")
            continue

        # Double-quoted identifier
        if ch == '"':
            start = i
            i += 1
            while i < n:
                if sql[i] == '"' and i + 1 < n and sql[i + 1] == '"':
                    i += 2
                    continue
                if sql[i] == '"':
                    i += 1
                    break
                i += 1
            ident = sql[start:i]
            out_raw.append(ident)
            out_unquoted.append(ident)
            continue

        out_raw.append(ch)
        out_unquoted.append(ch)
        i += 1

    return "".join(out_raw).strip(), "".join(out_unquoted).strip()


def validate_readonly_sql(sql: str) -> str:
    """Validate that SQL is a single read-only SELECT or WITH query without escape functions."""
    stripped = _strip_sql_fences(sql)
    if not stripped:
        raise SQLSecurityError("SQL query must not be empty.")

    raw_no_comments, unquoted = _strip_comments_and_literals(stripped)
    if raw_no_comments.endswith(";"):
        raw_no_comments = raw_no_comments[:-1].strip()
    if unquoted.endswith(";"):
        unquoted = unquoted[:-1].strip()

    if ";" in unquoted:
        raise SQLSecurityError("Multiple SQL statements are forbidden.")

    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", unquoted.upper())
    if not tokens or tokens[0] not in {"SELECT", "WITH"}:
        raise SQLSecurityError("Only single SELECT or WITH read-only queries are allowed.")

    for tok in tokens:
        if tok in _FORBIDDEN_SQL_KEYWORDS:
            raise SQLSecurityError(f"Forbidden SQL keyword detected: {tok}")

    return raw_no_comments


def audit_data_traps(sql: str) -> list[str]:
    """Check validated SQL against documented Obsidian DATA_TRAP rules."""
    _, unquoted = _strip_comments_and_literals(sql)
    upper = unquoted.upper()
    warnings: list[str] = []

    if "GOLD_SALES_OBT" in upper:
        if re.search(r"\bTOTAL_PRICE\b", upper):
            warnings.append(
                "DATA_TRAP: total_price_zero — Cột total_price bằng 0; hãy dùng SUM(quantity * unit_price)."
            )
        if not re.search(r"\bIS_DELETED\b", upper):
            warnings.append(
                "DATA_TRAP: soft_delete — Thiếu điều kiện lọc WHERE is_deleted = false."
            )

    if "DIM_CUSTOMERS" in upper and "TEST_" not in upper:
        warnings.append(
            "DATA_TRAP: test_accounts — Khuyến nghị loại tài khoản kiểm thử bằng customer_id NOT LIKE 'TEST_%'."
        )

    if "FMCG_SALES_6M" in upper:
        if re.search(r"\bTOTAL_PRICE\b", upper):
            warnings.append(
                "DATA_TRAP: total_price_zero — Toàn bộ 6,758,125 dòng fmcg_sales_6m có total_price = 0.0; cấm dùng SUM(total_price)."
            )
        if re.search(r"\bSALES_DATE\b", upper) and "IS NOT NULL" not in upper and "IS NULL" not in upper:
            warnings.append(
                "DATA_TRAP: null_sales_date — Có 67,526 dòng bị sales_date IS NULL (~1%); bắt buộc lọc WHERE sales_date IS NOT NULL."
            )

    return warnings
