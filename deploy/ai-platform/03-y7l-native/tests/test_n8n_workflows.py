"""Structural and contract tests for the 6 n8n workflow JSONs in 03-y7l-native."""

from __future__ import annotations

import json
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / "n8n-workflows"

EXPECTED_WORKFLOWS = [
    "01_chat_voice_entrypoint.json",
    "02_rag_obsidian_sql_singlehop.json",
    "03_rag_sop_hybrid_n8n.json",
    "04_webview_oauth_login.json",
    "05_hr_master_iam_killswitch.json",
    "06_finops_token_ledger_sheet.json",
]


def test_all_six_workflows_exist_and_have_valid_structure() -> None:
    for filename in EXPECTED_WORKFLOWS:
        wf_path = WORKFLOWS_DIR / filename
        assert wf_path.is_file(), f"Missing workflow JSON: {filename}"

        data = json.loads(wf_path.read_text(encoding="utf-8"))
        assert isinstance(data.get("name"), str) and data["name"]
        nodes = data.get("nodes")
        connections = data.get("connections")
        assert isinstance(nodes, list) and len(nodes) >= 5
        assert isinstance(connections, dict) and len(connections) >= 4

        node_names = {n["name"] for n in nodes}
        for src_name, branches in connections.items():
            assert src_name in node_names, f"{filename}: connection source {src_name} missing"
            for outputs in branches.get("main", []):
                for edge in outputs:
                    assert edge["node"] in node_names, f"{filename}: target {edge['node']} missing"


def test_llm_workflows_report_token_usage_to_wf06() -> None:
    for filename in [
        "01_chat_voice_entrypoint.json",
        "02_rag_obsidian_sql_singlehop.json",
        "03_rag_sop_hybrid_n8n.json",
    ]:
        raw = (WORKFLOWS_DIR / filename).read_text(encoding="utf-8")
        assert "y7l-token-log" in raw, f"{filename} must send token usage to WF-06 /webhook/y7l-token-log"


def test_finops_workflow_includes_sheet_cost_and_litellm_killswitch() -> None:
    wf06_path = WORKFLOWS_DIR / "06_finops_token_ledger_sheet.json"
    raw = wf06_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    node_types = {n["type"] for n in data["nodes"]}
    assert "n8n-nodes-base.googleSheets" in node_types
    assert "n8n-nodes-base.code" in node_types
    assert "n8n-nodes-base.redis" in node_types
    assert "AI_Token_Ledger" in raw
    assert "estimated_cost_usd" in raw
    assert "/key/block" in raw
    assert "/key/generate" in raw
    assert "/key/unblock" in raw
    assert "/key/delete" in raw
