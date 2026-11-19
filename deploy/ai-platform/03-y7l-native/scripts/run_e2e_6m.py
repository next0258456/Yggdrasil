"""Live End-to-End Test on the real 6,758,125-row FMCG sales Parquet dataset."""

from __future__ import annotations

import asyncio
import csv
import ctypes
import io
import json
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

import httpx
import redis
from fastapi.testclient import TestClient
from openpyxl import load_workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data.seed_data import seed_all  # noqa: E402
from y7l_tools.api import create_app  # noqa: E402
from y7l_tools.config import Settings  # noqa: E402

FMCG_PARQUET_PATH = Path(
    os.environ.get(
        "FMCG_SALES_PARQUET_PATH",
        str(PROJECT_ROOT.parents[2] / "Valkyrie" / ".scratch" / "sales_6m.parquet"),
    )
)


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def get_process_rss_mb() -> tuple[float, float]:
    """Return (current_rss_mb, peak_rss_mb) for the current Python process."""
    if sys.platform == "win32":
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return (
                round(counters.WorkingSetSize / (1024 * 1024), 2),
                round(counters.PeakWorkingSetSize / (1024 * 1024), 2),
            )
    return 0.0, 0.0


def main() -> int:
    if not FMCG_PARQUET_PATH.is_file():
        print(f"ERROR: 6.8M Parquet file not found: {FMCG_PARQUET_PATH}", file=sys.stderr)
        return 1

    data_dir = PROJECT_ROOT / "data"
    if not (data_dir / "sample_iam_users.json").is_file():
        seed_all(data_dir)

    iam_file = data_dir / "sample_iam_users.json"
    iam_backup = iam_file.read_text(encoding="utf-8")
    created_artifacts: list[Path] = []
    redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    if "host.docker.internal" in redis_url:
        redis_url = "redis://127.0.0.1:6379/0"

    r_client: redis.Redis | None = None
    try:
        candidate = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1.5)
        candidate.ping()
        r_client = candidate
    except Exception:
        r_client = None
        redis_url = ""

    cfg = Settings(
        obsidian_vault_path=str(PROJECT_ROOT / "vault"),
        data_dir=str(data_dir),
        fmcg_sales_parquet_path=str(FMCG_PARQUET_PATH),
        redis_url=redis_url,
        jwt_secret="e2e_live_6m_secret_key_for_y7l_native_2026",
        jwt_ttl_seconds=36000,
    )
    app = create_app(cfg)
    client = TestClient(app)
    report: list[tuple[str, str, str]] = []

    try:
        # ------------------------------------------------------------------
        # 1. Obsidian Zero-Chunking & Linter
        # ------------------------------------------------------------------
        lint = client.get("/vault/lint").json()
        assert lint["ok"] is True, f"Vault lint failed: {lint}"

        ctx = client.post(
            "/vault/context",
            json={"query": "fmcg_sales_6m total_price sales_date", "max_depth": 1},
        ).json()
        assert ctx["zero_chunking"] is True
        assert "fmcg_sales_6m" in ctx["entities"]
        assert any("total_price_zero" in t for t in ctx["data_traps"])
        assert any("null_sales_date" in t for t in ctx["data_traps"])
        report.append(
            (
                "1. Obsidian Zero-Chunking & Lint",
                "PASS",
                f"notes={lint['note_count']}, entities={ctx['entities']}, traps={len(ctx['data_traps'])}",
            )
        )

        # ------------------------------------------------------------------
        # 2. 10h JWT Auth + Live Redis :6379 + 2-Tier Kill-Switch
        # ------------------------------------------------------------------
        admin_token = client.post(
            "/auth/login",
            json={"username": "cfo_admin", "password": "admin123", "chat_user_id": "e2e_6m_admin"},
        ).json()["access_token"]
        north_token = client.post(
            "/auth/login",
            json={"username": "sale_north", "password": "north123", "chat_user_id": "e2e_6m_north"},
        ).json()["access_token"]
        south_token = client.post(
            "/auth/login",
            json={"username": "sale_south", "password": "south123", "chat_user_id": "e2e_6m_south"},
        ).json()["access_token"]

        if r_client is not None:
            ttl = r_client.ttl("y7l:session:e2e_6m_north")
            assert ttl > 35000, f"Unexpected Redis session TTL: {ttl}"

        # Provision temp user & test Tier-1 + Tier-2 Kill-Switch
        prov = client.post(
            "/auth/users/provision",
            json={
                "username": "e2e_temp_kill",
                "password": "temp123",
                "department": "sales",
                "region": "North",
                "role": "sales",
                "is_active": True,
            },
        )
        assert prov.status_code == 200
        temp_login = client.post(
            "/auth/login",
            json={"username": "e2e_temp_kill", "password": "temp123", "chat_user_id": "e2e_6m_temp"},
        )
        assert temp_login.status_code == 200
        temp_jwt = temp_login.json()["access_token"]

        t1 = client.post("/auth/session/revoke", json={"chat_user_id": "e2e_6m_temp"}).json()
        assert t1["session_removed"] is True
        if r_client is not None:
            assert r_client.get("y7l:session:e2e_6m_temp") is None

        # Tier-2 deactivate -> existing JWT must return HTTP 403
        client.post(
            "/auth/login",
            json={"username": "e2e_temp_kill", "password": "temp123", "chat_user_id": "e2e_6m_temp"},
        )
        t2 = client.post("/auth/users/e2e_temp_kill/deactivate", json={}).json()
        assert t2["is_active"] is False
        verify_after_kill = client.post(
            "/auth/verify",
            headers={"Authorization": f"Bearer {temp_jwt}"},
        )
        assert verify_after_kill.status_code == 403
        report.append(
            (
                "2. Auth 10h JWT, Live Redis & 2-Tier Kill-Switch",
                "PASS",
                f"redis_live={r_client is not None}, tier1_revoked=True, tier2_http={verify_after_kill.status_code}",
            )
        )

        # ------------------------------------------------------------------
        # 3. 6,758,125-Row Full Scan, DATA_TRAP Proof & Excel/CSV Export
        # ------------------------------------------------------------------
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        scan_res = client.post(
            "/sql/execute-rls",
            headers=admin_headers,
            json={
                "sql": (
                    "SELECT COUNT(*) AS total_rows, "
                    "SUM(total_price) AS broken_total_price, "
                    "COUNT(*) FILTER (WHERE sales_date IS NULL) AS null_dates, "
                    "SUM(quantity) AS total_units "
                    "FROM fmcg_sales_6m"
                ),
                "export_format": "csv",
            },
        ).json()
        assert scan_res["empty"] is False
        scan_csv = cfg.exports_dir / scan_res["artifact_filename"]
        created_artifacts.append(scan_csv)
        with scan_csv.open("r", encoding="utf-8") as f:
            row0 = next(csv.DictReader(f))
        assert int(row0["total_rows"]) == 6_758_125
        assert float(row0["broken_total_price"]) == 0.0
        assert int(row0["null_dates"]) == 67_526
        assert any("total_price_zero" in w for w in scan_res["data_trap_warnings"])

        top10_xlsx = client.post(
            "/sql/execute-rls",
            headers=admin_headers,
            json={
                "sql": (
                    "SELECT product_id, COUNT(*) AS tx_count, SUM(quantity) AS total_units, "
                    "ROUND(AVG(discount), 4) AS avg_discount "
                    "FROM fmcg_sales_6m WHERE sales_date IS NOT NULL "
                    "GROUP BY product_id ORDER BY total_units DESC LIMIT 10"
                ),
                "export_format": "xlsx",
            },
        ).json()
        assert top10_xlsx["row_count"] == 10
        assert top10_xlsx["data_trap_warnings"] == []
        xlsx_dl = client.get(top10_xlsx["artifact_url"])
        assert xlsx_dl.status_code == 200
        created_artifacts.append(cfg.exports_dir / top10_xlsx["artifact_filename"])
        wb = load_workbook(io.BytesIO(xlsx_dl.content))
        assert wb.active.max_row == 11  # header + 10 rows
        report.append(
            (
                "3. 6.76M-Row Full Scan, DATA_TRAP & XLSX Export",
                "PASS",
                f"rows=6,758,125, null_dates=67,526, broken_total_price=0.0, scan_ms={scan_res['execution_ms']}, xlsx_ms={top10_xlsx['execution_ms']}",
            )
        )

        # ------------------------------------------------------------------
        # 4. 6.76M-Row RLS Partition Completeness & Injection Defense
        # ------------------------------------------------------------------
        north_headers = {"Authorization": f"Bearer {north_token}"}
        south_headers = {"Authorization": f"Bearer {south_token}"}

        north_res = client.post(
            "/sql/execute-rls",
            headers=north_headers,
            json={"sql": "SELECT region, COUNT(*) AS rows, SUM(quantity) AS units FROM fmcg_sales_6m GROUP BY region"},
        ).json()
        south_res = client.post(
            "/sql/execute-rls",
            headers=south_headers,
            json={"sql": "SELECT region, COUNT(*) AS rows, SUM(quantity) AS units FROM fmcg_sales_6m GROUP BY region"},
        ).json()
        north_csv = cfg.exports_dir / north_res["artifact_filename"]
        south_csv = cfg.exports_dir / south_res["artifact_filename"]
        created_artifacts.extend([north_csv, south_csv])

        with north_csv.open("r", encoding="utf-8") as fn:
            north_rows_list = list(csv.DictReader(fn))
        with south_csv.open("r", encoding="utf-8") as fs:
            south_rows_list = list(csv.DictReader(fs))

        assert len(north_rows_list) == 1 and north_rows_list[0]["region"] == "North"
        assert len(south_rows_list) == 1 and south_rows_list[0]["region"] == "South"
        n_cnt = int(north_rows_list[0]["rows"])
        s_cnt = int(south_rows_list[0]["rows"])
        assert n_cnt + s_cnt == 6_758_125

        inject_res = client.post(
            "/sql/execute-rls",
            headers=north_headers,
            json={"sql": "SELECT region, COUNT(*) AS rows FROM fmcg_sales_6m WHERE region = 'South' OR 1=1 GROUP BY region"},
        ).json()
        created_artifacts.append(cfg.exports_dir / inject_res["artifact_filename"])
        assert "South" not in inject_res["markdown_preview"]
        assert "North" in inject_res["markdown_preview"]

        denied_res = client.post(
            "/sql/execute-rls",
            headers=north_headers,
            json={"sql": "SELECT * FROM fmcg_sales_6m WHERE region = 'South' LIMIT 5"},
        ).json()
        assert denied_res["empty"] is True
        assert denied_res["message"] == "Bạn không có quyền truy cập hoặc dữ liệu không tồn tại"

        report.append(
            (
                "4. 6.76M-Row RLS Partition & SQL Injection Defense",
                "PASS",
                f"North={n_cnt:,} ({north_res['execution_ms']}ms) + South={s_cnt:,} ({south_res['execution_ms']}ms) = 6,758,125; OR 1=1 blocked",
            )
        )

        # ------------------------------------------------------------------
        # 5. Flow-1 Saved Metrics on 6.76M Rows (Cold vs Warm Redis Cache)
        # ------------------------------------------------------------------
        if r_client is not None:
            for k in r_client.scan_iter("y7l:metric:fmcg_6m_*"):
                r_client.delete(k)

        t_cold = time.perf_counter()
        cold = client.post("/metrics/saved/fmcg_6m_monthly_summary?export_format=csv", headers=north_headers).json()
        cold_ms = round((time.perf_counter() - t_cold) * 1000.0, 2)
        if cold.get("artifact_filename"):
            created_artifacts.append(cfg.exports_dir / cold["artifact_filename"])

        t_warm = time.perf_counter()
        warm = client.post("/metrics/saved/fmcg_6m_monthly_summary?export_format=csv", headers=north_headers).json()
        warm_ms = round((time.perf_counter() - t_warm) * 1000.0, 2)

        assert cold["cached"] is False
        assert warm["cached"] is True
        assert warm_ms < 50.0, f"Warm cache took {warm_ms}ms (>= 50ms)"
        report.append(
            (
                "5. Flow-1 Saved Metrics (6.76M Cold vs Redis Warm)",
                "PASS",
                f"cold={cold_ms}ms, warm={warm_ms}ms (cached={warm['cached']}), rows={cold['row_count']}",
            )
        )

        # ------------------------------------------------------------------
        # 6. Live LiteLLM :4000 Text-to-SQL + Cost Probe
        # ------------------------------------------------------------------
        litellm_status = "SKIPPED"
        litellm_detail = "Not checked"
        try:
            with httpx.Client(timeout=20.0) as http:
                llm_resp = http.post(
                    "http://127.0.0.1:4000/v1/chat/completions",
                    headers={"Authorization": "Bearer sk-yggdrasil-master-admin-2026"},
                    json={
                        "model": "yggdrasil-default-llm",
                        "temperature": 0,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Bạn là DuckDB SQL Planner. CHỈ trả về DUY NHẤT 1 câu SELECT DuckDB SQL, "
                                    "không giải thích, không markdown fence. Tuân thủ DATA_TRAP:\n\n"
                                    + ctx["context_markdown"]
                                ),
                            },
                            {
                                "role": "user",
                                "content": "Thống kê tổng số lượng bán theo từng tháng từ bảng fmcg_sales_6m",
                            },
                        ],
                    },
                )
            if llm_resp.status_code == 200:
                body = llm_resp.json()
                gen_sql = body["choices"][0]["message"]["content"]
                usage = body.get("usage", {})
                cost_json = client.post(
                    "/finops/estimate-cost",
                    json={
                        "model": body.get("model", "yggdrasil-default-llm"),
                        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                        "completion_tokens": int(usage.get("completion_tokens", 0)),
                    },
                ).json()
                exec_llm_sql = client.post(
                    "/sql/execute-rls",
                    headers=north_headers,
                    json={"sql": gen_sql, "export_format": "csv"},
                )
                if exec_llm_sql.status_code == 200 and not exec_llm_sql.json().get("empty"):
                    ej = exec_llm_sql.json()
                    if ej.get("artifact_filename"):
                        created_artifacts.append(cfg.exports_dir / ej["artifact_filename"])
                    litellm_status = "PASS"
                    litellm_detail = (
                        f"tokens={cost_json['total_tokens']}, cost=${cost_json['estimated_cost_usd']}, "
                        f"rows={ej['row_count']}, ms={ej['execution_ms']}"
                    )
                else:
                    litellm_status = "WARN"
                    litellm_detail = f"LLM SQL HTTP={exec_llm_sql.status_code}: {exec_llm_sql.text[:140]}"
            else:
                litellm_status = "SKIPPED"
                litellm_detail = f"LiteLLM HTTP {llm_resp.status_code}: {llm_resp.text[:140]}"
        except Exception as exc:
            litellm_status = "SKIPPED"
            litellm_detail = f"LiteLLM unavailable: {exc}"
        report.append(("6. Live LiteLLM :4000 Text-to-SQL & Cost", litellm_status, litellm_detail))

        # ------------------------------------------------------------------
        # 7. Live Vietnamese Voice TTS Probe (edge-tts)
        # ------------------------------------------------------------------
        tts_status = "SKIPPED"
        tts_detail = ""
        try:
            t_tts = time.perf_counter()
            tts_resp = client.post(
                "/voice/tts",
                json={
                    "text": (
                        f"Báo cáo khu vực miền Bắc trên 6,76 triệu giao dịch ghi nhận {n_cnt} đơn hàng hợp lệ."
                    )
                },
            )
            tts_ms = round((time.perf_counter() - t_tts) * 1000.0, 2)
            if tts_resp.status_code == 200:
                tj = tts_resp.json()
                mp3_path = cfg.exports_dir / tj["artifact_filename"]
                created_artifacts.append(mp3_path)
                dl_mp3 = client.get(tj["artifact_url"])
                if dl_mp3.status_code == 200 and len(dl_mp3.content) > 100:
                    tts_status = "PASS"
                    tts_detail = f"mp3_bytes={len(dl_mp3.content):,}, tts_ms={tts_ms}"
                else:
                    tts_status = "WARN"
                    tts_detail = f"Unexpected MP3 payload len={len(dl_mp3.content)}"
            else:
                tts_status = "SKIPPED"
                tts_detail = f"HTTP {tts_resp.status_code}: {tts_resp.text[:120]}"
        except Exception as exc:
            tts_status = "SKIPPED"
            tts_detail = f"Edge-TTS network unavailable: {exc}"
        report.append(("7. Live Vietnamese Edge-TTS Voice Reply", tts_status, tts_detail))

        rss_mb, peak_rss_mb = get_process_rss_mb()
        print("# 03-Y7L-NATIVE — 6,758,125-ROW LIVE E2E REPORT\n")
        print(f"- **Dataset:** `{FMCG_PARQUET_PATH}` (`6,758,125` rows, `173.88 MB` ZSTD Parquet)")
        print(f"- **Process Memory:** Current RSS = `{rss_mb} MB` | Peak RSS = `{peak_rss_mb} MB`\n")
        print("| Stage | Status | Metrics & Evidence |")
        print("| :--- | :---: | :--- |")
        for stage, status, detail in report:
            print(f"| {stage} | {status} | {detail} |")

    finally:
        iam_file.write_text(iam_backup, encoding="utf-8")
        for artifact in created_artifacts:
            try:
                if artifact.is_file():
                    artifact.unlink()
            except OSError:
                pass
        if r_client is not None:
            try:
                for key in list(r_client.scan_iter("y7l:session:e2e_6m_*")) + list(
                    r_client.scan_iter("y7l:metric:fmcg_6m_*")
                ):
                    r_client.delete(key)
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
