"""Спільні допоміжні функції для генерації Typst-звітів з JSON-метрик."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# ";" is escaped too: right after an embedded expression like #raw("x") Typst would swallow it.
_SPECIAL = set("\\#$*_`<>@~[];")


def esc(text: str) -> str:
    """Екранує спецсимволи Typst-розмітки в звичайному тексті."""
    out = "".join("\\" + ch if ch in _SPECIAL else ch for ch in str(text))
    out = re.sub(r"^([=+/\-])", r"\\\1", out)
    out = re.sub(r"^(\d+)\.", r"\1\\.", out)
    return out


def code(text: str) -> str:
    """Рядок як `raw` (моноширинний), безпечний для вставки в розмітку."""
    inner = str(text).replace("\\", "\\\\").replace('"', '\\"')
    return f'#raw("{inner}")'


def md(text: str) -> str:
    """Міні-розмітка: `код` -> raw, *жирний* -> strong, решта екранується."""
    out = []
    for i, part in enumerate(str(text).split("`")):
        if i % 2:
            out.append(code(part))
            continue
        chunks = part.split("*")
        out.append("".join(esc(c) if j % 2 == 0 else f"#strong[{esc(c)}]" for j, c in enumerate(chunks)))
    return "".join(out)


def table(columns: list[str], header: list[str], rows: list[list], aligns: list[str] | None = None,
          size: str | None = None, inset: str = "5pt") -> str:
    aligns = aligns or ["left"] * len(columns)
    head = ", ".join(f"[*{md(h)}*]" for h in header)
    body = ",\n  ".join(", ".join(f"[{md(c)}]" for c in row) for row in rows)
    out = (
        "#table(\n"
        f"  columns: ({', '.join(columns)}),\n"
        '  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },\n'
        '  stroke: 0.5pt + rgb("#cbd5e1"),\n'
        f"  inset: (x: {inset}, y: {inset}),\n"
        f"  align: (col, row) => ({', '.join(aligns)}).at(col) + horizon,\n"
        f"  {head},\n  {body}\n)"
    )
    out = f"#text(size: {size})[\n{out}\n]" if size else out
    # a table is never split across pages (report contract): it moves to the next page whole
    return f"#block(breakable: false)[\n{out}\n]"


def bullets(items: list[str]) -> str:
    return "\n".join(f"- {md(i)}" for i in items)


def money(value) -> str:
    """'3619701.14' -> '3 619 701.14'"""
    if value is None:
        return "—"
    d = Decimal(str(value))
    sign = "-" if d < 0 else ""
    whole, _, frac = f"{abs(d):.2f}".partition(".")
    groups = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return f"{sign}{' '.join(groups)}.{frac}"


def integer(value) -> str:
    if value is None:
        return "—"
    n = int(Decimal(str(value)))
    return f"{n:,}".replace(",", " ")


def day(iso: str | None) -> str:
    return (iso or "—")[:10]


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def meta() -> dict:
    path = ROOT / "docs" / "report_meta.json"
    return json.loads(path.read_text(encoding="utf-8"))


def link_or_hint(url: str, label: str, hint: str) -> str:
    if url:
        return f'#link("{url}")[{esc(label)}]'
    print(f"УВАГА: {hint}")
    return esc("(посилання буде додано після створення Pull Request)")


def ai_section(lab_number: int) -> str:
    """Беремо розділ про ШІ з AI_USAGE.md, щоб звіт і файл у репозиторії не розходилися."""
    text = (ROOT / "AI_USAGE.md").read_text(encoding="utf-8")
    pattern = rf"^## Лабораторна робота №{lab_number}\s*$(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, flags=re.M | re.S)
    if not match:
        raise SystemExit(f"У AI_USAGE.md немає розділу «Лабораторна робота №{lab_number}»")
    paragraphs = [p.strip().replace("\n", " ") for p in match.group(1).strip().split("\n\n") if p.strip()]
    return "\n\n".join(md(p) for p in paragraphs)


def render(template_path: Path, output_path: Path, values: dict[str, str]) -> None:
    text = template_path.read_text(encoding="utf-8")
    for key, value in values.items():
        token = f"%%{key}%%"
        if token not in text:
            raise SystemExit(f"У шаблоні {template_path.name} немає {token}")
        text = text.replace(token, value)
    left = re.findall(r"%%[A-Z0-9_]+%%", text)
    if left:
        raise SystemExit(f"Не підставлено: {sorted(set(left))}")
    output_path.write_text(text, encoding="utf-8")
    print(f"Записано {output_path.relative_to(ROOT)}")
