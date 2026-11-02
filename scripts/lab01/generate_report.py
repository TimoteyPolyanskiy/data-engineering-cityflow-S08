"""Збирає docs/lab01/report_lab_01.typ з docs/lab01/metrics.json (результат виконання ноутбука).

Запуск: uv run python scripts/lab01/generate_report.py && typst compile docs/lab01/report_lab_01.typ
Жодного числа у звіті не вписано вручну: усе береться з metrics.json, report_meta.json і AI_USAGE.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typst_utils import (ROOT, ai_section, bullets, code, day, esc, integer, link_or_hint,  # noqa: E402
                         load_json, md, meta, render, table)

m = load_json("docs/lab01/metrics.json")
info = meta()
summary = {row["file"]: row for row in m["summary"]}
arch = m["archives"].get("cityflow_S08_base_v1.zip", {})

# ---- конфігурація -----------------------------------------------------------
repo = info["repo_url"]
pr = link_or_hint(info["lab01"]["pr_url"], "Pull Request", "docs/report_meta.json: вкажіть lab01.pr_url, коли створите PR")
sha_note = "збігається з наданою викладачем" if arch.get("matches_teacher") else "викладацька сума не записана"
config = "\n".join([
    bullets([
        f"Студент: {info['student']}, група {info['group']}; `student_id: {m['student_id']}` (пакет `{m['package_id']}`).",
        f"Вхідний архів: `cityflow_S08_base_v1.zip`, SHA-256 `{arch.get('sha256', 'не записано')}` ({sha_note}); "
        "файли звірено з `PACKAGE_INFO.json`.",
        "Середовище: Omarchy (Arch Linux, Wayland), fish, Neovim, tmux; контроль версій — git, lazygit, gh.",
        f"Python `{m['python']}`, менеджер `uv`, pandas `{m['pandas']}`, matplotlib, jupytext (залежності зафіксовано в `pyproject.toml` і `uv.lock`).",
        f"Гілка `{info['lab01']['branch']}`, тег `{info['lab01']['tag']}`.",
    ]),
    f"- Репозиторій: #link(\"{repo}\")[{esc(repo)}]; Pull Request: {pr}",
])

# ---- джерела ------------------------------------------------------------------
sources_table = table(
    ["1.25fr", "1.2fr", "1.6fr", "2.4fr", "1.1fr"],
    ["Файл", "Ключ", "Один рядок =", "Зв'язки (перевірено)", "Унікальних ID / рядків"],
    [
        ["`customers.csv`", "`customer_id`", "один клієнт", "батько для `orders.customer_id`", f"{integer(summary['customers.csv']['unique_ids'])} / {integer(summary['customers.csv']['rows'])}"],
        ["`merchants.csv`", "`merchant_id`", "один заклад-партнер", "батько для `products` і `orders`", f"{integer(summary['merchants.csv']['unique_ids'])} / {integer(summary['merchants.csv']['rows'])}"],
        ["`products.csv`", "`product_id`", "один товар закладу", "`merchant_id` → `merchants` (відсутніх батьків: " + str(len(m["orphans"]["products.merchant_id"])) + ")", f"{integer(summary['products.csv']['unique_ids'])} / {integer(summary['products.csv']['rows'])}"],
        ["`orders.csv`", "`order_id`", "одне замовлення", "`customer_id` → `customers` (" + str(len(m["orphans"]["orders.customer_id"])) + "), `merchant_id` → `merchants` (" + str(len(m["orphans"]["orders.merchant_id"])) + ")", f"{integer(summary['orders.csv']['unique_ids'])} / {integer(summary['orders.csv']['rows'])}"],
    ],
    aligns=["left", "left", "left", "left", "center"], size="8.5pt",
)

# ---- підсумкова таблиця ---------------------------------------------------------
summary_table = table(
    ["1.2fr", "0.8fr", "0.8fr", "0.9fr", "1fr", "1fr", "1.2fr", "2.1fr", "0.9fr"],
    ["Файл", "Рядків", "Колонок", "Унікальних ID", "Повних дублікатів", "Пропущених клітинок", "Часове поле", "Діапазон дат", "Некоректних дат"],
    [[f"`{r['file']}`", integer(r["rows"]), r["columns"], integer(r["unique_ids"]), r["full_duplicates"], r["missing_cells"],
      f"`{r['date_column']}`", f"{day(r['date_min'])} — {day(r['date_max'])}", r["invalid_dates"]] for r in m["summary"]],
    aligns=["left", "center", "center", "center", "center", "center", "left", "center", "center"], size="8pt", inset="4pt",
)

invalid = m["date_info"]["orders"]["invalid_rows"]
date_note = (
    md("Пропуск — порожнє поле; некоректна дата — непорожнє значення, що не є ISO 8601. ")
    + md(f"У `orders.created_at` таких значень {len(invalid)}: "
         + "; ".join(f"`{r['value']}` (`{r['id']}`)" for r in invalid)
         + ". Значення `DD/MM/YYYY` — лише припущення про формат; початкові значення збережено.")
    if invalid else md("Некоректних дат не виявлено.")
)
nan_total = sum(r["nan"] for r in m["missing"])
empty_total = sum(r["empty_field"] for r in m["missing"])
ws_total = sum(r["whitespace_only"] for r in m["missing"])
# NaN vs empty field vs whitespace: the file is also read as text (dtype=str, keep_default_na=False)
gaps = "; ".join(
    f"`{r['file']}` / `{r['column']}`: NaN — {r['nan']}, порожніх полів — {r['empty_field']}, "
    f"лише з пробілів — {r['whitespace_only']}, з пробілами по краях — {r['edge_whitespace']}"
    for r in m["missing"]
)
gaps_text = md(
    "«Пропущені клітинки» — це `NaN` після `pd.read_csv()`. Щоб відрізнити порожнє поле від рядка з пробілів, файли прочитано ще й як текст: "
    + gaps + ". "
    + (f"Отже, усі {nan_total} `NaN` — це порожні поля" if nan_total == empty_total else f"`NaN` — {nan_total}, порожніх полів — {empty_total}")
    + ("; рядків лише з пробілів немає" if ws_total == 0 else f"; рядків лише з пробілів — {ws_total}")
    + ". Пробіли по краях не дають `NaN`, тому в цій колонці таблиці їх не видно."
)

# ---- графіки ---------------------------------------------------------------------
total_rows = sum(m["statuses"].values())
labels = ", ".join(f"`{k}` — {integer(v)}" for k, v in m["statuses"].items())
status_text = md(f"Серед {integer(total_rows)} записів (разом із повним дублікатом): {labels}. "
                 "Статус `delivered` переважає; активних замовлень мало, що відповідає історичному зрізу. "
                 "Це підрахунки записів, а не перевірена виручка.")
d = m["daily"]
daily_text = md(
    f"За {d['days']} діб кількість записів на добу: мінімум {d['min']} ({d['min_day']}), максимум {d['max']} ({d['max_day']}), "
    f"медіана {d['median']:g}, середнє {d['mean']:g}. Середній місячний рівень найвищий у {d['high_month']} ({d['high_month_mean']:g}) "
    f"і найнижчий у {d['low_month']} ({d['low_month_mean']:g}); причину цих коливань дані пакета не пояснюють. "
    f"Доба рахується за UTC; якщо групувати за київським часом, межі доби зсуваються й діапазон стає {d['kyiv_min']}–{d['kyiv_max']} записів. "
    f"У графік не потрапили {d['excluded_non_iso']} записи з не-ISO датою."
)

# ---- реєстр проблем -----------------------------------------------------------------
def ids_cell(ids):
    return ", ".join(f"`{i}`" for i in ids[:3]) + ("…" if len(ids) > 3 else "")


findings_table = table(
    ["0.35fr", "1.5fr", "1.1fr", "0.45fr", "1.55fr", "2.7fr"],
    ["№", "Файл / поле", "Тип", "К-сть", "Приклад ID", "Проблема, вплив і дія"],
    [[i, f"`{f['file']}` / `{f['field']}`", f["kind"], f["count"], ids_cell(f["ids"]),
      f"{f['problem']}. Вплив: {f['impact']}. Дія: {f['action']}."] for i, f in enumerate(m["findings"], 1)],
    aligns=["center", "left", "left", "center", "left", "left"], size="8pt", inset="3.5pt",
)

# ---- висновки ---------------------------------------------------------------------------
dups = m["dups"]
dup_total = sum(v["full_duplicate_rows"] for v in dups.values())
conflicts = sum(v["key_conflicts"] for v in dups.values())
orph = m["orphans"]
orphan_total = sum(len(v) for v in orph.values())
orphan_ids = ", ".join(f"`{i}`" for v in orph.values() for i in v)
odd_currency = ", ".join(f"`{k}`" for k in m["currencies"] if k not in ("UAH", "USD", "EUR")) or "—"
zero_price = len(m["zero_price"])
missing_phone = len(m["missing_phone"])
formula = m["formula_bad"]
formula_text = (
    f"У {len(formula)} замовленні `subtotal + delivery_fee − discount` не дорівнює `total_amount` (`{formula[0]['order_id']}`)."
    if formula else "Формула суми замовлення виконується для всіх рядків."
)
all_dup_ids = ids_cell([i for v in dups.values() for i in v["ids"]])

conclusions = "\n".join("+ " + md(t) for t in [
    f"*Grain і ключі.* У всіх чотирьох файлах кандидатний ключ повторюється лише через повні дублікати (усього {dup_total}); конфліктів ключів {conflicts}.",
    f"*Зв'язки.* Знайдено {orphan_total} посилання на відсутні батьківські записи: {orphan_ids}.",
    f"*Значення, що потребують правил.* Код валюти {odd_currency}; {len(invalid)} не-ISO дати; {zero_price} товар із нульовою ціною (активний — потребує уточнення); "
    f"{missing_phone} порожніх телефонів; пробіли по краях у `city` та `category`. Нулі в `delivery_fee` і `discount_amount` помилкою не вважаються.",
    f"*Діагностика сум.* {formula_text}",
    "*Обмеження.* Це пасивний аудит: нічого не виправлялось, СУБД не підключалась. Причини дублікатів, обов'язковість `phone` і формат `DD/MM/YYYY` — припущення; графіки показують записи, а не бізнес-показники.",
])

q8 = md(
    f"*Підтверджено даними:* повних дублікатів {dup_total} ({all_dup_ids}); порожніх телефонів {missing_phone}; "
    f"відсутніх батьків {orphan_total} ({orphan_ids}); код валюти {odd_currency}; {len(invalid)} не-ISO дати. "
    "*Припущення:* що телефон необов'язковий; що `04/09/2025 11:32` означає 4 вересня; що нульова ціна активного товару — помилка "
    "(це правило навчального контракту Лаби 2, а не факт із даних); причина появи дублікатів. "
    "Поради ШІ перевірялись повторним обчисленням на файлах пакета й порівнянням із виведенням блокнота."
)

# ---- ключові перевірки: фрагменти коду з ноутбука + обчислений результат --------------------
def py_block(src: str) -> str:
    inner = src.strip("\n").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'#block(breakable: false)[#text(size: 8pt)[#raw("{inner}", block: true, lang: "python")]]'


key_result = md("Результат: " + "; ".join(
    f"`{n}` — унікальних ID {integer(summary[n + '.csv']['unique_ids'])} з {integer(summary[n + '.csv']['rows'])} рядків, "
    f"повних дублікатів {v['full_duplicate_rows']}, конфліктів {v['key_conflicts']}" for n, v in m["dups"].items()) + ".")
date_rows = "; ".join(f"`{r['value']}` (`{r['id']}`)" for r in invalid) or "немає"
missing_dates = ", ".join(f"`{n}` — {i['missing']}" for n, i in m["date_info"].items())
date_result = md(f"Результат: пропущених дат: {missing_dates}; некоректних — лише в `orders.created_at`: {date_rows}. "
                 "Початкові значення не змінюються: розбір робиться в окремій змінній.")
orphan_result = md("Результат: " + "; ".join(
    f"`{k}` — " + (", ".join(f"`{i}`" for i in v) or "0") for k, v in m["orphans"].items()) + ".")
code_checks = "\n\n".join([
    md("*Кандидатний ключ, повні дублікати й конфлікти ключа* (розділ 3.3 ноутбука):"),
    py_block("""
