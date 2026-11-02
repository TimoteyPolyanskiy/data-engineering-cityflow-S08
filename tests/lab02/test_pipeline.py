"""Тести надійності конвеєра на справжній PostgreSQL (пропускаються, якщо БД недоступна).

Докази (кількості до/після, run_id, тексти помилок) зберігаються в docs/lab02/evidence.json
і підтягуються у звіт автоматично. Навмисні fixtures створюються в tmp_path, а не в data/raw.
"""

import json
from pathlib import Path

import psycopg
import pytest

from src.lab02 import ingest, pipeline
from src.lab02.db import get_connection

EVIDENCE_PATH = Path("docs/lab02/evidence.json")
EVIDENCE: dict = {}
TABLES = [("customers", "customer_id"), ("merchants", "merchant_id"), ("products", "product_id"),
          ("orders", "order_id"), ("order_items", "order_item_id")]


@pytest.fixture(scope="module", autouse=True)
def database_ready():
    try:
        with get_connection() as conn:
            conn.execute("SELECT count(*) FROM audit.pipeline_runs")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL або схема audit недоступні: {exc}")
    yield
    if EVIDENCE:
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(json.dumps(EVIDENCE, ensure_ascii=False, indent=2), encoding="utf-8")


def snapshot() -> dict:
    """Стан core: кількості, відбиток набору ключів і суми окремо за валютами."""
    with get_connection() as conn, conn.cursor() as cur:
        counts, fingerprints = {}, {}
        for table, key in TABLES:
            cur.execute(f"SELECT count(*), coalesce(md5(string_agg({key}, ',' ORDER BY {key})), '') FROM core.{table}")
            counts[table], fingerprints[table] = cur.fetchone()
        cur.execute("SELECT currency, count(*), sum(total_amount) FROM core.orders GROUP BY 1 ORDER BY 1")
        orders = {c: {"orders": n, "total_amount": str(s)} for c, n, s in cur.fetchall()}
        cur.execute("SELECT currency, count(*), sum(line_total) FROM core.order_items GROUP BY 1 ORDER BY 1")
        items = {c: {"items": n, "line_total": str(s)} for c, n, s in cur.fetchall()}
    return {"counts": counts, "key_md5": fingerprints, "orders_by_currency": orders, "items_by_currency": items}


def last_run(status: str | None = None):
    sql = "SELECT run_id, batch_id, status, error_message FROM audit.pipeline_runs"
    params: tuple = ()
    if status:
        sql += " WHERE status = %s"
        params = (status,)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql + " ORDER BY run_id DESC LIMIT 1", params)
        return cur.fetchone()


def decision_counts(run_id: int) -> dict:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT source_file, final_status, count(*) FROM audit.row_decisions WHERE run_id = %s GROUP BY 1, 2 ORDER BY 1, 2",
            (run_id,),
        )
        return {f"{f}:{s}": n for f, s, n in cur.fetchall()}


def test_rerun_keeps_business_state_and_adds_new_run():
    run_1 = pipeline.run_pipeline("S08-V1")
    state_1 = snapshot()
    run_2 = pipeline.run_pipeline("S08-V1")
    state_2 = snapshot()
    assert run_2 > run_1, "повторний запуск має отримати новий run_id"
    assert state_1 == state_2, "кількості, набір ключів і суми за валютами мають збігтися"
    assert decision_counts(run_1) == decision_counts(run_2)
    assert last_run("SUCCESS")[0] == run_2
    EVIDENCE["idempotency"] = {"run_1": run_1, "run_2": run_2, "state_equal": state_1 == state_2,
                               "state_run_1": state_1, "state_run_2": state_2,
                               "decisions_equal": decision_counts(run_1) == decision_counts(run_2)}


def test_failure_after_core_change_rolls_back_everything_and_logs_failed_run():
    before = snapshot()

    def inject_bad_child(cur):
        # дочірній рядок із quantity = -1 порушує CHECK(quantity > 0) ПІСЛЯ того, як
        # core уже очищено й заповнено новими рядками в цій самій транзакції
        cur.execute(
            "INSERT INTO core.order_items (order_item_id, order_id, product_id, quantity, unit_price, line_discount, "
            "line_total, currency) SELECT 'TEST-NEG-QTY', order_id, product_id, -1, 1, 0, 1, 'UAH' "
            "FROM core.order_items LIMIT 1"
        )

    with pytest.raises(psycopg.errors.CheckViolation):
        pipeline.run_pipeline("S08-V1", after_publish_hook=inject_bad_child)

    after = snapshot()
    assert before == after, "ROLLBACK має повернути попередній стан усіх core-таблиць"
    run_id, _batch, status, error = last_run()
    assert status == "FAILED" and "quantity" in error.lower()

    recovery = pipeline.run_pipeline("S08-V1")
    assert snapshot() == before
    EVIDENCE["rollback"] = {
        "injected": "INSERT у core.order_items з quantity = -1 після TRUNCATE та вставки нових рядків",
        "failed_run_id": run_id, "failed_status": status, "error_message": error[:300],
        "state_before": before["counts"], "state_after": after["counts"], "state_equal": before == after,
        "recovery_run_id": recovery,
    }


def _sources_with(tmp_path, index, filename, content):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    sources = ingest.default_sources()
    sources[index] = {**sources[index], "file": path}
    return sources


def test_wrong_header_stops_before_publish(tmp_path):
    before = snapshot()
    sources = _sources_with(tmp_path, 0, "customers.csv", "invalid_col1,invalid_col2\n1,test\n")
    with pytest.raises(ValueError, match="Порушення схеми CSV"):
        pipeline.run_pipeline("TEST-BAD-HEADER", sources=sources)
    assert snapshot() == before
    run_id, batch, status, error = last_run()
    assert (batch, status) == ("TEST-BAD-HEADER", "FAILED")
    EVIDENCE["wrong_header"] = {"run_id": run_id, "status": status, "error_message": error[:200], "core_unchanged": True}


def test_missing_required_file_stops_before_publish(tmp_path):
    before = snapshot()
    sources = ingest.default_sources()
    sources[3] = {**sources[3], "file": tmp_path / "orders.csv"}  # файла не існує
    with pytest.raises(FileNotFoundError):
        pipeline.run_pipeline("TEST-MISSING-FILE", sources=sources)
    assert snapshot() == before
    run_id, batch, status, error = last_run()
    assert (batch, status) == ("TEST-MISSING-FILE", "FAILED")
    EVIDENCE["missing_file"] = {"run_id": run_id, "status": status, "error_message": error[:200], "core_unchanged": True}


def test_changed_content_under_same_batch_id_is_not_accepted(tmp_path):
    pipeline.run_pipeline("S08-V1")  # гарантує, що batch зареєстровано
    before = snapshot()
    original = ingest.default_sources()[3]["file"].read_text(encoding="utf-8")
    original = original if original.endswith("\n") else original + "\n"
    sources = _sources_with(tmp_path, 3, "orders.csv", original + original.splitlines()[1] + "\n")
    with pytest.raises(ValueError, match="змінився"):
        pipeline.run_pipeline("S08-V1", sources=sources)
    assert snapshot() == before
    run_id, _batch, status, error = last_run()
    assert status == "FAILED"
    EVIDENCE["changed_batch_content"] = {"run_id": run_id, "status": status, "error_message": error[:240], "core_unchanged": True}
    pipeline.run_pipeline("S08-V1")  # повертаємо журнал у «зелений» стан
