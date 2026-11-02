"""Приймання CSV у staging (stg.*) через COPY без втрати записів.

* Заголовок і порядок колонок перевіряються явно; зламаний файл зупиняє пакет.
* Кількість рядків у staging дорівнює кількості CSV-записів (повтори включно).
* Усі файли завантажуються в одній транзакції: або весь пакет, або нічого.
* Той самий batch_id з іншим вмістом файла не приймається (audit.batch_sources).
"""

from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path

from src.lab02.db import get_connection

RAW_ROOT = Path(os.getenv("DATA_RAW_PATH", "data/raw"))

SOURCE_SPECS = [
    ("customers.csv", "stg.customers", "base_v1",
     ["customer_id", "full_name", "email", "phone", "city", "service_zone_id", "registered_at", "customer_status"]),
    ("merchants.csv", "stg.merchants", "base_v1",
     ["merchant_id", "merchant_name", "merchant_type", "city", "service_zone_id", "opened_at", "merchant_status"]),
    ("products.csv", "stg.products", "base_v1",
     ["product_id", "merchant_id", "product_name", "category", "unit_price_uah", "is_active", "updated_at"]),
    ("orders.csv", "stg.orders", "base_v1",
     ["order_id", "customer_id", "merchant_id", "created_at", "order_status", "currency",
      "subtotal_amount", "delivery_fee", "discount_amount", "total_amount"]),
    ("order_items.csv", "stg.order_items", "lab02_relational",
     ["order_item_id", "order_id", "product_id", "quantity", "unit_price", "line_discount", "line_total", "currency"]),
]


def default_sources(raw_root: Path | None = None) -> list[dict]:
    root = Path(raw_root) if raw_root else RAW_ROOT
    return [
        {"name": name, "table": table, "file": root / subdir / name, "columns": cols}
        for name, table, subdir, cols in SOURCE_SPECS
    ]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_batch_registry(cur, batch_id: str, name: str, digest: str, rows: int) -> None:
    cur.execute(
        "SELECT sha256 FROM audit.batch_sources WHERE batch_id = %s AND source_file = %s",
        (batch_id, name),
    )
    known = cur.fetchone()
    if known is None:
        cur.execute(
            "INSERT INTO audit.batch_sources (batch_id, source_file, sha256, row_count) VALUES (%s, %s, %s, %s)",
            (batch_id, name, digest, rows),
        )
    elif known[0] != digest:
        raise ValueError(
            f"Вміст {name} змінився під тим самим batch_id={batch_id}: "
            f"було {known[0][:12]}…, стало {digest[:12]}…. Використайте новий batch_id."
        )


def _read_csv(src: dict) -> list[list[str]]:
    path: Path = src["file"]
    if not path.exists():
        raise FileNotFoundError(f"Обов'язковий файл {path} відсутній.")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header != src["columns"]:
            raise ValueError(
                f"Порушення схеми CSV у {path.name}. Очікувалось: {src['columns']}, отримано: {header}"
            )
        rows = []
        for index, row in enumerate(reader, start=1):
            if len(row) != len(src["columns"]):
                raise ValueError(f"Пошкоджений рядок {index} у {path.name}: {len(row)} полів замість {len(src['columns'])}")
            rows.append(row)
    return rows


def load_staging(batch_id: str, sources: list[dict] | None = None) -> dict[str, int]:
    """Завантажує всі джерела в stg.* однією транзакцією. Повертає {файл: кількість рядків}."""
    sources = sources if sources is not None else default_sources()
    # Спершу читаємо й перевіряємо ВСІ файли: помилка не залишає часткового staging.
    parsed = [(src, _read_csv(src)) for src in sources]

    counts: dict[str, int] = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            for src, rows in parsed:
                name, table, path = src["name"], src["table"], src["file"]
                _check_batch_registry(cur, batch_id, name, sha256_of(path), len(rows))
                cur.execute(f"TRUNCATE TABLE {table}")
                columns = src["columns"] + ["batch_id", "source_file", "source_row_number"]
                with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
                    for index, row in enumerate(rows, start=1):
                        copy.write_row(row + [batch_id, name, index])
                counts[name] = len(rows)
                print(f"[STAGING COPY] {name:16} -> {table:16}: {len(rows)} рядків")
    return counts


if __name__ == "__main__":
    load_staging("S08-V1")