full = frame.duplicated(keep=False)                      # усі колонки однакові
key_dup = frame.duplicated(subset=[key], keep=False)     # повторюється лише ключ
conflicts = key_dup & ~full                              # той самий ключ, різні значення
"""),
    key_result,
    md("*Пропуск, порожнє поле й пробіли* (розділ 3.2): файл додатково читається як текст, бо `pd.read_csv()` перетворює порожнє поле на `NaN`:"),
    py_block("""
t = pd.read_csv(path, dtype=str, keep_default_na=False)  # порожнє поле лишається ""
stripped = t[col].str.strip()
empty_field = (t[col] == "").sum()
whitespace_only = ((stripped == "") & (t[col] != "")).sum()
edge_whitespace = ((t[col] != stripped) & (stripped != "")).sum()
"""),
    gaps_text,
    md("*Пропущені й некоректні дати* (розділ 3.4):"),
    py_block("""
parsed = pd.to_datetime(raw_col, format="ISO8601", errors="coerce", utc=True)
empty = raw_col.str.strip() == ""                        # пропуск
invalid = parsed.isna() & ~empty                         # значення є, але не ISO 8601
"""),
    date_result,
    md("*Посилання на відсутні батьківські записи* (розділ 3.6):"),
    py_block("""
orphan_orders_customer = o[~o["customer_id"].isin(c["customer_id"])]
orphan_orders_merchant = o[~o["merchant_id"].isin(m["merchant_id"])]
orphan_products_merchant = p[~p["merchant_id"].isin(m["merchant_id"])]
"""),
    orphan_result,
])

render(ROOT / "docs/lab01/report_lab_01.tpl.typ", ROOT / "docs/lab01/report_lab_01.typ", {
    "COURSE_YEAR": esc(info["course_year"]), "GROUP": esc(info["group"]), "STUDENT": esc(info["student"]),
    "TEACHER": esc(info["teacher"]), "CONFIG": config, "SOURCES_TABLE": sources_table, "SUMMARY_TABLE": summary_table,
    "DATE_NOTE": date_note, "STATUS_TEXT": status_text, "DAILY_TEXT": daily_text, "FINDINGS_TABLE": findings_table,
    "CONCLUSIONS": conclusions, "AI_TEXT": ai_section(1), "Q8": q8, "CODE_CHECKS": code_checks,
})
