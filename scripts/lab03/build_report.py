"""Builds docs/lab03/report_lab_03.pdf: AI section from AI_USAGE.md + typst compile.

Usage: uv run python scripts/lab03/build_report.py
All numbers in report_lab_03.typ come from docs/lab03/output/ and the plan files (run_lab03.fish).
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typst_utils import ROOT, ai_section  # noqa: E402

docs = ROOT / "docs" / "lab03"
(docs / "ai_usage.typ").write_text(ai_section(3) + "\n", encoding="utf-8")
subprocess.run(["typst", "compile", "report_lab_03.typ", "report_lab_03.pdf"], cwd=docs, check=True)
print("Written docs/lab03/report_lab_03.pdf")
