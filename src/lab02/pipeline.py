"""Конвеєр Лаби 2: staging -> рішення по рядках -> транзакційна публікація core -> звірка.

Порядок дій:
 1. RUNNING реєструється в окремій транзакції ДО публікації.
 2. CSV приймаються в stg (ingest.load_staging).
 3. Правила приймання (validate.py) дають рішення для кожного рядка.
 4. В одній транзакції: рішення -> audit, повна заміна core (snapshot), звірка,
    SUCCESS. Будь-яка помилка = ROLLBACK, а FAILED пишеться окремою транзакцією.
"""

from __future__ import annotations

from typing import Callable

from psycopg.types.json import Jsonb

from src.lab02 import ingest, validate
from src.lab02.db import get_connection

BATCH_ID = "S08-V1"

FILES = [
    # (файл, staging, core, ключ у core, колонки staging для читання)
    ("customers.csv", "stg.customers", "core.customers", "customer_id", validate.CUSTOMER_COLS),
    ("merchants.csv", "stg.merchants", "core.merchants", "merchant_id", validate.MERCHANT_COLS),
    ("products.csv", "stg.products", "core.products", "product_id", validate.PRODUCT_COLS),
    ("orders.csv", "stg.orders", "core.orders", "order_id", validate.ORDER_COLS),
    ("order_items.csv", "stg.order_items", "core.order_items", "order_item_id", validate.ITEM_COLS),
]

