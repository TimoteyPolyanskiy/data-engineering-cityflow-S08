"""Тести правил приймання без БД. Fixtures — малі синтетичні набори, не raw-файли."""

import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.lab02 import validate as v


def make_row(columns, number, **values):
    row = {c: "" for c in columns}
    row.update(values)
    row["source_row_number"] = number
    return row


def customer(n, cid="C1", **kw):
    base = dict(customer_id=cid, full_name="Ann", email="a@example.test", phone="", city="Lviv",
                service_zone_id="Z1", registered_at="2025-01-01T10:00:00Z", customer_status="active")
    base.update(kw)
    return make_row(v.CUSTOMER_COLS, n, **base)


def merchant(n, mid="M1", **kw):
    base = dict(merchant_id=mid, merchant_name="Shop", merchant_type="grocery", city="Lviv",
                service_zone_id="Z1", opened_at="2020-01-01T10:00:00Z", merchant_status="active")
    base.update(kw)
    return make_row(v.MERCHANT_COLS, n, **base)


def product(n, pid="P1", **kw):
    base = dict(product_id=pid, merchant_id="M1", product_name="Milk", category="food",
                unit_price_uah="10.00", is_active="True", updated_at="2025-01-01T10:00:00Z")
    base.update(kw)
    return make_row(v.PRODUCT_COLS, n, **base)


def order(n, oid="O1", **kw):
    base = dict(order_id=oid, customer_id="C1", merchant_id="M1", created_at="2025-09-01T10:00:00Z",
                order_status="delivered", currency="UAH", subtotal_amount="10.00", delivery_fee="5.00",
                discount_amount="0.00", total_amount="15.00")
    base.update(kw)
    return make_row(v.ORDER_COLS, n, **base)


def item(n, iid="I1", **kw):
    base = dict(order_item_id=iid, order_id="O1", product_id="P1", quantity="1", unit_price="10.00",
                line_discount="0.00", line_total="10.00", currency="UAH")
    base.update(kw)
    return make_row(v.ITEM_COLS, n, **base)


def run(customers=(), merchants=(), products=(), orders=(), items=()):
    return v.validate_package({
        "customers.csv": list(customers), "merchants.csv": list(merchants), "products.csv": list(products),
        "orders.csv": list(orders), "order_items.csv": list(items),
    })


def by_key(result):
    return {d.business_key: d for d in result.decisions if d.business_key}


# ---------------------------------------------------------------------------
# Дати
# ---------------------------------------------------------------------------
def test_iso_z_and_offset_become_utc():
    assert v.parse_timestamp("2025-09-01T11:47:50Z") == datetime(2025, 9, 1, 11, 47, 50, tzinfo=timezone.utc)
    assert v.parse_timestamp("2025-09-01T13:47:50+02:00") == datetime(2025, 9, 1, 11, 47, 50, tzinfo=timezone.utc)


def test_dd_mm_yyyy_is_read_explicitly_as_utc_day_first():
    # 04/09/2025 — це 4 вересня, а не 9 квітня
    assert v.parse_timestamp("04/09/2025 11:32") == datetime(2025, 9, 4, 11, 32, tzinfo=timezone.utc)


def test_nanoseconds_are_truncated_to_microseconds():
    parsed = v.parse_timestamp("2026-03-09T23:37:51.562482847Z")
    assert parsed.microsecond == 562482


@pytest.mark.parametrize("bad", ["2026-19-45 25:61:00", "2025-09-01T10:00:00", "31/02/2025 10:00", "", "yesterday"])
def test_invalid_timestamps_are_rejected(bad):
    assert v.parse_timestamp(bad) is None


# ---------------------------------------------------------------------------
# Валюти, ціни, кількість
# ---------------------------------------------------------------------------
def test_currency_ua_h_is_not_guessed():
    assert v.normalize_currency("UA H") is None
    assert v.normalize_currency(" usd ") == "USD"


def test_active_product_with_zero_price_is_rejected_but_inactive_is_accepted():
    res = run(merchants=[merchant(1)], products=[
        product(1, "P-ACTIVE0", unit_price_uah="0.00", is_active="True"),
        product(2, "P-INACTIVE0", unit_price_uah="0.00", is_active="False"),
        product(3, "P-NEG", unit_price_uah="-1.00", is_active="False"),
    ])["products.csv"]
    decisions = by_key(res)
    assert decisions["P-ACTIVE0"].reason_code == "INVALID_PRICE"
    assert decisions["P-INACTIVE0"].status == "accepted"
    assert decisions["P-NEG"].reason_code == "INVALID_PRICE"


def test_order_with_ua_h_goes_to_quarantine_with_invalid_currency():
    res = run(customers=[customer(1)], merchants=[merchant(1)], orders=[order(1, currency="UA H")])["orders.csv"]
    assert res.decisions[0].status == "rejected" and res.decisions[0].reason_code == "INVALID_CURRENCY"
    assert res.decisions[0].payload["currency"] == "UA H"  # вихідне значення збережено


def test_non_positive_quantity_is_rejected_not_crashing_core():
    res = run(
        customers=[customer(1)], merchants=[merchant(1)], products=[product(1)], orders=[order(1)],
        items=[item(1, "I-NEG", quantity="-1"), item(2, "I-ZERO", quantity="0"), item(3, "I-OK")],
    )["order_items.csv"]
    decisions = by_key(res)
    assert decisions["I-NEG"].reason_code == "INVALID_QUANTITY"
    assert decisions["I-ZERO"].reason_code == "INVALID_QUANTITY"
    assert decisions["I-OK"].status == "accepted"


