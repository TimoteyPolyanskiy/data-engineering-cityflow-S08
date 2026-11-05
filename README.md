# CityFlow Data Engineering (student S08)

Навчальний проєкт з дисципліни «Методи та технології інженерії даних» (ЛНУ ім. І. Франка, ФЕП-34). Студент: Полянський Тимотей, `student_id = S08`.
Предметна область — сервіс міських замовлень і доставки **CityFlow**: клієнти, партнерські заклади, товари, замовлення та їхні позиції.
Проєкт розвивається етапами; тут — Лабораторні роботи №1 (профілювання джерел), №2 (PostgreSQL: завантаження, цілісність, транзакції) №3 (аналітичний SQL: CTE, віконні функції, план запиту й індекс) та №4 (надійне отримання даних із файлового пакета та REST API).

## Джерела даних
| Пакет | Файли | Каталог |
|---|---|---|
| `cityflow_S08_base_v1.zip` | customers, merchants, products, orders | `data/raw/base_v1/` |
| `cityflow_S08_lab02_relational_v1.zip` | order_items (+ payments, refunds, couriers, deliveries, service_zones — у Лабі 2 не завантажуються) | `data/raw/lab02_relational/` |

SHA-256 архівів і файлів — у `docs/package_checksums.json`. Raw-дані **не** входять до Git; у `data/sample/` лежать малі синтетичні вибірки.

## Схема проєкту (Architecture v0)
![Architecture v0](docs/lab01/architecture_v0.png)

Суцільні лінії — реалізоване в Лабі 1 (CSV → `data/raw/` → ноутбук профілювання → документація; Git зберігає код і документи, але не raw-дані). Пунктир — заплановані компоненти (API, база даних, сховище, трансформації, оркестрація, дашборд).

## Структура
```text
data/raw/ (поза Git), data/sample/lab01/
notebooks/lab01/01_source_profiling.py|.ipynb   # профілювання (jupytext: .py ↔ .ipynb)
src/lab02/{db,ingest,validate,pipeline}.py      # staging, правила приймання, публікація core
sql/lab02/{01_ddl,02_checks}.sql
sql/lab03/00–08_*.sql, 09_report_evidence.sql      # Лаба 3: комплект викладача + власні VIEW у 01 і 03
src/lab04/student.py (моє), main.py, support.py      # Лаба 4: три функції отримання + наданий завантажувач
tools/lab04/ sql/lab04/ tests/lab04/                # Лаба 4: локальний API, таблиці stg/audit, 26 відкритих тестів
tests/lab02/                                     # правила (без БД) і надійність (з PostgreSQL)
scripts/                                         # підготовка raw, схеми, збір метрик, генерація звітів
docs/lab01/  docs/lab02/  docs/package_checksums.json  docs/report_meta.json
```

