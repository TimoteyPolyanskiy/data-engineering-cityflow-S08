"""Розпаковує архіви CityFlow у data/raw/ і перевіряє контрольні суми.

Використання:
  uv run python scripts/prepare_raw.py <каталог-або-zip з архівами S08>   # розпакувати + перевірити
  uv run python scripts/prepare_raw.py                                  # лише перевірити data/raw/

Що перевіряється:
  * SHA-256 архіву cityflow_S08_base_v1.zip проти наданого викладачем файла .sha256;
  * SHA-256 кожного розпакованого файла проти PACKAGE_INFO.json усередині пакета.
Raw-файли не змінюються. Результат записується в docs/package_checksums.json.
"""

import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PACKAGES = {  # архів -> каталог у data/raw
    "cityflow_S08_base_v1.zip": "base_v1",
    "cityflow_S08_lab02_relational_v1.zip": "lab02_relational",
}
TEACHER_SUM_FILE = "cityflow_S08_base_v1.sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_archives(source: Path, workdir: Path) -> Path:
    """Повертає каталог, де лежать архіви (розпаковує зовнішній zip, якщо потрібно)."""
    if source.is_file() and source.suffix == ".zip":
        with zipfile.ZipFile(source) as outer:
            outer.extractall(workdir)
        source = workdir
    for candidate in [source, *source.rglob("*")]:
        if candidate.is_dir() and (candidate / "cityflow_S08_base_v1.zip").exists():
            return candidate
    raise SystemExit(f"Не знайдено cityflow_S08_base_v1.zip у {source}")


def extract_and_check(archives_dir: Path, report: dict) -> None:
    teacher_file = archives_dir / TEACHER_SUM_FILE
    teacher = teacher_file.read_text(encoding="utf-8").split()[0].lower() if teacher_file.exists() else None
    for archive, subdir in PACKAGES.items():
        path = archives_dir / archive
        if not path.exists():
            raise SystemExit(f"Немає архіву {archive}")
        digest = sha256(path)
        entry = {"sha256": digest, "teacher_sha256": None, "matches_teacher": None}
        if archive == "cityflow_S08_base_v1.zip" and teacher:
            entry.update(teacher_sha256=teacher, matches_teacher=(digest == teacher))
            if digest != teacher:
                raise SystemExit(f"SHA-256 {archive} не збігається з наданим викладачем — зверніться до викладача.")
        report["archives"][archive] = entry
        target = RAW / subdir
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            z.extractall(target)
        print(f"[OK] {archive}: sha256={digest[:16]}… -> {target.relative_to(ROOT)}"
              + (" (збігається з викладацьким)" if entry["matches_teacher"] else " (викладацької суми немає, записано обчислену)"))


def verify_files(report: dict) -> None:
    for archive, subdir in PACKAGES.items():
        info_path = RAW / subdir / "PACKAGE_INFO.json"
        if not info_path.exists():
            raise SystemExit(f"Немає {info_path.relative_to(ROOT)}: спершу розпакуйте архіви.")
        info = json.loads(info_path.read_text(encoding="utf-8"))
        files = {}
        for item in info["files"]:
            actual = sha256(RAW / subdir / item["path"])
            if actual != item["sha256"]:
                raise SystemExit(f"Файл {subdir}/{item['path']} змінено: {actual} != {item['sha256']}")
            files[item["path"]] = item["sha256"]
        report["packages"][archive] = {"package_id": info["package_id"], "student_id": info["student_id"],
                                       "directory": f"data/raw/{subdir}", "files": files}
        print(f"[OK] {subdir}: {len(files)} файлів збігаються з PACKAGE_INFO.json ({info['package_id']})")


def main() -> None:
    report: dict = {"archives": {}, "packages": {}}
    old = ROOT / "docs" / "package_checksums.json"
    if old.exists():
        report["archives"] = json.loads(old.read_text(encoding="utf-8")).get("archives", {})
    if len(sys.argv) > 1:
        with tempfile.TemporaryDirectory() as tmp:
            extract_and_check(find_archives(Path(sys.argv[1]).expanduser(), Path(tmp)), report)
    verify_files(report)
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Записано {old.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
