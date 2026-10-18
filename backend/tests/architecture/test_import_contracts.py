"""Règle de dépendance (PLAN.md §3.5) : les contrats import-linter doivent rester verts."""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_import_contracts_are_kept():
    lint_imports = Path(sys.executable).with_name("lint-imports")
    result = subprocess.run([str(lint_imports)], cwd=BACKEND, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