## Встановлення й запуск
Потрібні: Python 3.14 (див. `.python-version`), [uv](https://docs.astral.sh/uv/), Docker, `typst` (лише для PDF).
```fish
uv sync                                    # залежності з uv.lock
cp .env.example .env                       # змініть пароль; .env у Git не потрапляє
uv run python scripts/prepare_raw.py <каталог-або-zip-з-архівами-S08>
fish scripts/rebuild_all.fish              # усе: Лаба 1 → PostgreSQL → Лаба 2 → звіти
```
Окремо: `uv run jupytext --to notebook --execute notebooks/lab01/01_source_profiling.py` (Restart & Run All);
`docker compose up -d`; `docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U cityflow_user -d cityflow_s08 < sql/lab02/01_ddl.sql`;
`uv run python -m src.lab02.pipeline`; `uv run pytest tests -v`.

Змінні конфігурації (без секретів): `DATA_RAW_PATH`, `POSTGRES_HOST/PORT/DB/USER/PASSWORD`, `STUDENT_ID`.
Версії (фактичні, з останнього запуску): Python 3.14.7, pandas 3.0.6, psycopg 3.3.6, PostgreSQL сервер 16.15 і клієнт `psql` 16.15 (образ `postgres:16-alpine`).

## Політика Лаби 2
Повний **snapshot**: у транзакції очищуються лише `core.*` (без `CASCADE`) і вставляється прийнятий набір; `stg` і `audit` зберігаються. Правила приймання — `docs/lab02/load_policy.md`, відповідність колонок — `docs/lab02/source_to_target.md`. Кожен CSV-запис має один статус у `audit.row_decisions`; звірка кількостей, ключів і сум окремо за валютою виконується в тій самій транзакції.

## Лаба 3: аналітичний SQL
Читає лише `core` з Лаби 2; нові об'єкти — тільки в схемі `lab03_cf` (`core`, `stg`, `audit` не змінюються).
```fish
docker compose up -d
fish scripts/lab03/run_lab03.fish          # 00→04, 09, потім 05→06 (прогрів + 3)→07→06 (прогрів + 3)→08
```
Скрипт виконує файли в порядку README комплекту й зберігає виводи в `docs/lab03/output/`, плани — у `docs/lab03/plan_before.txt` і `plan_after.txt`, часи й медіани — у `docs/lab03/output/bench_timings.txt`.
Власні рішення: `v_daily_orders` у `sql/lab03/01_daily_report.sql`, `v_running_orders` і `v_latest_customer_order` у `sql/lab03/03_windows.sql`. Період (`lab03_cf.settings`) обирається під час першого запуску й далі не змінюється.

## Лаба 4: файловий пакет і REST API → raw → staging
Нові об'єкти — лише `stg.lab04_records` і `audit.lab04_runs`; `core` і `lab03_cf` не змінюються.

Локальне налаштування (секрети лише у файлах поза Git):
1. Розпакуйте свій `CityFlow_Lab04_S08.zip` так, щоб з'явився `data/lab04_variant/` (каталог у `.gitignore`).
2. `cp data/lab04_variant/credentials.env .env.lab04` і впишіть у `DATABASE_URL` власне підключення (`postgresql://<user>:<password>@localhost:5432/cityflow_s08`). `.env.lab04` у Git не потрапляє; шаблон без значень — `.env.lab04.example`.
3. Залежності вже в `pyproject.toml` (`uv sync`); версії як у `requirements-lab04.txt`.

Порядок запуску з кореня репозиторію (API — в окремому терміналі; перезапуск сервера скидає навчальні збої 429/500):
```fish
docker compose up -d
uv run python tools/lab04/start_api.py                 # термінал 1, лишається працювати
uv run python src/lab04/main.py check                  # термінал 2
uv run python src/lab04/main.py init-db
uv run pytest -q tests/lab04                           # 26 тестів
uv run python src/lab04/main.py file                   # EXTRACTED_ONLY, у БД не пише
uv run python src/lab04/main.py api                    # EXTRACTED_ONLY, raw-сторінки в data/raw/lab04/<run_id>/api
uv run python src/lab04/main.py run --fail-before-commit   # лише ДО першого успішного run: FAILED, 0 нових записів
uv run python src/lab04/main.py run; uv run python src/lab04/main.py verify
uv run python src/lab04/main.py run; uv run python src/lab04/main.py verify   # повтор: inserted = 0
docker compose exec -T postgres psql -U cityflow_user -d cityflow_s08 < sql/lab04/01_verify.sql
uv run python scripts/lab04/check_broken_package.py    # змінений / неповний пакет відхиляється
```
Raw-копії (`data/raw/lab04/<run_id>/`: `source.zip`, `api/page_NNNN.json` + `.meta.json`, `run.json`, `run.log`) у Git не входять. Числа й пояснення — `docs/lab04/results.md`, виводи — `docs/lab04/output/`.

## Висновки та обмеження
1. Ключі й grain чотирьох файлів підтверджено; повторення ключів — лише повні дублікати.
2. Проблеми джерел (відсутні батьки, `UA H`, не-ISO дати, нульова ціна активного товару, пробіли) не виправляються вручну, а обробляються явними правилами з обліком.
3. Core публікується атомарно; повторний запуск не змінює бізнес-стан, збій відкочується, `FAILED` зберігається в журналі.
4. Суми `orders` і `order_items` рахуються й звіряються окремо за валютою; прямий JOIN завищує суми.
5. Обмеження: лише повний snapshot (без UPSERT/SCD); `payments`, `refunds`, `couriers`, `deliveries`, `service_zones` не завантажуються; швидкодія не вимірювалась.

Використання ШІ описано в `AI_USAGE.md`.