INSERT_SQL = {
    "customers.csv": "INSERT INTO core.customers (customer_id, full_name, city, registered_at) VALUES (%s, %s, %s, %s)",
    "merchants.csv": "INSERT INTO core.merchants (merchant_id, merchant_name, city, opened_at) VALUES (%s, %s, %s, %s)",
    "products.csv": (
        "INSERT INTO core.products (product_id, merchant_id, product_name, unit_price_uah, is_active) "
        "VALUES (%s, %s, %s, %s, %s)"
    ),
    "orders.csv": (
        "INSERT INTO core.orders (order_id, customer_id, merchant_id, created_at, order_status, currency, "
        "subtotal_amount, delivery_fee, discount_amount, total_amount) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    ),
    "order_items.csv": (
        "INSERT INTO core.order_items (order_item_id, order_id, product_id, quantity, unit_price, "
        "line_discount, line_total, currency) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    ),
}

DECISION_SQL = (
    "INSERT INTO audit.row_decisions (run_id, batch_id, source_file, source_row_number, business_key, "
    "final_status, reason_code, reason_codes, raw_payload) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::text[], %s)"
)


# ---------------------------------------------------------------------------
# Журнал спроб
# ---------------------------------------------------------------------------
def _register_run(batch_id: str) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit.pipeline_runs (batch_id, status) VALUES (%s, 'RUNNING') RETURNING run_id",
                (batch_id,),
            )
            return cur.fetchone()[0]


def _mark_failed(run_id: int, error: Exception) -> None:
    """Окрема транзакція: запис про збій не зникає разом із відкотом публікації."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE audit.pipeline_runs SET finished_at = clock_timestamp(), status = 'FAILED', "
                "error_message = %s WHERE run_id = %s",
                (f"{type(error).__name__}: {error}"[:2000], run_id),
            )


# ---------------------------------------------------------------------------
# Публікація
# ---------------------------------------------------------------------------
def _read_staging(cur, table: str, columns: list[str]) -> list[dict]:
    cur.execute(f"SELECT {', '.join(columns)}, source_row_number FROM {table} ORDER BY source_row_number")
    return [dict(zip(columns + ["source_row_number"], row)) for row in cur.fetchall()]


def _reconcile(cur, run_id: int) -> None:
    """Звіряє той самий прийнятий набір до (staging) і після (core) публікації."""
    problems: list[str] = []

    def record(check: str, scope: str, stg_value, core_value) -> None:
        ok = stg_value == core_value
        cur.execute(
            "INSERT INTO audit.reconciliation (run_id, check_name, scope, staging_value, core_value, ok) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (run_id, check, scope, stg_value, core_value, ok),
        )
        if not ok:
            problems.append(f"{check} [{scope}]: staging={stg_value} core={core_value}")

    for name, stg_table, core_table, key, _cols in FILES:
        cur.execute(f"SELECT count(*) FROM {stg_table}")
        input_count = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FILTER (WHERE final_status = 'accepted'), "
            "       count(*) FILTER (WHERE final_status = 'rejected'), "
            "       count(*) FILTER (WHERE final_status = 'duplicate'), count(*) "
            "FROM audit.row_decisions WHERE run_id = %s AND source_file = %s",
            (run_id, name),
        )
        accepted, rejected, duplicate, decided = cur.fetchone()
        record("rows_input_vs_decisions", name, input_count, decided)
        cur.execute(f"SELECT count(*) FROM {core_table}")
        record("rows_accepted_vs_core", name, accepted, cur.fetchone()[0])
        # набір ключів: accepted ↔ core, в обидва боки
        cur.execute(
            "SELECT count(*) FROM (SELECT business_key FROM audit.row_decisions "
            f"WHERE run_id = %s AND source_file = %s AND final_status = 'accepted' EXCEPT SELECT {key} FROM {core_table}) x",
            (run_id, name),
        )
        missing_in_core = cur.fetchone()[0]
        cur.execute(
            f"SELECT count(*) FROM (SELECT {key} FROM {core_table} EXCEPT SELECT business_key FROM audit.row_decisions "
            "WHERE run_id = %s AND source_file = %s AND final_status = 'accepted') x",
            (run_id, name),
        )
        extra_in_core = cur.fetchone()[0]
        record("key_set_difference", name, 0, missing_in_core + extra_in_core)
        cur.execute(
            "INSERT INTO audit.run_file_stats (run_id, source_file, input_count, accepted_count, rejected_count, "
            "duplicate_count) VALUES (%s, %s, %s, %s, %s, %s)",
            (run_id, name, input_count, accepted, rejected, duplicate),
        )

    # суми окремо за валютами: orders
    cur.execute(
        "SELECT upper(btrim(s.currency)), count(*), sum(btrim(s.subtotal_amount)::numeric), "
        "sum(btrim(s.delivery_fee)::numeric), sum(btrim(s.discount_amount)::numeric), sum(btrim(s.total_amount)::numeric) "
        "FROM stg.orders s JOIN audit.row_decisions d ON d.run_id = %s AND d.source_file = 'orders.csv' "
        "AND d.source_row_number = s.source_row_number AND d.final_status = 'accepted' GROUP BY 1",
        (run_id,),
    )
    stg_orders = {row[0]: row[1:] for row in cur.fetchall()}
    cur.execute(
        "SELECT currency, count(*), sum(subtotal_amount), sum(delivery_fee), sum(discount_amount), sum(total_amount) "
        "FROM core.orders GROUP BY 1"
    )
    core_orders = {row[0]: row[1:] for row in cur.fetchall()}
    for currency in sorted(set(stg_orders) | set(core_orders)):
        s, c = stg_orders.get(currency, (0, 0, 0, 0, 0)), core_orders.get(currency, (0, 0, 0, 0, 0))
        for label, a, b in zip(("orders_count", "subtotal", "delivery_fee", "discount", "total_amount"), s, c):
            record(f"orders_{label}_by_currency", currency, a, b)

    # суми окремо за валютами: order_items
    cur.execute(
        "SELECT upper(btrim(s.currency)), count(*), sum(btrim(s.quantity)::numeric), sum(btrim(s.line_total)::numeric) "
        "FROM stg.order_items s JOIN audit.row_decisions d ON d.run_id = %s AND d.source_file = 'order_items.csv' "
        "AND d.source_row_number = s.source_row_number AND d.final_status = 'accepted' GROUP BY 1",
        (run_id,),
    )
    stg_items = {row[0]: row[1:] for row in cur.fetchall()}
    cur.execute("SELECT currency, count(*), sum(quantity), sum(line_total) FROM core.order_items GROUP BY 1")
    core_items = {row[0]: row[1:] for row in cur.fetchall()}
    for currency in sorted(set(stg_items) | set(core_items)):
        s, c = stg_items.get(currency, (0, 0, 0)), core_items.get(currency, (0, 0, 0))
        for label, a, b in zip(("items_count", "quantity", "line_total"), s, c):
            record(f"order_items_{label}_by_currency", currency, a, b)

    # відсутні FK (очікується 0)
    fk_checks = {
        "orders->customers": "SELECT count(*) FROM core.orders o LEFT JOIN core.customers c USING (customer_id) WHERE c.customer_id IS NULL",
        "orders->merchants": "SELECT count(*) FROM core.orders o LEFT JOIN core.merchants m USING (merchant_id) WHERE m.merchant_id IS NULL",
        "products->merchants": "SELECT count(*) FROM core.products p LEFT JOIN core.merchants m USING (merchant_id) WHERE m.merchant_id IS NULL",
        "order_items->orders": "SELECT count(*) FROM core.order_items i LEFT JOIN core.orders o USING (order_id) WHERE o.order_id IS NULL",
        "order_items->products": "SELECT count(*) FROM core.order_items i LEFT JOIN core.products p USING (product_id) WHERE p.product_id IS NULL",
    }
    for scope, sql in fk_checks.items():
        cur.execute(sql)
        record("missing_fk", scope, 0, cur.fetchone()[0])

    if problems:
        raise ValueError("Звірка не пройдена: " + "; ".join(problems[:8]))


def _publish(cur, run_id: int, batch_id: str, hook: Callable | None) -> dict[str, validate.FileResult]:
    stg = {name: _read_staging(cur, table, cols) for name, table, _core, _key, cols in FILES}
    results = validate.validate_package(stg)

    decision_rows = [
        (run_id, batch_id, d.source_file, d.source_row_number, d.business_key, d.status, d.reason_code,
         d.reason_codes, Jsonb(d.payload) if d.payload is not None else None)
        for name, *_ in FILES for d in results[name].decisions
    ]
    cur.executemany(DECISION_SQL, decision_rows)

    # Повний snapshot: лише core-таблиці проєкту, без CASCADE (audit не зачіпається).
    cur.execute("TRUNCATE TABLE core.order_items, core.orders, core.products, core.merchants, core.customers")
    for name, *_ in FILES:  # порядок FILES = порядок залежностей FK
        cur.executemany(INSERT_SQL[name], results[name].accepted_rows)

    if hook is not None:  # тестовий шов: імітація збою після початку зміни core
        hook(cur)

    _reconcile(cur, run_id)
    cur.execute(
        "UPDATE audit.pipeline_runs SET finished_at = clock_timestamp(), status = 'SUCCESS' WHERE run_id = %s",
        (run_id,),
    )
    return results


def run_pipeline(
    batch_id: str = BATCH_ID,
    *,
    sources: list[dict] | None = None,
    after_publish_hook: Callable | None = None,
) -> int:
    run_id = _register_run(batch_id)
    print(f"\n[PIPELINE] RUN_ID={run_id} (batch {batch_id}): RUNNING")
    try:
        ingest.load_staging(batch_id, sources)
        with get_connection() as conn:  # одна транзакція: COMMIT при виході, ROLLBACK при винятку
            with conn.cursor() as cur:
                results = _publish(cur, run_id, batch_id, after_publish_hook)
    except Exception as error:
        _mark_failed(run_id, error)
        print(f"[PIPELINE] RUN_ID={run_id}: FAILED ({type(error).__name__}: {str(error)[:200]})")
        raise

    print("=== Облік записів ===")
    for name, *_ in FILES:
        counts = {s: sum(1 for d in results[name].decisions if d.status == s) for s in ("accepted", "rejected", "duplicate")}
        total = sum(counts.values())
        print(f"  {name:16}: input={total} accepted={counts['accepted']} rejected={counts['rejected']} duplicate={counts['duplicate']}")
    print(f"[PIPELINE] RUN_ID={run_id}: SUCCESS")
    return run_id


if __name__ == "__main__":
    run_pipeline()
