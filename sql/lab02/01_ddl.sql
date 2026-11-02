-- sql/lab02/01_ddl.sql
-- Реляційна модель CityFlow S08: схеми stg (приймання), core (перевірена копія), audit (журнал).
-- Застосовується командою:
--   docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U cityflow_user -d cityflow_s08 < sql/lab02/01_ddl.sql
-- stg і core перестворюються (DROP без CASCADE: спершу дочірні таблиці, потім батьківські);
-- audit зберігається між застосуваннями (CREATE IF NOT EXISTS).

-- Захист від старої схеми audit з попередніх експериментів: потрібна чиста база.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'audit' AND table_name = 'rejected_rows' AND table_type = 'BASE TABLE') THEN
        RAISE EXCEPTION 'Знайдено стару схему audit: виконайте "docker compose down -v" і запустіть знову на чистій базі';
    END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS audit;

-- ============================================================================
-- 1. AUDIT: спроби запуску, облік вхідних пакетів, рішення по рядках, звірка
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
    run_id        BIGSERIAL PRIMARY KEY,
    batch_id      TEXT        NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at   TIMESTAMPTZ,
    status        TEXT        NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    error_message TEXT
);

-- Контрольна сума кожного файла пакета: той самий batch_id з іншим вмістом не
-- переписує історію мовчки (див. src/lab02/ingest.py).
CREATE TABLE IF NOT EXISTS audit.batch_sources (
    batch_id      TEXT        NOT NULL,
    source_file   TEXT        NOT NULL,
    sha256        TEXT        NOT NULL,
    row_count     INTEGER     NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, source_file)
);

-- Підсумковий статус кожного CSV-запису в межах run.
CREATE TABLE IF NOT EXISTS audit.row_decisions (
    run_id            BIGINT  NOT NULL REFERENCES audit.pipeline_runs(run_id),
    batch_id          TEXT    NOT NULL,
    source_file       TEXT    NOT NULL,
    source_row_number INTEGER NOT NULL,           -- номер CSV-запису після заголовка
    business_key      TEXT,
    final_status      TEXT    NOT NULL CHECK (final_status IN ('accepted', 'rejected', 'duplicate')),
    reason_code       TEXT,                       -- головна причина (NULL лише для accepted)
    reason_codes      TEXT[]  NOT NULL DEFAULT '{}',  -- усі причини/примітки нормалізації
    raw_payload       JSONB,                      -- вихідні значення для rejected/duplicate
    decided_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, source_file, source_row_number),
    CONSTRAINT chk_reason_matches_status CHECK ((final_status = 'accepted') = (reason_code IS NULL))
);

CREATE OR REPLACE VIEW audit.rejected_rows AS
SELECT * FROM audit.row_decisions WHERE final_status <> 'accepted';

CREATE TABLE IF NOT EXISTS audit.run_file_stats (
    stat_id         BIGSERIAL PRIMARY KEY,
    run_id          BIGINT  NOT NULL REFERENCES audit.pipeline_runs(run_id),
    source_file     TEXT    NOT NULL,
    input_count     INTEGER NOT NULL CHECK (input_count >= 0),
    accepted_count  INTEGER NOT NULL CHECK (accepted_count >= 0),
    rejected_count  INTEGER NOT NULL CHECK (rejected_count >= 0),
    duplicate_count INTEGER NOT NULL CHECK (duplicate_count >= 0),
    UNIQUE (run_id, source_file),
    CONSTRAINT chk_file_balance CHECK (input_count = accepted_count + rejected_count + duplicate_count)
);

-- Результати звірки staging(accepted) ↔ core, окремо за валютами.
CREATE TABLE IF NOT EXISTS audit.reconciliation (
    recon_id      BIGSERIAL PRIMARY KEY,
    run_id        BIGINT  NOT NULL REFERENCES audit.pipeline_runs(run_id),
    check_name    TEXT    NOT NULL,
    scope         TEXT    NOT NULL,
    staging_value NUMERIC,
    core_value    NUMERIC,
    ok            BOOLEAN NOT NULL
);

-- ============================================================================
-- 2. STAGING: оригінальні значення як TEXT + походження рядка
-- ============================================================================
DROP TABLE IF EXISTS stg.order_items;
DROP TABLE IF EXISTS stg.orders;
DROP TABLE IF EXISTS stg.products;
DROP TABLE IF EXISTS stg.merchants;
DROP TABLE IF EXISTS stg.customers;

