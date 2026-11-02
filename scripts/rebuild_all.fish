#!/usr/bin/env fish
# Повна перебудова: raw-дані → Лаба 1 → PostgreSQL → Лаба 2 → звіти (PDF).
# Запуск з будь-якого місця:  fish scripts/rebuild_all.fish [шлях-до-архівів-S08]
# Якщо шлях не вказано, лише перевіряється вже розпакований data/raw/.

set -l root (path resolve (status dirname)/..)
cd $root; or exit 1

function step
    echo
    echo "==> $argv"
end

function must
    $argv
    or begin
        echo "ПОМИЛКА у кроці: $argv" >&2
        exit 1
    end
end

set -l db_user cityflow_user
set -l db_name cityflow_s08

step "1. Залежності (uv sync)"
must uv sync
if not test -f .env
    cp .env.example .env
    echo "Створено .env із .env.example (змініть пароль за потреби)."
end

step "2. Raw-дані: розпакування та контрольні суми"
if test (count $argv) -gt 0
    must uv run python scripts/prepare_raw.py $argv[1]
else
    must uv run python scripts/prepare_raw.py
end

step "3. Лаба 1: профілювання (ноутбук), схема, звіт"
must uv run python notebooks/lab01/01_source_profiling.py
must uv run jupytext --to notebook --execute notebooks/lab01/01_source_profiling.py
must uv run python scripts/lab01/build_architecture.py
must uv run python scripts/lab01/generate_report.py

step "4. PostgreSQL: контейнер і DDL"
must docker compose up -d
set -l ready 0
for i in (seq 1 40)
    if docker compose exec -T postgres pg_isready -U $db_user -d $db_name >/dev/null 2>&1
        set ready 1
        break
    end
    sleep 1
end
test $ready -eq 1; or begin
    echo "PostgreSQL не став доступним" >&2
    exit 1
end
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U $db_user -d $db_name < sql/lab02/01_ddl.sql; or exit 1

step "5. Лаба 2: конвеєр, контрольні SQL, тести"
must uv run python -m src.lab02.pipeline
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U $db_user -d $db_name < sql/lab02/02_checks.sql > docs/lab02/checks_output.txt; or exit 1
cat docs/lab02/checks_output.txt
must uv run pytest tests -v

step "6. Метрики та звіт Лаби 2"
must uv run python scripts/lab02/collect_metrics.py
must uv run python scripts/lab02/generate_report.py

step "7. PDF-звіти (Typst)"
if command -q typst
    must typst compile docs/lab01/report_lab_01.typ docs/lab01/report_lab_01.pdf
    must typst compile docs/lab02/report_lab_02.typ docs/lab02/report_lab_02.pdf
else
    echo "typst не встановлено: .typ-файли створено, PDF — після встановлення typst" >&2
end

echo
echo "Готово. Перед здачею: вкажіть pr_url у docs/report_meta.json і перегенеруйте звіти (кроки 3 і 6–7)."
