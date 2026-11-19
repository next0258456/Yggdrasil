"""Tests for Zero-Chunking Obsidian Vault loader, [[Wikilinks]] traversal, and vault linter."""

from __future__ import annotations

from pathlib import Path

from y7l_tools.vault import lint_vault, list_entities, read_context

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VAULT_DIR = PROJECT_ROOT / "vault"


def test_vault_linter_passes() -> None:
    report = lint_vault(VAULT_DIR)
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["note_count"] >= 5


def test_list_entities_contains_expected_notes() -> None:
    entities = {item["entity"] for item in list_entities(VAULT_DIR)}
    assert {"Doanh_Thu_Thuan", "gold_sales_obt", "dim_customers"}.issubset(entities)


def test_read_context_zero_chunking_and_wikilinks_traversal() -> None:
    ctx = read_context(VAULT_DIR, query="Tính doanh thu thuần theo khách hàng", max_depth=1)
    assert ctx["zero_chunking"] is True
    assert "Doanh_Thu_Thuan" in ctx["entities"]
    assert "gold_sales_obt" in ctx["entities"]
    assert "dim_customers" in ctx["entities"]
    assert any("total_price_zero" in trap for trap in ctx["data_traps"])
    assert any("soft_delete" in trap for trap in ctx["data_traps"])

    # Verify whole unchunked note contents are present
    gold_file = (VAULT_DIR / "tables" / "gold_sales_obt.md").read_text(encoding="utf-8")
    assert gold_file.strip() in ctx["context_markdown"]
