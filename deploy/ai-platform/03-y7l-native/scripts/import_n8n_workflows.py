"""Import all 03-y7l-native n8n workflow JSONs into an n8n instance as inactive workflows."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = PROJECT_ROOT / "n8n-workflows"


def main() -> int:
    n8n_url = os.environ.get("N8N_URL", "http://localhost:5678").rstrip("/")
    api_key = os.environ.get("N8N_API_KEY", "").strip()
    if not api_key:
        print("ERROR: Set N8N_API_KEY before importing workflows into n8n.", file=sys.stderr)
        return 1

    headers = {
        "X-N8N-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    files = sorted(WORKFLOWS_DIR.glob("*.json"))
    if not files:
        print(f"No workflow JSON files found in {WORKFLOWS_DIR}", file=sys.stderr)
        return 1

    with httpx.Client(timeout=20.0) as client:
        for wf_file in files:
            payload = json.loads(wf_file.read_text(encoding="utf-8"))
            payload["active"] = False
            resp = client.post(f"{n8n_url}/api/v1/workflows", headers=headers, json=payload)
            if resp.status_code >= 400:
                print(
                    f"FAILED {wf_file.name}: HTTP {resp.status_code} - {resp.text}",
                    file=sys.stderr,
                )
                return 1
            created = resp.json()
            print(
                f"IMPORTED (inactive) {wf_file.name} -> id={created.get('id')} name={created.get('name')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
