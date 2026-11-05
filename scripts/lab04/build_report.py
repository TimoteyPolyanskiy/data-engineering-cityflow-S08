"""Builds docs/lab04/report_lab_04.pdf: AI section from AI_USAGE.md + typst compile.

Usage: uv run python scripts/lab04/build_report.py
All numbers in report_lab_04.typ come from docs/lab04/output/ and docs/lab04/results.md.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typst_utils import ROOT, ai_section  # noqa: E402

docs = ROOT / "docs" / "lab04"
(docs / "ai_usage.typ").write_text(ai_section(4) + "\n", encoding="utf-8")
subprocess.run(["typst", "compile", "report_lab_04.typ", "report_lab_04.pdf"], cwd=docs, check=True)
print("Written docs/lab04/report_lab_04.pdf")
