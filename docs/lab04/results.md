# Лабораторна 4 — результати

Student ID: S08
Python / PostgreSQL: Python 3.14.7 (uv; requests 2.32.5, psycopg 3.3.6, pytest 9.1.1) / PostgreSQL 16.15 (Docker `postgres:16-alpine`)
Коміт / Pull Request: гілка `lab/04-ingestion`, https://github.com/TimoteyPolyanskiy/data-engineering-cityflow-S08/pull/4
SHA-256 вихідного ZIP: `cityflow_S08_batch_01_normal_v1.zip` — `84017962ee62af3ba7c05c2108fd518eab5457fce5b4356a0068353d3ae3744c` (збігається з `package_sha256` у `expected_counts.json`); архів варіанта `CityFlow_Lab04_S08.zip` — `147bfaaf726178db012cdc0b21d838b677993e961abd54ecd473700598879ab8`

## Кількості для власного варіанта

Значення expected взяти з data/lab04_variant/expected_counts.json, actual — з власного запуску.

| Джерело | Received | Unique | Duplicates in input | Inserted (run 1) | Inserted (run 2) |
|---|---:|---:|---:|---:|---:|
| orders | 420 | 420 | 0 | 420 | 0 |
| order_items | 966 | 966 | 0 | 966 | 0 |
| delivery_events | 4064 | 4064 | 0 | 4064 | 0 |

Expected (`expected_counts.json`): orders 420, order_items 966, api_records 4064, api_unique_events 4064, api_duplicate_records 0, сторінок 41 — усе збігається. У run 2 `already_present` = 420 / 966 / 4064 = unique.

## Пагінація та повнота

Кількість сторінок: 41 (40 × 100 + 64).
Сума count / total_count: 4064 / 4064.
Кількість унікальних event_id: 4064 (у Python після `prepare_records` і окремо в БД: `COUNT(DISTINCT payload->>'event_id') = 4064`).
Чому received може відрізнятися від unique: джерело може віддати ту саму подію двічі (повтор сторінки, повторна доставка події). `received` рахує всі отримані записи, `unique` — різні ключі; у варіанті S08 повторів немає, тому вони рівні.

## Тести й контрольований збій

26 тестів: 26 passed (`pytest -q tests/lab04 -k file` — 5 passed; `-k "retry or timeout or attempts or tls"` — 11 passed; усі — 26 passed).
HTTP 429: сторінка 1, спроба 1 → 429, пауза 1 с (більше з backoff 1 с і Retry-After 1 с), спроба 2 → 200; HTTP 500: сторінка 2, спроба 1 → 500, пауза 1 с, спроба 2 → 200.
Run ID зі збоєм до COMMIT: `493a2615-1438-428b-bf0b-83e1b6b4800e` (код завершення 1, `error_code = INJECTED_BEFORE_COMMIT`).
Кількість staging до / після збою: 0 / 0.
Audit-статус: FAILED; `records_first_inserted_by_run = 0`; raw-каталог цієї спроби (source.zip, 41 сторінка + meta, run.json, run.log) залишився.
Перший успішний run ID: `3fdd023e-b4ee-469f-8e20-27a4d6bb88f7` (5450 нових записів); повторний run ID: `80fa2c44-ac54-4626-b538-b31e8e355fcc` (0 нових).
verify: `ok: true` після обох запусків (orders 420, order_items 966, delivery_events 4064).

Додатково (`scripts/lab04/check_broken_package.py`): копія пакета зі зміненим `refunds.csv` → `INVALID_CHECKSUM:refunds.csv`; без `order_items.csv` → `MISSING_FILE:order_items.csv`; оригінал з чужим student_id → `INVALID_STUDENT_ID`.

Усі виводи — `docs/lab04/output/`.

## Пояснення своїми словами

1. Чому завершувати обхід після першої короткої сторінки неправильно?
   Розмір сторінки — не сигнал кінця: сервер може віддати коротку сторінку посередині (обмеження, фільтр, збій), а повна сторінка може бути останньою. Кінець визначає лише `next_cursor = null`; додатково звіряємо суму записів із `total_count`.
2. Чим raw-відповідь відрізняється від JSONB payload у staging?
   Raw — точні байти тіла відповіді (`page_0001.json`) з SHA-256 і метаданими запиту; їх можна перевірити й повторно обробити. JSONB — розібране значення одного запису: PostgreSQL не зберігає пробіли, порядок ключів і форматування, тому JSONB не доводить, що саме прийшло від джерела.
3. Чому не можна мовчки пропустити однаковий ID з іншим payload?
   Це конфлікт: джерело змінило запис або є помилка. Якщо мовчки залишити перший варіант, ми втратимо зміну й не дізнаємося про неї. Тому `prepare_records` зупиняє запуск (`CONFLICT_IN_INPUT`), а `publish` — при розбіжності з уже збереженим (`CONFLICT_WITH_TARGET`).
4. Що саме означає SUCCESS у цій роботі, а чого він не доводить?
   SUCCESS означає: пакет і всі сторінки API отримано й технічно перевірено (контрольні суми, заголовки, конверт відповіді, кількості), усі унікальні записи є в `stg.lab04_records`, і це зафіксовано однією транзакцією. Він не доводить бізнес-коректності сум, статусів і зв'язків (це ЛР №5) і не гарантує, що джерело віддало всі події, яких ми не бачили.

## AI BLACK BOX (80–150 слів)

Див. розділ «Лабораторна робота №4» у `AI_USAGE.md` (той самий текст є у PDF-звіті).
