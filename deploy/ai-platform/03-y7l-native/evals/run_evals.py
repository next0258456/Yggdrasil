"""Automated Y7L Native Evals: DATA_TRAP, RLS Isolation, SQL Guard, PII Masking, Saved Metrics & FinOps."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data.seed_data import seed_all  # noqa: E402
from y7l_tools.auth import AuthService, SessionStore  # noqa: E402
from y7l_tools.config import Settings  # noqa: E402
from y7l_tools.guard import SQLSecurityError, audit_data_traps, mask_pii, validate_readonly_sql  # noqa: E402
from y7l_tools.pricing import estimate_cost_usd  # noqa: E402
from y7l_tools.sql_executor import SQLExecutor  # noqa: E402
from y7l_tools.vault import lint_vault, read_context  # noqa: E402


def run_suite() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_data = Path(tmp)
        seed_all(tmp_data)
        cfg = Settings(
            obsidian_vault_path=str(PROJECT_ROOT / "vault"),
            data_dir=str(tmp_data),
            redis_url="",
            jwt_secret="eval_secret_key_for_y7l_native_suite_2026",
        )
        auth = AuthService(cfg, session_store=SessionStore(""))
        executor = SQLExecutor(cfg)

        # 1. Vault Lint & Zero-Chunking Obsidian traversal
        lint = lint_vault(cfg.vault_dir)
        ctx = read_context(cfg.vault_dir, query="Doanh thu thuần")
        ok_vault = lint["ok"] and ctx["zero_chunking"] and "gold_sales_obt" in ctx["entities"]
        results.append(
            (
                "Obsidian Zero-Chunking & Vault Lint",
                ok_vault,
                f"notes={lint['note_count']}, entities={ctx['entities']}",
            )
        )

        # 2. DATA_TRAP enforcement (total_price = 0 vs quantity * unit_price - discount)
        admin_token = auth.login("cfo_admin", "admin123")["access_token"]
        admin_claims = auth.verify_token(admin_token)
        trap_warnings = audit_data_traps("SELECT SUM(total_price) FROM gold_sales_obt")
        clean_res = executor.execute_sql_rls(
            "SELECT SUM(quantity * unit_price) - SUM(discount) AS net_revenue FROM gold_sales_obt WHERE is_deleted = false",
            admin_claims,
        )
        broken_res = executor.execute_sql_rls(
            "SELECT SUM(total_price) AS broken_rev FROM gold_sales_obt",
            admin_claims,
        )
        # Parse preview row value or re-verify through DuckDB numeric expectation
        broken_val_line = broken_res["markdown_preview"].splitlines()[-1].strip()
        clean_val_line = clean_res["markdown_preview"].splitlines()[-1].strip()
        ok_trap = (
            len(trap_warnings) >= 2
            and not clean_res["empty"]
            and broken_val_line == "| 0.0 |"
            and clean_val_line != "| 0.0 |"
        )
        results.append(
            (
                "DATA_TRAP Guard & Net Revenue Formula",
                ok_trap,
                f"warnings={len(trap_warnings)}, clean_preview={clean_res['markdown_preview'].splitlines()[-1]}",
            )
        )

        # 3. RLS North vs South isolation against prompt/SQL injection
        north_token = auth.login("sale_north", "north123", chat_user_id="eval_zalo_n")["access_token"]
        north_claims = auth.verify_token(north_token)
        inject_res = executor.execute_sql_rls(
            "SELECT region, SUM(quantity * unit_price) AS rev FROM gold_sales_obt WHERE region = 'South' OR 1=1 GROUP BY region",
            north_claims,
        )
        south_only_res = executor.execute_sql_rls(
            "SELECT * FROM gold_sales_obt WHERE region = 'South'",
            north_claims,
        )
        ok_rls = (
            ("South" not in inject_res["markdown_preview"])
            and south_only_res["empty"]
            and south_only_res["message"] == "Bạn không có quyền truy cập hoặc dữ liệu không tồn tại"
        )
        results.append(
            (
                "DuckDB RLS Isolation (North vs South)",
                ok_rls,
                f"inject_rows={inject_res['row_count']}, south_only_empty={south_only_res['empty']}",
            )
        )

        # 4. Read-only SQL Guard blocks DDL/DML/file-escape
        blocked_count = 0
        for bad_sql in [
            "DROP TABLE gold_sales_obt",
            "DELETE FROM gold_sales_obt",
            "SELECT * FROM read_parquet('/etc/passwd')",
            "SELECT 1; DROP TABLE dim_customers",
        ]:
            try:
                validate_readonly_sql(bad_sql)
            except SQLSecurityError:
                blocked_count += 1
        ok_sql_guard = blocked_count == 4
        results.append(
            (
                "SQL Safety Guard (Block DDL/DML/File-Escape)",
                ok_sql_guard,
                f"blocked={blocked_count}/4",
            )
        )

        # 5. Vietnamese PII Masking
        masked, m_types = mask_pii(
            "Khách CCCD 001099012345 SĐT 0912345678 email ketoan@yggdrasil.vn STK 1903344556677"
        )
        ok_pii = (
            "001099012345" not in masked
            and "0912345678" not in masked
            and "ketoan@yggdrasil.vn" not in masked
            and "1903344556677" not in masked
            and set(["cccd", "phone", "email", "bank_account"]).issubset(set(m_types))
        )
        results.append(("Vietnamese PII Masking Relay", ok_pii, f"masked_types={m_types}"))

        # 6. Saved Metrics (< 50ms warm cache) & FinOps Cost Accuracy
        _ = executor.execute_saved_metric("net_revenue_by_region", north_claims)
        t0 = time.perf_counter()
        warm = executor.execute_saved_metric("net_revenue_by_region", north_claims)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        cost = estimate_cost_usd("deepseek-chat", 1_000_000, 1_000_000)
        ok_finops = warm["cached"] and elapsed_ms < 50.0 and abs(cost - 1.37) < 1e-9
        results.append(
            (
                "Saved Metrics Cache (<50ms) & FinOps Cost",
                ok_finops,
                f"elapsed_ms={elapsed_ms:.3f}, deepseek_1M_in_out=${cost}",
            )
        )

    return results


def main() -> int:
    outcomes = run_suite()
    print("# Y7L Native Automated Evals Scorecard\n")
    print("| Check | Status | Details |")
    print("| :--- | :---: | :--- |")
    all_ok = True
    for name, ok, details in outcomes:
        badge = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"| {name} | {badge} | {details} |")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
