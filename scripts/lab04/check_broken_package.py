"""Shows that read_file_batch rejects a changed or incomplete copy of the real S08 package.

Usage (from the repo root): uv run python scripts/lab04/check_broken_package.py
Broken copies are built in a temporary directory; the original ZIP is only read.
"""

import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "lab04"))
import student  # noqa: E402

ORIGINAL = ROOT / "data/lab04_variant/input/cityflow_S08_batch_01_normal_v1.zip"


def copy_with(target: Path, change) -> Path:
    """Rewrites the package into target, letting change(name, data) edit or drop (None) a member."""
    with zipfile.ZipFile(ORIGINAL) as src, zipfile.ZipFile(target, "w") as dst:
        for name in src.namelist():
            data = change(name, src.read(name))
            if data is not None:
                dst.writestr(name, data)
    return target


def edit_refunds(name, data):
    # one changed byte in a file we do not load: the whole package must still be rejected
    return data.replace(b"S08", b"S09", 1) if name == "refunds.csv" else data


cases = {
    "changed refunds.csv": lambda d: copy_with(d / "changed.zip", edit_refunds),
    "missing order_items.csv": lambda d: copy_with(d / "missing.zip", lambda n, b: None if n == "order_items.csv" else b),
    "original, other student_id": lambda d: ORIGINAL,
}

with tempfile.TemporaryDirectory() as tmp:
    print("original package:", {k: len(v) for k, v in student.read_file_batch(ORIGINAL, "S08").items()})
    for label, build in cases.items():
        student_id = "S01" if "other student" in label else "S08"
        try:
            student.read_file_batch(build(Path(tmp)), student_id)
            print(f"{label}: ACCEPTED (unexpected)")
        except ValueError as exc:
            print(f"{label}: rejected, ValueError {exc}")
