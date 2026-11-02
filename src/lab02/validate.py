"""Правила приймання Лабораторної роботи №2 (чиста логіка без доступу до БД).

Вхід: рядки зі staging (усі значення — текст, порожнє поле — "").
Вихід: рішення по кожному рядку (accepted / rejected / duplicate) та типізовані
рядки, придатні для публікації в core. Політику описано в docs/lab02/load_policy.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

ALLOWED_CURRENCIES = frozenset({"UAH", "USD", "EUR"})

_ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$"
)
_DMY_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2})$")
_MONEY_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_INT_RE = re.compile(r"^-?\d+$")
_CENT = Decimal("0.01")
_MONEY_LIMIT = Decimal("10000000000")  # numeric(12,2) < 10^10
_INT_LIMIT = 2**31


# ---------------------------------------------------------------------------
# Розбір значень
# ---------------------------------------------------------------------------
def parse_timestamp(raw: str | None) -> datetime | None:
    """ISO 8601 з Z/зсувом -> UTC; DD/MM/YYYY HH:MM -> явно UTC; інакше None.

    * Частки секунди довші за мікросекунди відкидаються (truncate); оригінал
      лишається в staging/raw.
    * ISO без зсуву (без Z/±hh:mm) не вгадується і відхиляється.
    * День/місяць автоматично не визначаються: DD/MM/YYYY читається лише як
      день-місяць-рік.
    """
    if raw is None:
        return None
    text = raw.strip()
    try:
        m = _ISO_RE.match(text)
        if m:
            year, month, day, hour, minute, second, frac, tz = m.groups()
            micro = int((frac or "")[:6].ljust(6, "0"))
            if tz == "Z":
                tzinfo = timezone.utc
            else:
                sign = 1 if tz[0] == "+" else -1
                tz_h, tz_m = int(tz[1:3]), int(tz[4:6])
                if tz_h > 23 or tz_m > 59:
                    return None
                tzinfo = timezone(sign * timedelta(hours=tz_h, minutes=tz_m))
            value = datetime(
                int(year), int(month), int(day), int(hour), int(minute), int(second), micro, tzinfo=tzinfo
            )
            return value.astimezone(timezone.utc)
        m = _DMY_RE.match(text)
        if m:
            day, month, year, hour, minute = (int(x) for x in m.groups())
            return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None
    return None


def parse_money(raw: str | None) -> Decimal | None:
    """Число для numeric(12,2): більше двох знаків округлюється half-up."""
    if raw is None:
        return None
    text = raw.strip()
    if not _MONEY_RE.match(text):
        return None
    value = Decimal(text).quantize(_CENT, rounding=ROUND_HALF_UP)
    if abs(value) >= _MONEY_LIMIT:
        return None
    return value


def parse_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = raw.strip()
    if not _INT_RE.match(text):
        return None
    value = int(text)
    return value if abs(value) < _INT_LIMIT else None


def parse_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    text = raw.strip().lower()
    if text in ("true", "t", "1"):
        return True
    if text in ("false", "f", "0"):
        return False
    return None


def normalize_currency(raw: str | None) -> str | None:
    """Дозволена нормалізація: прибрати пробіли по краях і привести до верхнього регістру.
    Внутрішні пробіли («UA H») не виправляються."""
    if raw is None:
        return None
    text = raw.strip().upper()
    return text if text in ALLOWED_CURRENCIES else None


# ---------------------------------------------------------------------------
# Загальна обробка одного файла
# ---------------------------------------------------------------------------
@dataclass
class Decision:
    source_file: str
    source_row_number: int
    business_key: str | None
    status: str  # accepted | rejected | duplicate
    reason_code: str | None
    reason_codes: list[str] = field(default_factory=list)
    payload: dict | None = None  # вихідний рядок для не-accepted


@dataclass
class FileResult:
    decisions: list[Decision]
    accepted_rows: list[tuple]
    accepted_keys: set[str]


RowValidator = Callable[[dict, "Context"], tuple[list[str], tuple | None]]


@dataclass
class Context:
    accepted_customers: set[str] = field(default_factory=set)
    accepted_merchants: set[str] = field(default_factory=set)
    accepted_products: set[str] = field(default_factory=set)
    accepted_orders: set[str] = field(default_factory=set)


def process_file(
    source_file: str,
    rows: list[dict],
    key_col: str,
    columns: list[str],
    validator: RowValidator,
    ctx: Context,
) -> FileResult:
    """Класифікує кожен рядок рівно в один із статусів.

    1. Порожній ключ -> rejected/EMPTY_KEY.
    2. Група з однаковим ключем: усі рядки однакові після нормалізації -> перший
       іде далі, решта duplicate/FULL_DUPLICATE; значення різні -> уся група
       rejected/KEY_CONFLICT (без вибору «останнього» рядка).
    3. Перший рядок групи проходить правила файла.
    """
    decisions: dict[int, Decision] = {}
    accepted_rows: list[tuple] = []
    accepted_keys: set[str] = set()

    normalized: dict[int, dict] = {}
    notes: dict[int, list[str]] = {}
    for row in rows:
        n = row["source_row_number"]
        norm = {c: (row[c].strip() if row[c] is not None else None) for c in columns}
        normalized[n] = norm
        trimmed = any(row[c] is not None and row[c] != norm[c] for c in columns)
        notes[n] = ["WHITESPACE_TRIMMED"] if trimmed else []

    def payload_of(row: dict) -> dict:
        return {c: row[c] for c in columns}

    groups: dict[str, list[dict]] = {}
    for row in rows:
        n = row["source_row_number"]
        key = normalized[n][key_col]
        if not key:
            decisions[n] = Decision(
                source_file, n, None, "rejected", "EMPTY_KEY", ["EMPTY_KEY"] + notes[n], payload_of(row)
            )
            continue
        groups.setdefault(key, []).append(row)

    for key, group in groups.items():
        variants = {tuple(normalized[r["source_row_number"]][c] for c in columns) for r in group}
        if len(variants) > 1:
            for r in group:
                n = r["source_row_number"]
                decisions[n] = Decision(
                    source_file, n, key, "rejected", "KEY_CONFLICT", ["KEY_CONFLICT"] + notes[n], payload_of(r)
                )
            continue
        first, *copies = group
        for r in copies:
            n = r["source_row_number"]
            decisions[n] = Decision(
                source_file, n, key, "duplicate", "FULL_DUPLICATE",
                ["FULL_DUPLICATE"] + notes[n], payload_of(r),
            )
        n = first["source_row_number"]
        reasons, typed = validator(normalized[n], ctx)
        if reasons:
            decisions[n] = Decision(
                source_file, n, key, "rejected", reasons[0], reasons + notes[n], payload_of(first)
            )
        else:
            decisions[n] = Decision(source_file, n, key, "accepted", None, notes[n], None)
            accepted_rows.append((n, typed))
            accepted_keys.add(key)

    accepted_rows.sort(key=lambda item: item[0])
    return FileResult(
        decisions=[decisions[r["source_row_number"]] for r in rows],
        accepted_rows=[typed for _, typed in accepted_rows],
        accepted_keys=accepted_keys,
    )


# ---------------------------------------------------------------------------
# Правила окремих файлів (порядок причин = пріоритет reason_code)
# ---------------------------------------------------------------------------
def _blank(*values: str | None) -> bool:
    return any(v is None or v == "" for v in values)


CUSTOMER_COLS = ["customer_id", "full_name", "email", "phone", "city", "service_zone_id", "registered_at", "customer_status"]
MERCHANT_COLS = ["merchant_id", "merchant_name", "merchant_type", "city", "service_zone_id", "opened_at", "merchant_status"]
PRODUCT_COLS = ["product_id", "merchant_id", "product_name", "category", "unit_price_uah", "is_active", "updated_at"]
ORDER_COLS = [
    "order_id", "customer_id", "merchant_id", "created_at", "order_status", "currency",
    "subtotal_amount", "delivery_fee", "discount_amount", "total_amount",
]
ITEM_COLS = ["order_item_id", "order_id", "product_id", "quantity", "unit_price", "line_discount", "line_total", "currency"]


def validate_customer(r: dict, ctx: Context):
    reasons: list[str] = []
    if _blank(r["full_name"], r["city"]):
        reasons.append("MISSING_REQUIRED")
    ts = parse_timestamp(r["registered_at"])
    if ts is None:
        reasons.append("INVALID_DATE")
    if reasons:
        return reasons, None
    return [], (r["customer_id"], r["full_name"], r["city"], ts)


def validate_merchant(r: dict, ctx: Context):
    reasons: list[str] = []
    if _blank(r["merchant_name"], r["city"]):
        reasons.append("MISSING_REQUIRED")
    ts = parse_timestamp(r["opened_at"])
    if ts is None:
        reasons.append("INVALID_DATE")
    if reasons:
        return reasons, None
    return [], (r["merchant_id"], r["merchant_name"], r["city"], ts)


def validate_product(r: dict, ctx: Context):
    reasons: list[str] = []
    if _blank(r["product_name"]):
        reasons.append("MISSING_REQUIRED")
    active = parse_bool(r["is_active"])
    if active is None:
        reasons.append("INVALID_BOOLEAN")
    price = parse_money(r["unit_price_uah"])
    if price is None or price < 0 or (active is True and price <= 0):
        reasons.append("INVALID_PRICE")
    if r["merchant_id"] not in ctx.accepted_merchants:
        reasons.append("ORPHAN_MERCHANT_FK")
    if reasons:
        return reasons, None
    return [], (r["product_id"], r["merchant_id"], r["product_name"], price, active)


def validate_order(r: dict, ctx: Context):
    reasons: list[str] = []
    if _blank(r["order_status"]):
        reasons.append("MISSING_REQUIRED")
    ts = parse_timestamp(r["created_at"])
    if ts is None:
        reasons.append("INVALID_DATE")
    currency = normalize_currency(r["currency"])
    if currency is None:
        reasons.append("INVALID_CURRENCY")
    amounts = [parse_money(r[c]) for c in ("subtotal_amount", "delivery_fee", "discount_amount", "total_amount")]
    if any(a is None or a < 0 for a in amounts):
        reasons.append("INVALID_AMOUNT")
    if r["customer_id"] not in ctx.accepted_customers:
        reasons.append("ORPHAN_CUSTOMER_FK")
    if r["merchant_id"] not in ctx.accepted_merchants:
        reasons.append("ORPHAN_MERCHANT_FK")
    if reasons:
        return reasons, None
    return [], (r["order_id"], r["customer_id"], r["merchant_id"], ts, r["order_status"], currency, *amounts)


def validate_item(r: dict, ctx: Context):
    reasons: list[str] = []
    qty = parse_int(r["quantity"])
    if qty is None or qty <= 0:
        reasons.append("INVALID_QUANTITY")
    amounts = [parse_money(r[c]) for c in ("unit_price", "line_discount", "line_total")]
    if any(a is None or a < 0 for a in amounts):
        reasons.append("INVALID_AMOUNT")
    currency = normalize_currency(r["currency"])
    if currency is None:
        reasons.append("INVALID_CURRENCY")
    if r["order_id"] not in ctx.accepted_orders:
        reasons.append("PARENT_REJECTED_ORDER")
    if r["product_id"] not in ctx.accepted_products:
        reasons.append("PARENT_REJECTED_PRODUCT")
    if reasons:
        return reasons, None
    return [], (r["order_item_id"], r["order_id"], r["product_id"], qty, *amounts, currency)


def validate_package(stg: dict[str, list[dict]]) -> dict[str, FileResult]:
    """stg: ім'я файла -> рядки зі staging. Порядок: батьки перед дочірніми."""
    ctx = Context()
    out: dict[str, FileResult] = {}

    out["customers.csv"] = process_file("customers.csv", stg["customers.csv"], "customer_id", CUSTOMER_COLS, validate_customer, ctx)
    ctx.accepted_customers = out["customers.csv"].accepted_keys
    out["merchants.csv"] = process_file("merchants.csv", stg["merchants.csv"], "merchant_id", MERCHANT_COLS, validate_merchant, ctx)
    ctx.accepted_merchants = out["merchants.csv"].accepted_keys
    out["products.csv"] = process_file("products.csv", stg["products.csv"], "product_id", PRODUCT_COLS, validate_product, ctx)
    ctx.accepted_products = out["products.csv"].accepted_keys
    out["orders.csv"] = process_file("orders.csv", stg["orders.csv"], "order_id", ORDER_COLS, validate_order, ctx)
    ctx.accepted_orders = out["orders.csv"].accepted_keys
    out["order_items.csv"] = process_file("order_items.csv", stg["order_items.csv"], "order_item_id", ITEM_COLS, validate_item, ctx)
    return out
