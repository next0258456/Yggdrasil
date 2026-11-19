"""End-to-end FastAPI TestClient tests for y7l-tools Track-B Sidecar."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data.seed_data import seed_all
from y7l_tools.api import create_app
from y7l_tools.config import Settings


def _build_minimal_pdf(text: str) -> bytes:
    """Construct a valid single-page PDF with Helvetica text for offline pypdf extraction tests."""
    safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT\n/F1 12 Tf\n72 720 Td\n({safe_text}) Tj\nET\n".encode("latin-1")

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        ),
        (
            f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"endstream\nendobj\n"
        ),
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    buf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for obj in objects:
        offsets.append(len(buf))
        buf.extend(obj)

    xref_pos = len(buf)
    buf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    buf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buf.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

    buf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("latin-1")
    )
    return bytes(buf)


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "data"
    seed_all(data_dir)
    cfg = Settings(
        obsidian_vault_path=str(Path(__file__).resolve().parents[1] / "vault"),
        data_dir=str(data_dir),
        redis_url="",
        jwt_secret="e2e_test_secret_y7l_native_2026",
    )
    app = create_app(cfg)
    return TestClient(app)


def test_health_vault_and_guard_endpoints(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    lint = client.get("/vault/lint")
    assert lint.status_code == 200
    assert lint.json()["ok"] is True

    entities = client.get("/vault/entities")
    assert entities.status_code == 200
    assert entities.json()["count"] >= 5

    ctx = client.post("/vault/context", json={"query": "Doanh thu thuần"})
    assert ctx.status_code == 200
    assert ctx.json()["zero_chunking"] is True

    pii = client.post(
        "/guard/mask-pii",
        json={"text": "CCCD 001099012345 SĐT 0901234567"},
    )
    assert pii.status_code == 200
    assert "001099012345" not in pii.json()["masked_text"]

    bad_sql = client.post("/guard/validate-sql", json={"sql": "DROP TABLE gold_sales_obt"})
    assert bad_sql.status_code == 400


def test_auth_sql_metrics_and_artifact_download(client: TestClient) -> None:
    login = client.post(
        "/auth/login",
        json={"username": "sale_north", "password": "north123", "chat_user_id": "zalo_e2e"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    verify = client.post("/auth/verify", headers=headers)
    assert verify.status_code == 200
    assert verify.json()["claims"]["region"] == "North"

    metrics_list = client.get("/metrics/saved")
    assert metrics_list.status_code == 200
    assert len(metrics_list.json()["metrics"]) == 6

    metric_run = client.post("/metrics/saved/net_revenue_by_region?export_format=csv", headers=headers)
    assert metric_run.status_code == 200
    artifact_url = metric_run.json()["artifact_url"]
    assert artifact_url.startswith("/artifacts/")

    dl = client.get(artifact_url)
    assert dl.status_code == 200
    assert "North" in dl.text

    # Path traversal must be rejected
    traversal = client.get("/artifacts/..%2Fsample_iam_users.json")
    assert traversal.status_code in {400, 404}

    sql_res = client.post(
        "/sql/execute-rls",
        headers=headers,
        json={"sql": "SELECT * FROM gold_sales_obt WHERE region = 'South'"},
    )
    assert sql_res.status_code == 200
    assert sql_res.json()["empty"] is True


def test_ocr_extract_finops_and_tts(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    md_resp = client.post(
        "/ocr/extract",
        files={"file": ("sop.md", "Quy trình hoàn đơn 7 ngày".encode("utf-8"), "text/markdown")},
    )
    assert md_resp.status_code == 200
    assert md_resp.json()["chunk_count"] == 1

    pdf_bytes = _build_minimal_pdf("SOP-FIN-001 Refund Policy 7 Days")
    pdf_resp = client.post(
        "/ocr/extract",
        files={"file": ("policy.pdf", pdf_bytes, "application/pdf")},
    )
    assert pdf_resp.status_code == 200
    assert "SOP-FIN-001" in pdf_resp.json()["text"]

    cost_resp = client.post(
        "/finops/estimate-cost",
        json={"model": "deepseek-chat", "prompt_tokens": 1000, "completion_tokens": 500},
    )
    assert cost_resp.status_code == 200
    assert cost_resp.json()["total_tokens"] == 1500
    assert cost_resp.json()["estimated_cost_usd"] == pytest.approx(0.00082, rel=1e-6)

    class _FakeCommunicate:
        def __init__(self, text: str, voice: str) -> None:
            self.text = text
            self.voice = voice

        async def save(self, path: str) -> None:
            Path(path).write_bytes(b"ID3-MOCK-MP3")

    monkeypatch.setattr("y7l_tools.voice_ocr.edge_tts.Communicate", _FakeCommunicate)
    tts_resp = client.post("/voice/tts", json={"text": "Doanh thu hôm nay đạt 150 triệu đồng."})
    assert tts_resp.status_code == 200
    assert tts_resp.json()["artifact_filename"].endswith(".mp3")
    mp3_dl = client.get(tts_resp.json()["artifact_url"])
    assert mp3_dl.status_code == 200
    assert mp3_dl.content == b"ID3-MOCK-MP3"