# ---------------------------------------------------------------------------
# Повтори, конфлікти, нормалізація
# ---------------------------------------------------------------------------
def test_exact_copy_is_duplicate_and_first_row_survives():
    res = run(customers=[customer(1, "C1"), customer(2, "C1")])["customers.csv"]
    assert [d.status for d in res.decisions] == ["accepted", "duplicate"]
    assert res.decisions[1].reason_code == "FULL_DUPLICATE"
    assert len(res.accepted_rows) == 1


def test_key_conflict_rejects_the_whole_group():
    res = run(customers=[customer(1, "C1", city="Lviv"), customer(2, "C1", city="Kyiv")])["customers.csv"]
    assert [d.status for d in res.decisions] == ["rejected", "rejected"]
    assert {d.reason_code for d in res.decisions} == {"KEY_CONFLICT"}
    assert res.accepted_rows == []


def test_edge_whitespace_is_trimmed_and_noted():
    res = run(customers=[customer(1, "C1", city=" Lviv ")])["customers.csv"]
    assert res.accepted_rows[0][2] == "Lviv"
    assert res.decisions[0].reason_codes == ["WHITESPACE_TRIMMED"]


def test_optional_phone_may_be_empty_and_empty_key_is_rejected():
    res = run(customers=[customer(1, "C1", phone=""), customer(2, "")])["customers.csv"]
    assert res.decisions[0].status == "accepted"
    assert res.decisions[1].reason_code == "EMPTY_KEY"


# ---------------------------------------------------------------------------
# Зв'язки і каскад
# ---------------------------------------------------------------------------
def test_orphans_and_parent_rejection_cascade():
    res = run(
        customers=[customer(1, "C1")],
        merchants=[merchant(1, "M1")],
        products=[product(1, "P-OK"), product(2, "P-ORPHAN", merchant_id="M-NONE")],
        orders=[order(1, "O-OK"), order(2, "O-NOCUST", customer_id="C-NONE"), order(3, "O-NOMERCH", merchant_id="M-NONE")],
        items=[
            item(1, "I-OK", order_id="O-OK", product_id="P-OK"),
            item(2, "I-BAD-ORDER", order_id="O-NOCUST", product_id="P-OK"),
            item(3, "I-BAD-PRODUCT", order_id="O-OK", product_id="P-ORPHAN"),
        ],
    )
    assert by_key(res["products.csv"])["P-ORPHAN"].reason_code == "ORPHAN_MERCHANT_FK"
    assert by_key(res["orders.csv"])["O-NOCUST"].reason_code == "ORPHAN_CUSTOMER_FK"
    assert by_key(res["orders.csv"])["O-NOMERCH"].reason_code == "ORPHAN_MERCHANT_FK"
    items = by_key(res["order_items.csv"])
    assert items["I-OK"].status == "accepted"
    assert items["I-BAD-ORDER"].reason_code == "PARENT_REJECTED_ORDER"
    assert items["I-BAD-PRODUCT"].reason_code == "PARENT_REJECTED_PRODUCT"


def test_every_row_gets_exactly_one_final_status_and_balance_holds():
    res = run(customers=[customer(1, "C1"), customer(2, "C1"), customer(3, "C2", registered_at="2026-19-45 25:61:00")])["customers.csv"]
    assert len(res.decisions) == 3
    counts = {s: sum(d.status == s for d in res.decisions) for s in ("accepted", "rejected", "duplicate")}
    assert sum(counts.values()) == 3 and counts == {"accepted": 1, "rejected": 1, "duplicate": 1}


# ---------------------------------------------------------------------------
# Регресійна перевірка на справжньому пакеті S08 (пропускається без raw-даних)
# ---------------------------------------------------------------------------
RAW = Path("data/raw")


def read_csv(path, columns):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        assert next(reader) == columns
        return [dict(zip(columns, row), source_row_number=i) for i, row in enumerate(reader, 1)]


@pytest.mark.skipif(not (RAW / "base_v1" / "orders.csv").exists(), reason="немає data/raw")
def test_s08_expected_decision_counts():
    stg = {
        "customers.csv": read_csv(RAW / "base_v1/customers.csv", v.CUSTOMER_COLS),
        "merchants.csv": read_csv(RAW / "base_v1/merchants.csv", v.MERCHANT_COLS),
        "products.csv": read_csv(RAW / "base_v1/products.csv", v.PRODUCT_COLS),
        "orders.csv": read_csv(RAW / "base_v1/orders.csv", v.ORDER_COLS),
        "order_items.csv": read_csv(RAW / "lab02_relational/order_items.csv", v.ITEM_COLS),
    }
    res = v.validate_package(stg)
    expected = {  # input, accepted, rejected, duplicate
        "customers.csv": (801, 800, 0, 1),
        "merchants.csv": (43, 42, 0, 1),
        "products.csv": (534, 531, 2, 1),
        "orders.csv": (6001, 5996, 4, 1),
        "order_items.csv": (14062, 14027, 35, 0),
    }
    for name, (total, acc, rej, dup) in expected.items():
        decisions = res[name].decisions
        got = (len(decisions), *(sum(d.status == s for d in decisions) for s in ("accepted", "rejected", "duplicate")))
        assert got == (total, acc, rej, dup), name
    orders = by_key(res["orders.csv"])
    assert orders["S08-O0002449"].reason_code == "INVALID_CURRENCY"
    assert orders["S08-O0003385"].reason_code == "INVALID_DATE"
    assert orders["S08-O0000044"].status == "accepted"  # DD/MM/YYYY прочитано як UTC
    assert by_key(res["products.csv"])["S08-P000074"].reason_code == "INVALID_PRICE"
