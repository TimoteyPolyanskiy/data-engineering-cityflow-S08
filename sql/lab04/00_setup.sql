-- Лише нові об’єкти ЛР4. core, lab03 та попередні stg-таблиці не змінюються.
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE TABLE IF NOT EXISTS audit.lab04_runs (
    run_id uuid PRIMARY KEY,
    student_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('RUNNING','SUCCESS','FAILED')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    raw_dir text NOT NULL,
    summary jsonb,
    error_code text
);
CREATE TABLE IF NOT EXISTS stg.lab04_records (
    student_id text NOT NULL,
    source text NOT NULL CHECK(source IN ('orders','order_items','delivery_events')),
    record_key text NOT NULL,
    payload jsonb NOT NULL,
    raw_path text NOT NULL,
    source_row_number integer NOT NULL CHECK(source_row_number > 0),
    first_run_id uuid NOT NULL REFERENCES audit.lab04_runs(run_id),
    loaded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(student_id,source,record_key)
);
