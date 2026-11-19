"""CLI linter for the 03-y7l-native Obsidian Vault."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from y7l_tools.config import get_settings  # noqa: E402
from y7l_tools.vault import lint_vault  # noqa: E402


def main() -> int:
    settings = get_settings()
    report = lint_vault(settings.vault_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
