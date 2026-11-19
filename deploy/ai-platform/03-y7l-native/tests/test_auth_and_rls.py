"""Tests for 10h JWT Auth, 2-tier Kill-Switch, DuckDB RLS isolation, DATA_TRAPs & exports."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from openpyxl import load_workbook

from data.seed_data import seed_all
from y7l_tools.auth import AuthError, AuthService, SessionStore
from y7l_tools.config import Settings
from y7l_tools.sql_executor import SQLExecutor


@pytest.fixture()
def sandbox(tmp_path: Path) -> tuple[Settings, AuthService, SQLExecutor]:
    data_dir = tmp_path / "data"
    seed_all(data_dir)
    cfg = Settings(
        obsidian_vault_path=str(Path(__file__).resolve().parents[1] / "vault"),
        data_dir=str(data_dir),
        redis_url="",
        jwt_secret="unit_test_secret_for_y7l_native_2026",
        jwt_ttl_seconds=36000,
    )
    store = SessionStore("")
    auth = AuthService(cfg, session_store=store)
    executor = SQLExecutor(cfg)
    return cfg, auth, executor


def test_login_issues_10h_jwt_and_never_stores_password(sandbox) -> None:
    _, auth, _ = sandbox
    res = auth.login("sale_north", "north123", chat_user_id="zalo_north_1")

    assert res["expires_in"] == 36000
    assert res["user"]["region"] == "North"
    assert "password" not in str(res["user"]).lower()
    claims = auth.verify_token(res["access_token"])
    assert claims["exp"] - claims["iat"] == 36000
    assert claims["region"] == "North"
    assert auth.session_store.get_session("zalo_north_1") == res["access_token"]


def test_two_tier_kill_switch(sandbox) -> None:
    _, auth, _ = sandbox
    login_res = auth.login("sale_north", "north123", chat_user_id="zalo_north_kill")
    token = login_res["access_token"]

    # Tier 1: revoke session only -> session cleared, user can still verify/re-login
    tier1 = auth.revoke_session("zalo_north_kill")
    assert tier1["session_removed"] is True
    assert auth.session_store.get_session("zalo_north_kill") is None
    assert auth.verify_token(token)["username"] == "sale_north"

    # Re-login then trigger Tier 2: deactivate user -> session purged AND existing JWT rejected
    login_res2 = auth.login("sale_north", "north123", chat_user_id="zalo_north_kill")
    token2 = login_res2["access_token"]
    tier2 = auth.deactivate_user("sale_north")
    assert tier2["is_active"] is False
    assert auth.session_store.get_session("zalo_north_kill") is None

    with pytest.raises(AuthError) as exc_info:
        auth.verify_token(token2)
    assert exc_info.value.status_code == 403


def test_duckdb_rls_isolation_blocks_cross_region_injection(sandbox) -> None:
    cfg, auth, executor = sandbox
    north_token = auth.login("sale_north", "north123")["access_token"]
    north_claims = auth.verify_token(north_token)

    # Injection attempt trying to read South rows via OR 1=1
    inject_res = executor.execute_sql_rls(
        "SELECT order_id, region FROM gold_sales_obt WHERE region = 'South' OR 1=1 ORDER BY order_id",
        north_claims,
        export_format="csv",
    )
    assert inject_res["empty"] is False
    csv_path = cfg.exports_dir / inject_res["artifact_filename"]
    with csv_path.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) > 0
    assert all(r["region"] == "North" for r in rows)

    # Direct South-only query returns 0 rows with exact denial message
    denied = executor.execute_sql_rls(
        "SELECT * FROM gold_sales_obt WHERE region = 'South'",
        north_claims,
    )
    assert denied["empty"] is True
    assert denied["row_count"] == 0
    assert denied["message"] == "Bạn không có quyền truy cập hoặc dữ liệu không tồn tại"
    assert denied["artifact_filename"] is None


def test_data_trap_zero_total_price_and_exports(sandbox) -> None:
    cfg, auth, executor = sandbox
    admin_claims = auth.verify_token(auth.login("cfo_admin", "admin123")["access_token"])

    # Broken column SUM(total_price) == 0.0
    broken = executor.execute_sql_rls(
        "SELECT SUM(total_price) AS broken_total FROM gold_sales_obt",
        admin_claims,
        export_format="csv",
    )
    assert any("total_price_zero" in w for w in broken["data_trap_warnings"])
    with (cfg.exports_dir / broken["artifact_filename"]).open("r", encoding="utf-8") as f:
        broken_rows = list(csv.DictReader(f))
    assert float(broken_rows[0]["broken_total"]) == 0.0

    # Correct formula + XLSX + MD exports
    clean_xlsx = executor.execute_sql_rls(
        "SELECT region, SUM(quantity * unit_price) - SUM(discount) AS net_rev "
        "FROM gold_sales_obt WHERE is_deleted = false GROUP BY region ORDER BY region",
        admin_claims,
        export_format="xlsx",
    )
    assert clean_xlsx["data_trap_warnings"] == []
    wb = load_workbook(cfg.exports_dir / clean_xlsx["artifact_filename"])
    ws = wb.active
    assert ws.cell(row=1, column=1).value == "region"
    assert ws.cell(row=2, column=1).value == "North"
    assert float(ws.cell(row=2, column=2).value) > 0.0
    assert ws.cell(row=3, column=1).value == "South"
    assert float(ws.cell(row=3, column=2).value) > 0.0

    clean_md = executor.execute_sql_rls(
        "SELECT region, COUNT(*) AS cnt FROM gold_sales_obt WHERE is_deleted = false GROUP BY region ORDER BY region",
        admin_claims,
        export_format="md",
    )
    md_text = (cfg.exports_dir / clean_md["artifact_filename"]).read_text(encoding="utf-8")
    assert "| region | cnt |" in md_text


def test_saved_metrics_rls_and_caching(sandbox) -> None:
    _, auth, executor = sandbox
    north_claims = auth.verify_token(auth.login("sale_north", "north123")["access_token"])

    first = executor.execute_saved_metric("net_revenue_by_region", north_claims)
    assert first["cached"] is False
    assert first["row_count"] == 1
    assert "North" in first["markdown_preview"]
    assert "South" not in first["markdown_preview"]

    second = executor.execute_saved_metric("net_revenue_by_region", north_claims)
    assert second["cached"] is True