CREATE TABLE stg.customers (
    customer_id TEXT, full_name TEXT, email TEXT, phone TEXT, city TEXT,
    service_zone_id TEXT, registered_at TEXT, customer_status TEXT,
    batch_id TEXT NOT NULL, source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE stg.merchants (
    merchant_id TEXT, merchant_name TEXT, merchant_type TEXT, city TEXT,
    service_zone_id TEXT, opened_at TEXT, merchant_status TEXT,
    batch_id TEXT NOT NULL, source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE stg.products (
    product_id TEXT, merchant_id TEXT, product_name TEXT, category TEXT,
    unit_price_uah TEXT, is_active TEXT, updated_at TEXT,
    batch_id TEXT NOT NULL, source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE stg.orders (
    order_id TEXT, customer_id TEXT, merchant_id TEXT, created_at TEXT,
    order_status TEXT, currency TEXT, subtotal_amount TEXT, delivery_fee TEXT,
    discount_amount TEXT, total_amount TEXT,
    batch_id TEXT NOT NULL, source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE stg.order_items (
    order_item_id TEXT, order_id TEXT, product_id TEXT, quantity TEXT,
    unit_price TEXT, line_discount TEXT, line_total TEXT, currency TEXT,
    batch_id TEXT NOT NULL, source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- ============================================================================
-- 3. CORE: типи, PK/FK, NOT NULL та погоджені CHECK
-- ============================================================================
DROP TABLE IF EXISTS core.order_items;
DROP TABLE IF EXISTS core.orders;
DROP TABLE IF EXISTS core.products;
DROP TABLE IF EXISTS core.merchants;
DROP TABLE IF EXISTS core.customers;

CREATE TABLE core.customers (
    customer_id   TEXT PRIMARY KEY,
    full_name     TEXT        NOT NULL,
    city          TEXT        NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE core.merchants (
    merchant_id   TEXT PRIMARY KEY,
    merchant_name TEXT        NOT NULL,
    city          TEXT        NOT NULL,
    opened_at     TIMESTAMPTZ NOT NULL
);

CREATE TABLE core.products (
    product_id     TEXT PRIMARY KEY,
    merchant_id    TEXT          NOT NULL REFERENCES core.merchants(merchant_id),
    product_name   TEXT          NOT NULL,
    unit_price_uah NUMERIC(12,2) NOT NULL CHECK (unit_price_uah >= 0),
    is_active      BOOLEAN       NOT NULL,
    -- навчальний контракт: активний товар має додатну ціну, для неактивного нуль допустимий
    CONSTRAINT chk_products_active_price CHECK (NOT is_active OR unit_price_uah > 0)
);

CREATE TABLE core.orders (
    order_id        TEXT PRIMARY KEY,
    customer_id     TEXT          NOT NULL REFERENCES core.customers(customer_id),
    merchant_id     TEXT          NOT NULL REFERENCES core.merchants(merchant_id),
    created_at      TIMESTAMPTZ   NOT NULL,
    order_status    TEXT          NOT NULL,
    currency        TEXT          NOT NULL CHECK (currency IN ('UAH', 'USD', 'EUR')),
    subtotal_amount NUMERIC(12,2) NOT NULL CHECK (subtotal_amount >= 0),
    delivery_fee    NUMERIC(12,2) NOT NULL CHECK (delivery_fee >= 0),
    discount_amount NUMERIC(12,2) NOT NULL CHECK (discount_amount >= 0),
    total_amount    NUMERIC(12,2) NOT NULL CHECK (total_amount >= 0)
);

CREATE TABLE core.order_items (
    order_item_id TEXT PRIMARY KEY,
    order_id      TEXT          NOT NULL REFERENCES core.orders(order_id),
    product_id    TEXT          NOT NULL REFERENCES core.products(product_id),
    quantity      INTEGER       NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    line_discount NUMERIC(12,2) NOT NULL CHECK (line_discount >= 0),
    line_total    NUMERIC(12,2) NOT NULL CHECK (line_total >= 0),
    currency      TEXT          NOT NULL CHECK (currency IN ('UAH', 'USD', 'EUR'))
);
