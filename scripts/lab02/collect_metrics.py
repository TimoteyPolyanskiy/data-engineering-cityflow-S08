"""Збирає з PostgreSQL (останній SUCCESS-запуск) усі числа для звіту Лаби 2 у docs/lab02/metrics.json.

Звіт не містить жодного вручну вписаного числа: усе береться з audit.*, core.* і evidence.json.
Запуск: uv run python scripts/lab02/collect_metrics.py
"""

import json
import platform
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.lab02.db import get_connection  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BATCH = "S08-V1"
FILES = ["customers.csv", "merchants.csv", "products.csv", "orders.csv", "order_items.csv"]
CORE_KEYS = {"customers": "customer_id", "merchants": "merchant_id", "products": "product_id",
             "orders": "order_id", "order_items": "order_item_id"}


def clean(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def psql_client_version() -> str:
    """psql from the same container that runs DDL and 02_checks.sql."""
    try:
        out = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "--version"],
                             cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "не визначено"


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    names = [d.name for d in cur.description]
    return [clean(dict(zip(names, r))) for r in cur.fetchall()]


def main() -> None:
    with get_connection() as conn, conn.cursor() as cur:
        m: dict = {"batch_id": BATCH}

        cur.execute("SHOW server_version")
        server = cur.fetchone()[0]
        m["versions"] = {
            "python": platform.python_version(),
            "psycopg": psycopg.__version__,
            "libpq": psycopg.pq.version(),
            "postgres_server": server,
            "psql_client": psql_client_version(),
        }

        run = rows(cur, "SELECT run_id, started_at, finished_at, status FROM audit.pipeline_runs "
                        "WHERE batch_id = %s AND status = 'SUCCESS' ORDER BY run_id DESC LIMIT 1", (BATCH,))
        if not run:
            raise SystemExit("Немає жодного SUCCESS-запуску: спершу виконайте конвеєр.")
        run = run[0]
        run_id = run["run_id"]
        m["run"] = run
        m["runs_total"] = rows(cur, "SELECT status, count(*) AS n FROM audit.pipeline_runs GROUP BY 1 ORDER BY 1")

        m["file_stats"] = {r["source_file"]: r for r in rows(
            cur, "SELECT source_file, input_count, accepted_count, rejected_count, duplicate_count "
                 "FROM audit.run_file_stats WHERE run_id = %s", (run_id,))}
        m["reasons"] = rows(
            cur, "SELECT source_file, final_status, reason_code, count(*) AS n FROM audit.row_decisions "
                 "WHERE run_id = %s AND final_status <> 'accepted' GROUP BY 1, 2, 3 ORDER BY 1, 2, 3", (run_id,))
        m["notes"] = rows(
            cur, "SELECT source_file, code, count(*) AS n FROM audit.row_decisions, unnest(reason_codes) AS code "
                 "WHERE run_id = %s AND final_status = 'accepted' GROUP BY 1, 2 ORDER BY 1, 2", (run_id,))
        m["rejected_examples"] = rows(
            cur, "SELECT source_file, business_key, reason_code FROM audit.row_decisions "
                 "WHERE run_id = %s AND final_status = 'rejected' AND source_file <> 'order_items.csv' "
                 "ORDER BY source_file, source_row_number", (run_id,))

        m["sources"] = rows(cur, "SELECT source_file, sha256, row_count FROM audit.batch_sources WHERE batch_id = %s ORDER BY 1", (BATCH,))
        m["reconciliation"] = rows(
            cur, "SELECT check_name, scope, staging_value, core_value, ok FROM audit.reconciliation WHERE run_id = %s ORDER BY recon_id", (run_id,))

        # 1) дублікати PK
        m["pk_duplicates"] = {}
        for table, key in CORE_KEYS.items():
            cur.execute(f"SELECT count(*) FROM (SELECT {key} FROM core.{table} GROUP BY {key} HAVING count(*) > 1) x")
            m["pk_duplicates"][table] = cur.fetchone()[0]
        # 2) відсутні FK
        fk = {
            "orders → customers": "SELECT count(*) FROM core.orders o LEFT JOIN core.customers c USING (customer_id) WHERE c.customer_id IS NULL",
            "orders → merchants": "SELECT count(*) FROM core.orders o LEFT JOIN core.merchants x USING (merchant_id) WHERE x.merchant_id IS NULL",
            "products → merchants": "SELECT count(*) FROM core.products p LEFT JOIN core.merchants x USING (merchant_id) WHERE x.merchant_id IS NULL",
            "order_items → orders": "SELECT count(*) FROM core.order_items i LEFT JOIN core.orders o USING (order_id) WHERE o.order_id IS NULL",
            "order_items → products": "SELECT count(*) FROM core.order_items i LEFT JOIN core.products p USING (product_id) WHERE p.product_id IS NULL",
        }
        m["missing_fk"] = {}
        for name, sql in fk.items():
            cur.execute(sql)
            m["missing_fk"][name] = cur.fetchone()[0]

        # 3) core за валютами
        m["orders_by_currency"] = rows(
            cur, "SELECT currency, count(*) AS orders, sum(subtotal_amount) AS subtotal, sum(delivery_fee) AS delivery_fee, "
                 "sum(discount_amount) AS discount, sum(total_amount) AS total FROM core.orders GROUP BY 1 ORDER BY 1")
        m["items_by_currency"] = rows(
            cur, "SELECT currency, count(*) AS items, sum(quantity) AS quantity, sum(line_total) AS line_total "
                 "FROM core.order_items GROUP BY 1 ORDER BY 1")

        # 4) fan-out за валютами
        m["fanout"] = rows(cur, """
            WITH wrong AS (
                SELECT o.currency, count(*) AS joined_rows, sum(o.total_amount) AS inflated_sum
                FROM core.orders o JOIN core.order_items i ON i.order_id = o.order_id GROUP BY o.currency),
            truth AS (
                SELECT currency, count(*) AS order_rows, sum(total_amount) AS true_sum FROM core.orders GROUP BY currency),
            items_agg AS (
                SELECT order_id, sum(line_total) AS items_sum FROM core.order_items GROUP BY order_id),
            correct AS (
                SELECT o.currency, count(*) AS orders_with_items, sum(o.total_amount) AS orders_total, sum(a.items_sum) AS items_total
                FROM core.orders o JOIN items_agg a ON a.order_id = o.order_id GROUP BY o.currency)
            SELECT t.currency, t.order_rows, w.joined_rows, t.true_sum, w.inflated_sum,
                   c.orders_with_items, c.orders_total, c.items_total
            FROM truth t LEFT JOIN wrong w USING (currency) LEFT JOIN correct c USING (currency) ORDER BY 1""")

        # діагностика формул (не виправляємо значення джерела)
        m["formula_total"] = rows(
            cur, "SELECT order_id, currency, subtotal_amount, delivery_fee, discount_amount, total_amount, "
                 "(subtotal_amount + delivery_fee - discount_amount - total_amount) AS difference "
                 "FROM core.orders WHERE abs(subtotal_amount + delivery_fee - discount_amount - total_amount) > 0.01 ORDER BY order_id")
        cur.execute("""
            WITH a AS (SELECT order_id, sum(line_total) AS lt, sum(line_discount) AS ld FROM core.order_items GROUP BY order_id)
            SELECT count(*) AS orders,
                   count(*) FILTER (WHERE abs(o.subtotal_amount - a.lt) > 0.01) AS subtotal_ne_sum_line_total,
                   count(*) FILTER (WHERE abs(o.subtotal_amount - (a.lt + a.ld)) > 0.01) AS subtotal_ne_sum_line_total_plus_discount,
                   count(*) FILTER (WHERE abs(o.discount_amount - a.ld) > 0.01) AS discount_ne_sum_line_discount
            FROM core.orders o JOIN a USING (order_id)""")
        names = [d.name for d in cur.description]
        m["items_vs_orders"] = dict(zip(names, cur.fetchone()))

        # why SUM(orders.total_amount) != SUM(order_items.line_total): components per currency
        m["sum_breakdown"] = rows(cur, """
            WITH a AS (SELECT order_id, sum(line_total) AS line_total, sum(line_discount) AS line_discount
                       FROM core.order_items GROUP BY order_id)
            SELECT o.currency, count(*) AS orders, sum(o.subtotal_amount) AS subtotal, sum(o.delivery_fee) AS delivery_fee,
                   sum(o.discount_amount) AS discount, sum(o.total_amount) AS total,
                   sum(a.line_total) AS line_total, sum(a.line_discount) AS line_discount
            FROM core.orders o JOIN a USING (order_id) GROUP BY 1 ORDER BY 1""")
        # orders left in core without any accepted item, and why their items were rejected
        m["orders_without_items"] = rows(cur, """
            SELECT o.order_id, o.currency, string_agg(DISTINCT d.reason_code, ', ') AS item_reasons,
                   string_agg(DISTINCT s.product_id, ', ') AS products
            FROM core.orders o
            JOIN stg.order_items s ON s.order_id = o.order_id
            JOIN audit.row_decisions d ON d.run_id = %s AND d.source_file = 'order_items.csv'
                 AND d.source_row_number = s.source_row_number
            WHERE NOT EXISTS (SELECT 1 FROM core.order_items i WHERE i.order_id = o.order_id)
            GROUP BY 1, 2 ORDER BY 1""", (run_id,))
        # PARENT_REJECTED_* split by the parent that was rejected
        m["parent_rejected"] = rows(cur, """
            SELECT d.reason_code, p.source_file AS parent_file, p.business_key AS parent_key,
                   p.reason_code AS parent_reason, count(*) AS items
            FROM audit.row_decisions d
            JOIN stg.order_items s ON s.source_row_number = d.source_row_number
            JOIN audit.row_decisions p ON p.run_id = d.run_id AND p.final_status = 'rejected'
                 AND ((d.reason_code = 'PARENT_REJECTED_ORDER' AND p.source_file = 'orders.csv' AND p.business_key = s.order_id)
                   OR (d.reason_code = 'PARENT_REJECTED_PRODUCT' AND p.source_file = 'products.csv' AND p.business_key = s.product_id))
            WHERE d.run_id = %s AND d.source_file = 'order_items.csv' AND d.reason_code LIKE 'PARENT_REJECTED_%%'
            GROUP BY 1, 2, 3, 4 ORDER BY 1, 3""", (run_id,))

    evidence_path = ROOT / "docs/lab02/evidence.json"
    m["evidence"] = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {}
    checksums = ROOT / "docs/package_checksums.json"
    m["archives"] = json.loads(checksums.read_text(encoding="utf-8")) if checksums.exists() else {}

    out = ROOT / "docs/lab02/metrics.json"
    out.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Записано {out.relative_to(ROOT)} (run_id={run_id}, postgres {server})")


if __name__ == "__main__":
    main()
