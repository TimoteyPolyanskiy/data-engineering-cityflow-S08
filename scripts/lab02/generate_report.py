"""Збирає docs/lab02/report_lab_02.typ з docs/lab02/metrics.json (БД + evidence.json).

Запуск: uv run python scripts/lab02/collect_metrics.py && uv run python scripts/lab02/generate_report.py
Усі числа беруться з PostgreSQL і результатів тестів; у шаблоні вручну вписаних чисел немає.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typst_utils import (ROOT, ai_section, bullets, esc, integer, link_or_hint, load_json, md,  # noqa: E402
                         meta, money, render, table)

m = load_json("docs/lab02/metrics.json")
info = meta()
ev = m.get("evidence", {})
FILES = ["customers.csv", "merchants.csv", "products.csv", "orders.csv", "order_items.csv"]
TABLES = ["customers", "merchants", "products", "orders", "order_items"]
CURRENCIES = [r["currency"] for r in m["orders_by_currency"]]
v = m["versions"]

# ---- 1. конфігурація -----------------------------------------------------------------
pr = link_or_hint(info["lab02"]["pr_url"], info["lab02"]["pr_url"], "docs/report_meta.json: вкажіть lab02.pr_url, коли створите PR")
config = "\n".join([
    bullets([
        f"Студент: {info['student']}, група {info['group']}; `student_id: {info['student_id']}`, batch `{m['batch_id']}`, останній успішний запуск `run_id = {m['run']['run_id']}`.",
        f"Python `{v['python']}`, драйвер `psycopg {v['psycopg']}` (libpq `{v['libpq']}`), PostgreSQL сервер `{v['postgres_server']}`, клієнт `{v.get('psql_client', 'не визначено')}` (Docker `postgres:16-alpine`), тести `pytest`.",
        "Пароль і параметри підключення — у `.env` поза Git (`.env.example` без секретів); повні дані й дампи в Git не потрапляють.",
        f"Гілка `{info['lab02']['branch']}`, тег `{info['lab02']['tag']}`.",
    ]),
    f"- Репозиторій: #link(\"{info['repo_url']}\")[{esc(info['repo_url'])}]\n- Pull Request: {pr}",
])

# ---- 2. джерела -------------------------------------------------------------------------
arch_rows = []
for name, a in m["archives"].get("archives", {}).items():
    check = "збігається з наданою викладачем" if a.get("matches_teacher") else "суму викладача не надано; записано обчислену"
    arch_rows.append([f"`{name}`", f"`{a['sha256']}`", check])
files_rows = []
used = {"customers.csv": "cityflow_S08_base_v1.zip", "merchants.csv": "cityflow_S08_base_v1.zip", "products.csv": "cityflow_S08_base_v1.zip",
        "orders.csv": "cityflow_S08_base_v1.zip", "order_items.csv": "cityflow_S08_lab02_relational_v1.zip"}
for f in FILES:
    pkg = m["archives"].get("packages", {}).get(used[f], {})
    sha = pkg.get("files", {}).get(f, "")
    files_rows.append([f"`{f}`", f"`{pkg.get('directory', '')}`", f"`{sha[:24]}…`" if sha else "—"])
sources = (
    md(f"Пакети студента `{info['student_id']}` зберігаються в різних каталогах і не змішуються з іншими SXX; raw-файли не змінювались. "
       "`payments`, `refunds`, `couriers`, `deliveries`, `service_zones` у core не завантажуються.")
    + "\n\n"
    + bullets([f"{r[0]} — SHA-256 {r[1]} ({r[2]})" for r in arch_rows])
    + "\n\n"
    + table(["1.2fr", "1.6fr", "2.4fr"], ["Файл", "Каталог", "SHA-256 (початок, за PACKAGE_INFO.json)"], files_rows, size="7.5pt", inset="4pt")
)

# ---- 3. модель -----------------------------------------------------------------------------
model_table = table(
    ["1fr", "1fr", "1.7fr", "2.3fr"],
    ["Таблиця core", "PK", "Grain", "FK, NOT NULL та CHECK"],
    [
        ["`customers`", "`customer_id`", "один клієнт", "`full_name`, `city`, `registered_at` NOT NULL"],
        ["`merchants`", "`merchant_id`", "один заклад-партнер", "`merchant_name`, `city`, `opened_at` NOT NULL"],
        ["`products`", "`product_id`", "один товар закладу", "FK `merchant_id`; `unit_price_uah ≥ 0`; активний товар має ціну > 0 (`NOT is_active OR unit_price_uah > 0`)"],
        ["`orders`", "`order_id`", "одне замовлення", "FK `customer_id`, `merchant_id`; `currency IN (UAH, USD, EUR)`; усі суми ≥ 0"],
        ["`order_items`", "`order_item_id`", "одна товарна позиція", "FK `order_id`, `product_id`; `quantity > 0`; `unit_price`, `line_discount`, `line_total` ≥ 0; валюта з того ж переліку"],
    ],
    size="8pt", inset="6pt",
)

# ---- 4. правила ------------------------------------------------------------------------------
rules = bullets([
    "Типи: ID — `text`, кількість — `integer`, суми — `numeric(12,2)`, час — `timestamptz`. Порожній ключ і непридатна дата відхиляються; порожній телефон помилкою не є, невідоме число нулем не замінюється.",
    "Дати: ISO 8601 із `Z` або зсувом (→ UTC); `DD/MM/YYYY HH:MM` явно читається як UTC (день, потім місяць); ISO без зсуву й неможливі дати відхиляються. Частки секунди довші за мікросекунди відкидаються в core, оригінал лишається в staging.",
    "Валюти: `UAH`, `USD`, `EUR` (дозволена нормалізація — лише обрізання пробілів по краях і верхній регістр); код `UA H` не виправляється й відхиляється як `INVALID_CURRENCY`.",
    "Активний товар із ціною ≤ 0 відхиляється (`INVALID_PRICE`); для неактивного нуль допустимий. `quantity > 0`, суми ≥ 0.",
    "Повтори: точна бізнес-копія → перша лишається, решта `duplicate`; той самий ключ із різними значеннями → уся група `rejected / KEY_CONFLICT` (вибору «останнього» рядка немає).",
    "Зв'язки: дочірній запис із відсутнім або відхиленим батьком не потрапляє в core (`ORPHAN_*_FK`, `PARENT_REJECTED_ORDER`, `PARENT_REJECTED_PRODUCT`); INNER JOIN мовчки нічого не губить. Повна політика — `docs/lab02/load_policy.md`.",
])

# ---- 5. облік -------------------------------------------------------------------------------
stats = m["file_stats"]
acc_rows = []
for f in FILES:
    s = stats[f]
    ok = s["input_count"] == s["accepted_count"] + s["rejected_count"] + s["duplicate_count"]
    acc_rows.append([f"`{f}`", integer(s["input_count"]), integer(s["accepted_count"]), integer(s["rejected_count"]),
                     integer(s["duplicate_count"]), "так" if ok else "ПОРУШЕНО"])
reason_rows = [[f"`{r['source_file']}`", r["final_status"], f"`{r['reason_code']}`", integer(r["n"])] for r in m["reasons"]]
rej_examples = ", ".join(f"`{r['business_key']}` ({r['reason_code']})" for r in m["rejected_examples"] if r["reason_code"] != "FULL_DUPLICATE")
notes = ", ".join(f"`{n['source_file']}`: {n['code']} — {n['n']}" for n in m["notes"]) or "немає"
parent_total = sum(r["items"] for r in m["parent_rejected"])
parent_text = "; ".join(
    f"`{code}` — {sum(r['items'] for r in m['parent_rejected'] if r['reason_code'] == code)} "
    + "(" + ", ".join(f"`{r['parent_key']}` {r['parent_reason']} — {r['items']}" for r in m["parent_rejected"] if r["reason_code"] == code) + ")"
    for code in ("PARENT_REJECTED_ORDER", "PARENT_REJECTED_PRODUCT")
)
accounting = (
    table(["1.4fr", "0.8fr", "0.9fr", "0.9fr", "0.9fr", "1.9fr"], ["Файл", "Вхід (input)", "Прийнято", "Відхилено", "Дублікати", "input = accepted + rejected + duplicate"],
          acc_rows, aligns=["left", "center", "center", "center", "center", "center"], size="8pt", inset="6pt")
    + "\n\n"
    + md(f"Кількість і набір ключів у core звіряються саме з `accepted`. Кожен рядок має один фінальний статус у `audit.row_decisions`; "
         f"відхилені: {rej_examples}. Нормалізація пробілів (рядок лишається `accepted`): {notes}. "
         f"Каскад для `order_items` ({integer(parent_total)} позицій): {parent_text}.")
    + "\n\n"
    + table(["1.5fr", "1fr", "2.2fr", "0.8fr"], ["Файл", "Статус", "Причина", "К-сть"], reason_rows,
            aligns=["left", "left", "left", "center"], size="8pt", inset="3.5pt")
)

# ---- 6. SQL-звірки ----------------------------------------------------------------------------
recon = {(r["check_name"], r["scope"]): r for r in m["reconciliation"]}


def pair(check, scope, fmt):
    r = recon.get((check, scope))
    return (fmt(r["staging_value"]), fmt(r["core_value"]), r["ok"]) if r else ("—", "—", False)


recon_rows = []
for cur in CURRENCIES:
    n_s, n_c, n_ok = pair("orders_orders_count_by_currency", cur, integer)
    t_s, t_c, t_ok = pair("orders_total_amount_by_currency", cur, money)
    recon_rows.append(["`orders`", f"`{cur}`", f"{n_s} / {n_c}", f"{t_s} / {t_c}", "так" if n_ok and t_ok else "ні"])
key_diff = {r["scope"]: r for r in m["reconciliation"] if r["check_name"] == "key_set_difference"}
key_text = ", ".join(f"`{f}` — {integer(key_diff[f]['core_value'])}" for f in FILES if f in key_diff)
for cur in [r["currency"] for r in m["items_by_currency"]]:
    n_s, n_c, n_ok = pair("order_items_items_count_by_currency", cur, integer)
    t_s, t_c, t_ok = pair("order_items_line_total_by_currency", cur, money)
    recon_rows.append(["`order_items`", f"`{cur}`", f"{n_s} / {n_c}", f"{t_s} / {t_c}", "так" if n_ok and t_ok else "ні"])

fan_rows = [[f"`{r['currency']}`", integer(r["order_rows"]), integer(r["joined_rows"]), money(r["true_sum"]), money(r["inflated_sum"]),
             money(r["orders_total"]), money(r["items_total"])] for r in m["fanout"]]
formula = m["formula_total"]
iv = m["items_vs_orders"]
no_items = sum(int(r["order_rows"]) for r in m["fanout"]) - sum(int(r["orders_with_items"] or 0) for r in m["fanout"])
no_items_text = "; ".join(f"`{r['order_id']}`: позиції відхилено як {r['item_reasons']} через товар {r['products']}" for r in m["orders_without_items"])
uah = next(r for r in m["sum_breakdown"] if r["currency"] == "UAH")
formula_text = (
    "Формула `subtotal + delivery_fee − discount = total` не виконується в " + str(len(formula)) + " замовленні: "
    + "; ".join(f"`{r['order_id']}` ({r['currency']}, різниця {money(r['difference'])})" for r in formula) + ". "
    if formula else "Формула `subtotal + delivery_fee − discount = total` виконується для всіх замовлень core. "
)
checks = "\n\n".join([
    md(f"*1. Дублікати PK:* {', '.join(f'`{t}` — {n}' for t, n in m['pk_duplicates'].items())} (очікується 0)."),
    md(f"*2. Відсутні FK:* {', '.join(f'{k}: {n}' for k, n in m['missing_fk'].items())} (очікується 0)."),
    md("*3. Прийнятий набір у staging ↔ core: кількість, набір ключів і суми окремо за валютою* (валюти не об'єднуються). "
       f"Набір ключів: кількість ключів, які є лише з одного боку (accepted без core або core без accepted), — {key_text} (очікується 0)."),
    table(["1.2fr", "0.8fr", "1.5fr", "2.6fr", "0.6fr"], ["Таблиця", "Валюта", "Рядків (stg / core)", "Сума (`total_amount` / `line_total`) (stg / core)", "Збіг"],
          recon_rows, aligns=["left", "center", "center", "center", "center"], size="7.5pt", inset="3.5pt"),
    md("*4. Чому `SUM(orders.total_amount)` після JOIN із `order_items` завищена.* `orders` має рівень «одне замовлення», `order_items` — «одна позиція»; "
       "JOIN повторює `total_amount` для кожної позиції. Правильний запит спершу зводить позиції до рівня замовлення (CTE `items_agg`) і лише потім з'єднує 1:1; "
       "`SUM(DISTINCT total_amount)` не підходить, бо відкидає різні замовлення з однаковою сумою."),
    table(["0.8fr", "0.9fr", "0.9fr", "1.4fr", "1.4fr", "1.4fr", "1.4fr"],
          ["Валюта", "Рядків orders", "Рядків після JOIN", "Істинна `SUM(total)`", "`SUM` після JOIN", "`SUM(total)` (CTE)", "`SUM(line_total)` (CTE)"],
          fan_rows, aligns=["center"] * 7, size="7.5pt", inset="3.5pt"),
    "#raw(\"WITH items_agg AS (SELECT order_id, sum(line_total) AS items_sum FROM core.order_items GROUP BY order_id)\\n"
    "SELECT o.currency, count(*) AS orders_with_items, sum(o.total_amount) AS orders_total, sum(a.items_sum) AS items_total\\n"
    "FROM core.orders o JOIN items_agg a ON a.order_id = o.order_id GROUP BY o.currency;\", block: true, lang: \"sql\")",
    md(f"*Чому `SUM(total_amount)` не дорівнює `SUM(line_total)`* (для UAH {money(uah['total'])} проти {money(uah['line_total'])}, лише замовлення з позиціями). "
       "Це різні величини: `total_amount = subtotal + delivery_fee − discount`, а `line_total` — позиція після своєї знижки, без доставки. Складові окремо за валютою:"),
    table(["0.7fr", "0.8fr", "1.3fr", "1.2fr", "1.1fr", "1.3fr", "1.3fr", "1.1fr"],
          ["Валюта", "Замовлень", "`Σ subtotal`", "`Σ delivery_fee`", "`Σ discount`", "`Σ total`", "`Σ line_total`", "`Σ line_discount`"],
          [[f"`{r['currency']}`", integer(r["orders"]), money(r["subtotal"]), money(r["delivery_fee"]), money(r["discount"]),
            money(r["total"]), money(r["line_total"]), money(r["line_discount"])] for r in m["sum_breakdown"]],
          aligns=["center"] * 8, size="7.5pt", inset="3.5pt"),
    md(f"*Діагностика (значення джерела не змінювались).* {formula_text}"
       f"Рівність `subtotal_amount = Σ line_total` не виконується в {iv['subtotal_ne_sum_line_total']} із {iv['orders']} замовлень, бо `line_total` уже без знижки позиції; "
       f"натомість `subtotal_amount = Σ(line_total + line_discount)` порушено лише в {iv['subtotal_ne_sum_line_total_plus_discount']}, "
       f"а `discount_amount = Σ line_discount` — у {iv['discount_ne_sum_line_discount']} замовленнях (можливі незалежні округлення; причину дані не пояснюють). `total_amount` не вважається чистим виторгом. "
       f"Замовлень у core без жодної прийнятої позиції: {no_items} ({no_items_text}); через це «Рядків orders» і кількість замовлень у CTE-запиті відрізняються."),
])

# ---- 7. повторний запуск ---------------------------------------------------------------------
idem = ev.get("idempotency")
if idem:
    s1, s2 = idem["state_run_1"], idem["state_run_2"]
    rows = [[f"`core.{t}`", integer(s1["counts"][t]), integer(s2["counts"][t]), f"`{s1['key_md5'][t][:10]}`", f"`{s2['key_md5'][t][:10]}`",
             "так" if s1["counts"][t] == s2["counts"][t] and s1["key_md5"][t] == s2["key_md5"][t] else "ні"] for t in TABLES]
    for cur in sorted(s1["orders_by_currency"]):
        a, b = s1["orders_by_currency"][cur], s2["orders_by_currency"].get(cur, {})
        rows.append([f"сума `orders`, `{cur}`", money(a["total_amount"]), money(b.get("total_amount")), "—", "—", "так" if a == b else "ні"])
    idempotency = (
        md(f"Той самий пакет `{m['batch_id']}` оброблено двічі: `run_id = {idem['run_1']}` і `run_id = {idem['run_2']}`. Бізнес-стан не змінився "
           f"({'так' if idem['state_equal'] else 'НІ'}), рішення по рядках ідентичні ({'так' if idem['decisions_equal'] else 'НІ'}); у журналі з'явився новий `run`. "
           "Політика — повний snapshot: у транзакції очищується лише список core-таблиць (без `CASCADE`, `audit` не зачіпається) і вставляється прийнятий набір. "
           "Той самий `batch_id` із *іншим* вмістом файла відхиляється (SHA-256 у `audit.batch_sources`).")
        + "\n\n"
        + table(["2fr", "1fr", "1fr", "1.2fr", "1.2fr", "0.5fr"], ["Показник", "Після run 1", "Після run 2", "Відбиток ключів 1", "Відбиток ключів 2", "Збіг"],
                rows, aligns=["left", "center", "center", "center", "center", "center"], size="7.5pt", inset="3.5pt")
    )
else:
    idempotency = md("Дані про повторний запуск відсутні: виконайте `uv run pytest tests/lab02 -v`.")

# ---- 8. rollback і failed-run ----------------------------------------------------------------
def first_line(message: str, limit: int = 160) -> str:
    """First line of an error; a pytest temp path is shortened to the file name."""
    line = re.sub(r"/\S*/pytest-\S*/(\S+?\.csv)", r"…/\1", message.splitlines()[0])
    return line if len(line) <= limit else line[:limit].rstrip() + "…"


rb = ev.get("rollback")
if rb:
    rows = [[f"`core.{t}`", integer(rb["state_before"][t]), integer(rb["state_after"][t]), "так" if rb["state_before"][t] == rb["state_after"][t] else "ні"] for t in TABLES]
    neg = []
    for key, title in (("wrong_header", "неправильний заголовок CSV"), ("missing_file", "відсутній обов'язковий файл"),
                       ("changed_batch_content", "змінений вміст під тим самим `batch_id`")):
        e = ev.get(key)
        if e:
            neg.append([title, e["run_id"], f"`{e['status']}`", f"`{first_line(e['error_message'], 110)}`", "так" if e["core_unchanged"] else "НІ"])
    rollback = (
        md(f"Збій імітується *після* початку зміни core: у тій самій транзакції, де вже виконано `TRUNCATE` і вставку нових рядків, додається дочірній рядок "
           f"з `quantity = -1`, що порушує `CHECK (quantity > 0)`. Транзакція відкочується повністю; запис `FAILED` (`run_id = {rb['failed_run_id']}`) "
           f"робиться окремою транзакцією й зберігається разом із помилкою: `{first_line(rb['error_message'])}`. Потім виправлений запуск успішний (`run_id = {rb['recovery_run_id']}`).")
        + "\n\n"
        + table(["2fr", "1fr", "1fr", "0.6fr"], ["Таблиця", "До збою", "Після rollback", "Збіг"], rows,
                aligns=["left", "center", "center", "center"], size="8pt", inset="3.5pt")
        + "\n\n"
        + md("Негативні тести: збій має зупинити роботу *до* публікації, core залишається незмінним, а `FAILED` лишається в журналі.")
        + "\n\n"
        + table(["2fr", "0.6fr", "0.8fr", "3fr", "0.9fr"], ["Сценарій", "run_id", "Статус", "Помилка", "core без змін"], neg,
                aligns=["left", "center", "center", "left", "center"], size="7.5pt", inset="3.5pt")
    )
else:
    rollback = md("Дані про rollback відсутні: виконайте `uv run pytest tests/lab02 -v`.")

# ---- 9. висновки ------------------------------------------------------------------------------
tot_in = sum(stats[f]["input_count"] for f in FILES)
tot_acc = sum(stats[f]["accepted_count"] for f in FILES)
tot_rej = sum(stats[f]["rejected_count"] for f in FILES)
tot_dup = sum(stats[f]["duplicate_count"] for f in FILES)
failed_runs = next((r["n"] for r in m["runs_total"] if r["status"] == "FAILED"), 0)
ok_all = all(r["ok"] for r in m["reconciliation"])
conclusions = "\n".join("+ " + md(t) for t in [
    f"Усі {integer(tot_in)} вхідних записів мають рівно один фінальний статус: {integer(tot_acc)} прийнято, {integer(tot_rej)} відхилено, {integer(tot_dup)} повторів; нічого не видалено зі staging.",
    f"Core публікується однією транзакцією; усі {len(m['reconciliation'])} звірок (кількості, набори ключів, суми окремо за валютою, відсутні FK) {'пройдено' if ok_all else 'ПРОЙДЕНО НЕ ВСІ'}.",
    f"Повторний запуск не змінює бізнес-стан, а збої (у журналі `FAILED`: {failed_runs}) не залишають часткового результату.",
    "Суми по JOIN `orders` × `order_items` без попередньої агрегації завищуються; контрольні суми рахуються окремо за валютою.",
    "Обмеження: snapshot-модель (без UPSERT і SCD); `payments`, `refunds`, `couriers`, `deliveries`, `service_zones` не завантажуються; перевірка швидкості не виконувалась.",
])

# ---- 10. питання --------------------------------------------------------------------------------
questions = [
    ("1. Чим бізнес-ключ відрізняється від технічного ідентифікатора надходження?",
     "Бізнес-ключ (`customer_id`, `order_id` …) ідентифікує сутність у джерелі й переходить у core. `batch_id`, `source_file`, `source_row_number`, `loaded_at` описують конкретне надходження рядка; один і той самий бізнес-ключ може надійти кілька разів, тож технічний ідентифікатор ключем сутності не є."),
    ("2. Чому staging може містити повтори й `text`, хоча core має суворі типи та ключі?",
     "Staging — доказ того, що надійшло: прийняти треба *всі* записи, зокрема непридатні (неможлива дата, `UA H`), інакше `COPY` перервався б, а втрати стали б непомітними. Типи, ключі й `CHECK` захищають лише перевірену копію в core."),
    ("3. Чим відрізняються точний дублікат, конфлікт ключа й оновлення?",
     "Точний дублікат — усі бізнес-значення збігаються: лишається перша копія, решта `duplicate`. Конфлікт — той самий ключ із різними значеннями без достовірної версії: уся група `rejected / KEY_CONFLICT`. Оновлення — нова версія тієї самої сутності з надійною ознакою версії; у цьому пакеті такої ознаки немає, тому оновлення не припускається."),
    ("4. Чому `CHECK` не завжди замінює `NOT NULL`? Які правила не покриває FK?",
     "Для `NULL` вираз `CHECK (x > 0)` дає `unknown`, і рядок проходить, тому потрібні обидва обмеження. FK перевіряє лише існування батька; він не перевіряє валюту, суми, активність товару чи відповідність валюти позиції валюті замовлення."),
    ("5. Що станеться, якщо батьківський запис відхилено, а дочірній сам по собі валідний?",
     "Дочірній запис у core не потрапляє: він отримує `rejected` з `PARENT_REJECTED_ORDER` або `PARENT_REJECTED_PRODUCT` і лишається в staging та `audit.row_decisions`. Мовчазний INNER JOIN втратив би його без сліду."),
    ("6. Що саме охоплює ваша транзакція? Як доведено rollback після часткового виконання?",
     "Запис рішень у `audit.row_decisions`, очищення й заповнення п'яти core-таблиць, звірку та `SUCCESS`. Rollback доведено тестом: після `TRUNCATE` і вставки нових рядків додається позиція з `quantity = -1`; кількості й відбитки ключів усіх таблиць після відкату збігаються з початковими (таблиця вище)."),
    ("7. Чому failed-run потрібно записувати поза транзакцією, яку відкотили?",
     "`ROLLBACK` скасував би й запис про збій. Тому `FAILED` пишеться окремим з'єднанням і транзакцією після відкату, а `RUNNING` реєструється ще до публікації."),
    ("8. Чому збіг кількості рядків або однієї загальної суми недостатній?",
     "Помилки можуть компенсувати одна одну (зайвий і відсутній рядок), а суми різних валют не можна складати. Тому звіряється набір ключів в обидва боки, суми окремо за валютою й відсутні FK."),
    ("9. Чому повторний run не змінює бізнес-стан? Чим це відрізняється від нового snapshot?",
     "Той самий пакет (SHA-256 файлів збігається) і детермінований повний snapshot дають однаковий core; лише з'являється новий `run_id`. Новий snapshot — це інший пакет або вміст; змінений вміст під тим самим `batch_id` конвеєр відхиляє."),
    ("10. Як ви перевірили AI-assisted рішення і яку помилку воно могло приховати?",
     "Правила перевірено юніт-тестами на синтетичних fixtures, регресійним тестом на пакеті S08, звіркою відхилених ID з реєстром проблем Лаби 1 (pandas) і звіркою ключів accepted ↔ core в обидва боки, а збої — тестами rollback. Приховати могли б: нормалізацію `UA H` → `UAH`, читання `04/09/2025` як 9 квітня та змішування валют в одній сумі — усі три випадки виявлено й виправлено."),
]
q_text = "\n\n".join(f"*{md(q)}*\\\n{md(a)}" for q, a in questions)

render(ROOT / "docs/lab02/report_lab_02.tpl.typ", ROOT / "docs/lab02/report_lab_02.typ", {
    "COURSE_YEAR": esc(info["course_year"]), "GROUP": esc(info["group"]), "STUDENT": esc(info["student"]), "TEACHER": esc(info["teacher"]),
    "CONFIG": config, "SOURCES": sources, "MODEL_TABLE": model_table, "RULES": rules, "ACCOUNTING": accounting, "CHECKS": checks,
    "IDEMPOTENCY": idempotency, "ROLLBACK": rollback, "CONCLUSIONS": conclusions, "AI_TEXT": ai_section(2), "QUESTIONS": q_text,
})
