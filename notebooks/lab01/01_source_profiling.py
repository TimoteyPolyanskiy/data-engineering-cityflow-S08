# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Лабораторна робота №1. Первинне дослідження джерел даних (CityFlow, S08)
#
# **Студент:** Полянський Тимотей, група ФЕП-34, `student_id = S08`.
# Блокнот лише **досліджує** сирі дані й нічого в них не виправляє: початкові CSV залишаються
# незмінними в `data/raw/base_v1/`. Усі числа в звіті та документації беруться з виконання цього
# блокнота (файли `docs/lab01/metrics.json`, `data_quality_findings.md`, `data_dictionary.md`
# записуються в останніх комірках).

# %%
import json
import platform
import hashlib
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

try:
    from IPython.display import display
except ImportError:  # запуск як звичайного скрипта
    display = print


def find_root() -> Path:
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("Не знайдено корінь проєкту (pyproject.toml)")


ROOT = find_root()
RAW = ROOT / "data" / "raw" / "base_v1"
DOCS = ROOT / "docs" / "lab01"
DOCS.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

print("Python", platform.python_version(), "| pandas", pd.__version__)

# %% [markdown]
# ## 1. Пакет даних і контрольні суми
# SHA-256 архіву звірено зі значенням викладача скриптом `scripts/prepare_raw.py`
# (результат — `docs/package_checksums.json`). Тут додатково перевіряємо, що розпаковані файли
# збігаються з `PACKAGE_INFO.json` пакета, тобто raw-дані не змінювалися.

# %%
package_info = json.loads((RAW / "PACKAGE_INFO.json").read_text(encoding="utf-8"))
checksums_path = ROOT / "docs" / "package_checksums.json"
checksums = json.loads(checksums_path.read_text(encoding="utf-8")) if checksums_path.exists() else {}

print("package_id:", package_info["package_id"], "| student_id:", package_info["student_id"])
for item in package_info["files"]:
    actual = hashlib.sha256((RAW / item["path"]).read_bytes()).hexdigest()
    status = "OK" if actual == item["sha256"] else "ЗМІНЕНО!"
    print(f"{item['path']:15} {actual[:16]}…  {status}")
    assert actual == item["sha256"], f"{item['path']} відрізняється від PACKAGE_INFO.json"
for name, info in checksums.get("archives", {}).items():
    print("архів", name, info["sha256"])

# %% [markdown]
# ## 2. Зчитування та структура даних
# Кожен файл читається двічі:
# * `df[...]` — звичайний `pd.read_csv()` (типи визначає pandas, порожні поля стають `NaN`);
# * `txt[...]` — той самий файл як текст (`dtype=str`, `keep_default_na=False`): так видно
#   порожні рядки, рядки з пробілами та значення, які pandas мовчки перетворює.
#
# **Що представляє рядок і які зв'язки очікуються**
#
# | Файл | Один рядок = | Кандидатний ключ | Зв'язки |
# |---|---|---|---|
# | `customers.csv` | один клієнт | `customer_id` | батько для `orders.customer_id` |
# | `merchants.csv` | один заклад-партнер | `merchant_id` | батько для `products.merchant_id` та `orders.merchant_id` |
# | `products.csv` | один товар закладу | `product_id` | `merchant_id` → `merchants` |
# | `orders.csv` | одне замовлення | `order_id` | `customer_id` → `customers`, `merchant_id` → `merchants` |
#
# Унікальність кандидатних ключів нижче **перевіряється**, а не припускається.

# %%
SOURCES = {
    "customers": "customer_id",
    "merchants": "merchant_id",
    "products": "product_id",
    "orders": "order_id",
}
DATE_COL = {"customers": "registered_at", "merchants": "opened_at", "products": "updated_at", "orders": "created_at"}

df = {name: pd.read_csv(RAW / f"{name}.csv") for name in SOURCES}
txt = {name: pd.read_csv(RAW / f"{name}.csv", dtype=str, keep_default_na=False) for name in SOURCES}
for name, frame in df.items():
    print(f"{name:10} shape={frame.shape}")

# %% [markdown]
# Для відтворюваності без raw-даних у Git зберігаємо **малі синтетичні вибірки** (перші 100 рядків
# кожного файла) у `data/sample/lab01/`.

# %%
SAMPLE = ROOT / "data" / "sample" / "lab01"
SAMPLE.mkdir(parents=True, exist_ok=True)
for name, frame in df.items():
    frame.head(100).to_csv(SAMPLE / f"{name}_sample.csv", index=False)
print("Вибірки збережено в", SAMPLE.relative_to(ROOT))

# %% [markdown]
# ### 2.1 customers

# %%
d = df["customers"]
display(d.head()); display(d.tail(3)); display(d.sample(3, random_state=8))
print("shape:", d.shape); print("columns:", list(d.columns)); print("index:", d.index)
print(d.dtypes); d.info()

# %% [markdown]
# **Пояснення.** 801 запис і 8 колонок. `phone` pandas прочитав як `float64`: усі непорожні значення —
# цифри (знак `+` зникає), а порожні поля стали `NaN`. Телефон — це ідентифікатор, а не число для
# усереднення, тому *тип pandas не відповідає змісту*. Дати (`registered_at`) прочитано як текст.

# %% [markdown]
# ### 2.2 merchants

# %%
d = df["merchants"]
display(d.head()); display(d.tail(3)); display(d.sample(3, random_state=8))
print("shape:", d.shape); print("columns:", list(d.columns)); print("index:", d.index)
print(d.dtypes); d.info()

# %% [markdown]
# **Пояснення.** Довідник закладів: 43 записи, 7 колонок, пропусків немає. `opened_at` — текст,
# який потрібно явно перетворювати на дату.

# %% [markdown]
# ### 2.3 products

# %%
d = df["products"]
display(d.head()); display(d.tail(3)); display(d.sample(3, random_state=8))
print("shape:", d.shape); print("columns:", list(d.columns)); print("index:", d.index)
print(d.dtypes); d.info()

# %% [markdown]
# **Пояснення.** 534 товари, 7 колонок. `is_active` прочитано як `bool`, `unit_price_uah` як `float64`,
# `updated_at` — як текст (у товарів **є** часове поле `updated_at`).

# %% [markdown]
# ### 2.4 orders

# %%
d = df["orders"]
display(d.head()); display(d.tail(3)); display(d.sample(3, random_state=8))
print("shape:", d.shape); print("columns:", list(d.columns)); print("index:", d.index)
print(d.dtypes); d.info()

# %% [markdown]
# **Пояснення.** 6001 запис, 10 колонок. Суми — `float64`. Валюта і статус — категоріальні тексти,
# `created_at` — текст, що містить і коректні ISO-значення, і значення в інших форматах (див. розділ 5).

# %% [markdown]
# ## 3. Первинне профілювання
# ### 3.1 Числові й категоріальні колонки: `describe()`, `nunique()`, `value_counts()`

# %%
for name, frame in df.items():
    print(f"\n=== {name} ===")
    display(frame.describe(include="all").T)
    display(frame.nunique().to_frame("nunique").T)
    for col in frame.columns:
        if frame[col].nunique() <= 12:
            print(f"\nvalue_counts: {name}.{col}")
            print(frame[col].value_counts(dropna=False).to_string())

# %% [markdown]
# Значення `value_counts` беруться з **початкових** даних, тому різні написання однієї категорії
# (наприклад, місто з пробілами навколо) з'являються окремими рядками.

# %% [markdown]
# ### 3.2 Пропуски, порожні рядки та рядки з пробілами
# `NaN` у `df` — це порожнє поле CSV або явне «NA». У `txt` розрізняємо: порожнє поле (`""`),
# рядок лише з пробілів та значення з пробілами по краях.

# %%
def missing_report(name: str) -> pd.DataFrame:
    t, f = txt[name], df[name]
    rows = []
    for col in t.columns:
        stripped = t[col].str.strip()
        rows.append({
            "column": col,
            "nan": int(f[col].isna().sum()),
            "nan_pct": round(float(f[col].isna().mean()) * 100, 2),
            "empty_field": int((t[col] == "").sum()),
            "whitespace_only": int(((stripped == "") & (t[col] != "")).sum()),
            "edge_whitespace": int(((t[col] != stripped) & (stripped != "")).sum()),
        })
    return pd.DataFrame(rows)


missing = {name: missing_report(name) for name in SOURCES}
for name, rep in missing.items():
    flagged = rep[(rep[["nan", "empty_field", "whitespace_only", "edge_whitespace"]] > 0).any(axis=1)]
    print(f"\n{name}: колонки з пропусками або пробілами ({len(flagged)} з {len(rep)})")
    display(flagged if len(flagged) else "немає")

# %% [markdown]
# ### 3.3 Повні дублікати та повторення кандидатного ключа

# %%
dup_info = {}
for name, key in SOURCES.items():
    frame = df[name]
    full = frame.duplicated(keep=False)
    key_dup = frame.duplicated(subset=[key], keep=False)
    conflicts = key_dup & ~full
    dup_info[name] = {
        "full_duplicate_rows": int(frame.duplicated().sum()),
        "key_repeat_rows": int(frame.duplicated(subset=[key]).sum()),
        "key_conflicts": int(conflicts.sum()),
        "ids": sorted(frame.loc[full, key].unique().tolist()),
    }
    print(f"{name:10} unique {key}: {frame[key].nunique()} з {len(frame)} рядків | {dup_info[name]}")
    if full.any():
        display(frame[full])

# %% [markdown]
# Усі повтори ключів є **повними** дублікатами (однакові всі колонки); конфліктів «той самий ключ,
# різні значення» немає. Причину появи дублікатів джерело не пояснює, тому це лише спостереження.

# %% [markdown]
# ### 3.4 Часовий діапазон: пропущені та некоректні дати
# Дата вважається коректною, якщо відповідає ISO 8601 із `Z` або зсувом. Порожнє поле — *пропуск*;
# непорожнє значення, що не розбирається, — *некоректна дата*. Початкові значення зберігаються.

# %%
date_info = {}
iso_dates = {}
for name in SOURCES:
    col = DATE_COL[name]
    raw_col = txt[name][col]
    parsed = pd.to_datetime(raw_col, format="ISO8601", errors="coerce", utc=True)
    empty = raw_col.str.strip() == ""
    invalid = parsed.isna() & ~empty
    iso_dates[name] = parsed
    date_info[name] = {
        "column": col,
        "min": str(parsed.min()), "max": str(parsed.max()),
        "missing": int(empty.sum()), "invalid": int(invalid.sum()),
        "invalid_rows": [
            {"id": txt[name].loc[i, SOURCES[name]], "value": raw_col.loc[i]} for i in invalid[invalid].index
        ],
    }
    print(f"{name:10} {col:14} min={parsed.min()}  max={parsed.max()}  пропущено={int(empty.sum())}  некоректних={int(invalid.sum())}")
    for row in date_info[name]["invalid_rows"]:
        print("    некоректне:", row)

# %% [markdown]
# Два значення в `orders.created_at` не є ISO 8601. Одне (`04/09/2025 11:32`) має вигляд
# `DD/MM/YYYY HH:MM` — **припущення**: це 4 вересня 2025 року, що вкладається в період пакета
# (2025-09-01 … 2026-08-31), тоді як читання «місяць/день» дало б 9 квітня, поза періодом. Друге
# (`2026-19-45 25:61:00`) неможливе за календарем. У цій роботі нічого не виправляємо; правила
# приведення описано в Лабі 2.

# %% [markdown]
# ### 3.5 Числові діапазони, нулі, від'ємні значення, категорії та коди валют

# %%
numeric_cols = {
    "products": ["unit_price_uah"],
    "orders": ["subtotal_amount", "delivery_fee", "discount_amount", "total_amount"],
}
numeric_info = {}
rows = []
for name, cols in numeric_cols.items():
    for col in cols:
        s = df[name][col]
        info = {"min": float(s.min()), "max": float(s.max()), "zero": int((s == 0).sum()), "negative": int((s < 0).sum())}
        numeric_info[f"{name}.{col}"] = info
        rows.append({"column": f"{name}.{col}", **info})
display(pd.DataFrame(rows))

products = df["products"]
zero_price = products[products["unit_price_uah"] <= 0]
print("\nТовари з ціною <= 0:")
display(zero_price)

ALLOWED_CURRENCY = {"UAH", "USD", "EUR"}
currency_counts = df["orders"]["currency"].value_counts(dropna=False).to_dict()
odd_currency = df["orders"][~df["orders"]["currency"].isin(ALLOWED_CURRENCY)]
print("\nКоди валют:", currency_counts)
display(odd_currency)

# %% [markdown]
# **Що потребує уточнення, а що — ні.** Нулі в `delivery_fee` і `discount_amount` — звичайні значення
# (безкоштовна доставка, відсутність знижки); це не помилки. Нульова ціна **активного** товару
# потребує бізнес-уточнення: за навчальним контрактом Лаби 2 вона недопустима, а для неактивного
# товару нуль припустимий. Від'ємних сум немає. Код валюти `UA H` не належить до `UAH/USD/EUR` і
# не виправляється здогадкою.

# %% [markdown]
# Додаткова діагностика сум замовлення (значення **не змінюються**): перевіряємо, чи виконується
# `subtotal_amount + delivery_fee − discount_amount = total_amount`.

# %%
o = df["orders"]
diff = (o["subtotal_amount"] + o["delivery_fee"] - o["discount_amount"] - o["total_amount"]).round(2)
formula_bad = o.loc[diff.abs() > 0.01, ["order_id", "currency", "subtotal_amount", "delivery_fee", "discount_amount", "total_amount"]].copy()
formula_bad["difference"] = diff[diff.abs() > 0.01]
print("Замовлень, де формула не виконується:", len(formula_bad))
display(formula_bad)

# %% [markdown]
# ### 3.6 Перевірка зв'язків між файлами

# %%
c, m, p = df["customers"], df["merchants"], df["products"]
orphan_orders_customer = o[~o["customer_id"].isin(c["customer_id"])]
orphan_orders_merchant = o[~o["merchant_id"].isin(m["merchant_id"])]
orphan_products_merchant = p[~p["merchant_id"].isin(m["merchant_id"])]
for title, frame in [
    ("orders.customer_id без запису в customers", orphan_orders_customer),
    ("orders.merchant_id без запису в merchants", orphan_orders_merchant),
    ("products.merchant_id без запису в merchants", orphan_products_merchant),
]:
    print(f"\n{title}: {len(frame)}")
    display(frame)

# %% [markdown]
# ## 4. Підсумкова таблиця
# Тут **рахуються рядки файла** (разом із дублікатами); «унікальні ID» — кількість різних значень ключа.

# %%
summary_rows = []
for name, key in SOURCES.items():
    frame = df[name]
    summary_rows.append({
        "file": f"{name}.csv",
        "rows": len(frame),
        "columns": frame.shape[1],
        "unique_ids": int(frame[key].nunique()),
        "full_duplicates": int(frame.duplicated().sum()),
        "missing_cells": int(frame.isna().sum().sum()),
        "date_column": DATE_COL[name],
        "date_min": date_info[name]["min"],
        "date_max": date_info[name]["max"],
        "invalid_dates": date_info[name]["invalid"],
    })
summary = pd.DataFrame(summary_rows)
display(summary)

# %% [markdown]
# ## 5. Діагностичні графіки
# Це підрахунки **записів** (разом із повними дублікатами), а не перевірені бізнес-показники;
# суми різних валют не об'єднуються.

# %%
status_counts = o["order_status"].value_counts(dropna=False)
fig, ax = plt.subplots(figsize=(8, 4.5))
status_counts.plot(kind="bar", color="#2b5c8f", edgecolor="black", ax=ax)
ax.set_title("Кількість записів про замовлення за статусами (S08)")
ax.set_xlabel("Статус замовлення")
ax.set_ylabel("Кількість записів")
for i, value in enumerate(status_counts.values):
    ax.text(i, value, str(int(value)), ha="center", va="bottom", fontsize=8)
plt.xticks(rotation=30, ha="right")
fig.tight_layout()
fig.savefig(DOCS / "orders_by_status.png", dpi=200)
plt.show()

# %%
dates = iso_dates["orders"].dropna()
daily = dates.dt.date.value_counts().sort_index()
fig, ax = plt.subplots(figsize=(9, 4))
ax.plot(pd.to_datetime(daily.index), daily.values, color="#e8590c", marker="o", markersize=2, linewidth=0.8)
ax.set_title(f"Кількість записів про замовлення за датою створення (n = {len(dates)} з ISO-датами)")
ax.set_xlabel("Дата створення (UTC)")
ax.set_ylabel("Записів на добу")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(DOCS / "orders_by_date.png", dpi=200)
plt.show()
daily_stats = {
    "days": int(len(daily)), "min": int(daily.min()), "max": int(daily.max()),
    "median": float(daily.median()), "mean": round(float(daily.mean()), 1),
    "min_day": str(daily.idxmin()), "max_day": str(daily.idxmax()),
    "excluded_non_iso": int(date_info["orders"]["invalid"]),
}
# The same counts by local Kyiv date: day boundaries move, so min/max may differ from UTC.
daily_kyiv = dates.dt.tz_convert("Europe/Kyiv").dt.date.value_counts()
daily_stats.update({"kyiv_min": int(daily_kyiv.min()), "kyiv_max": int(daily_kyiv.max())})
monthly = daily.groupby(pd.to_datetime(daily.index).to_period("M")).mean()
daily_stats.update({
    "high_month": str(monthly.idxmax()), "high_month_mean": round(float(monthly.max()), 1),
    "low_month": str(monthly.idxmin()), "low_month_mean": round(float(monthly.min()), 1),
})
print(daily_stats)

# %% [markdown]
# **Висновок за графіками.** Серед записів переважає статус `delivered`; активних (`in_progress`)
# лише кілька. Добова кількість записів коливається в діапазоні, наведеному вище; медіана ближча до
# середнього, ніж до екстремумів. Окремі добові піки й провали **не пояснюються** даними пакета —
# це спостереження, а не підтверджений висновок. Два записи з не-ISO датою на графік дат не потрапили.

# %% [markdown]
# ## 6. Реєстр проблем якості
# Реєстр формується **з обчислених вище результатів** (жодного вручну вписаного ID): якщо певної
# проблеми в пакеті немає, рядка в реєстрі немає.

# %%
findings = []


def add(file, field, kind, problem, count, ids, impact, action, targets=None):
    findings.append({
        "file": file, "field": field, "kind": kind, "problem": problem, "count": int(count),
        "ids": list(ids), "impact": impact, "action": action,
        "targets": targets or [file.replace(".csv", "")],
    })


CONF, RISK = "підтверджене порушення", "потенційний ризик"

dups = {n: i for n, i in dup_info.items() if i["full_duplicate_rows"] > 0}
if dups:
    add("усі 4 CSV" if len(dups) == 4 else ", ".join(f"{n}.csv" for n in dups), "ключ рядка", CONF,
        "повні дублікати рядків", sum(i["full_duplicate_rows"] for i in dups.values()),
        [x for i in dups.values() for x in i["ids"]],
        "подвоєння записів; порушення PK у реляційній базі",
        "залишити одну точну копію, решту позначити як duplicate (Лаба 2)", targets=list(dups))

phone_missing = txt["customers"].loc[txt["customers"]["phone"] == "", "customer_id"].tolist()
if phone_missing:
    add("customers.csv", "phone", RISK, "порожнє поле телефону", len(phone_missing), phone_missing,
        "немає контакту для зв'язку; чи є телефон обов'язковим — припущення, джерело цього не каже",
        "прийняти як допустимий пропуск, не підставляти 0 чи сурогат")

for name in SOURCES:
    for _, rep_row in missing[name].iterrows():
        if rep_row["edge_whitespace"] > 0:
            t = txt[name]
            col = rep_row["column"]
            bad = t.loc[(t[col] != t[col].str.strip()) & (t[col].str.strip() != ""), SOURCES[name]].tolist()
            add(f"{name}.csv", col, CONF, "пробіли на початку/в кінці значення", len(bad), bad,
                "окремі написання однієї категорії (' Lviv ' ≠ 'Lviv') ламають групування та порівняння",
                "обрізати пробіли за явним правилом нормалізації, оригінал зберегти")

if len(zero_price):
    active_zero = zero_price[zero_price["is_active"]]
    add("products.csv", "unit_price_uah", RISK, "ціна ≤ 0 в активного товару" if len(active_zero) else "ціна ≤ 0 в неактивного товару",
        len(zero_price), zero_price["product_id"].tolist(),
        "потребує бізнес-уточнення; нуль не завжди помилка (для неактивного товару допустимий)",
        "за контрактом Лаби 2 активний товар із ціною ≤ 0 відхиляється")

if len(orphan_products_merchant):
    add("products.csv", "merchant_id", CONF, "посилання на відсутнього партнера", len(orphan_products_merchant),
        orphan_products_merchant["product_id"].tolist(), "порушення FK; INNER JOIN мовчки втратить товар",
        "карантин з причиною ORPHAN_MERCHANT_FK")
if len(orphan_orders_customer):
    add("orders.csv", "customer_id", CONF, "посилання на відсутнього клієнта", len(orphan_orders_customer),
        orphan_orders_customer["order_id"].tolist(), "порушення FK; замовлення випаде зі звітів при INNER JOIN",
        "карантин з причиною ORPHAN_CUSTOMER_FK")
if len(orphan_orders_merchant):
    add("orders.csv", "merchant_id", CONF, "посилання на відсутнього партнера", len(orphan_orders_merchant),
        orphan_orders_merchant["order_id"].tolist(), "порушення FK", "карантин з причиною ORPHAN_MERCHANT_FK")

if len(odd_currency):
    add("orders.csv", "currency", CONF, "код валюти поза UAH/USD/EUR: " + ", ".join(f"'{v}'" for v in odd_currency["currency"].unique()),
        len(odd_currency), odd_currency["order_id"].tolist(), "розбиття групування за валютою; суми різних валют не можна об'єднувати",
        "не виправляти здогадкою; відхиляти з причиною INVALID_CURRENCY")

bad_dates = date_info["orders"]["invalid_rows"]
if bad_dates:
    add("orders.csv", "created_at", CONF, "значення не є ISO 8601: " + "; ".join(f"'{r['value']}'" for r in bad_dates),
        len(bad_dates), [r["id"] for r in bad_dates],
        "не приводяться до timestamptz автоматично; формат DD/MM/YYYY — лише припущення",
        "DD/MM/YYYY HH:MM явно читати як UTC, неможливі дати відхиляти (Лаба 2)")

if len(formula_bad):
    add("orders.csv", "total_amount", RISK, "subtotal + delivery_fee − discount ≠ total_amount", len(formula_bad),
        formula_bad["order_id"].tolist(),
        "total_amount " + ", ".join(("більший" if x < 0 else "менший") + f" за обчислений на {abs(x):.2f}" for x in formula_bad["difference"]) + "; причина невідома",
        "лише діагностика, значення джерела не переписувати")

print(f"Записів у реєстрі: {len(findings)}")
display(pd.DataFrame([{k: (", ".join(v[:3]) + ("…" if len(v) > 3 else "") if k == "ids" else v) for k, v in f.items()} for f in findings]))

# %% [markdown]
# ## 7. Запис документації: реєстр проблем, словник даних, метрики

# %%
def short_ids(ids, limit=4):
    return ", ".join(f"`{i}`" for i in ids[:limit]) + (f" … (усього {len(ids)})" if len(ids) > limit else "")


lines = ["# Реєстр проблем якості даних (CityFlow S08)", "",
         f"Пакет: `{package_info['package_id']}` (student_id `{package_info['student_id']}`). "
         "Згенеровано блокнотом `notebooks/lab01/01_source_profiling.py`; числа обчислені, а не вписані вручну.",
         "", "| № | Файл / поле | Тип | Проблема | К-сть | Приклади ID | Можливий вплив | Запропонована дія |",
         "|---|---|---|---|---|---|---|---|"]
for i, f in enumerate(findings, 1):
    lines.append(f"| {i} | `{f['file']}` / `{f['field']}` | {f['kind']} | {f['problem']} | {f['count']} | "
                 f"{short_ids(f['ids'])} | {f['impact']} | {f['action']} |")
lines += ["", "*Підтверджене порушення* — значення суперечить правилу, яке видно з самих даних. "
          "*Потенційний ризик* — потребує бізнес-уточнення; будь-яке припущення позначено прямо."]
(DOCS / "data_quality_findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# %%
META = {
    "customers": ("Клієнти сервісу.", "один клієнт", {
        "customer_id": ("text", "ідентифікатор клієнта", "PK (кандидат)", "ні"),
        "full_name": ("text", "ім'я клієнта", "—", "ні"),
        "email": ("text", "електронна пошта; унікальність не підтверджена правилом (припущення)", "—", "ні"),
        "phone": ("text", "телефон; обов'язковість не підтверджена (припущення)", "—", "так"),
        "city": ("text", "місто", "—", "ні"),
        "service_zone_id": ("text", "код зони обслуговування (припущення: довідник service_zones з Лаби 2)", "FK? (припущення)", "ні"),
        "registered_at": ("timestamptz", "момент реєстрації", "—", "ні"),
        "customer_status": ("text", "статус клієнта", "—", "ні"),
    }),
    "merchants": ("Партнерські заклади.", "один заклад", {
        "merchant_id": ("text", "ідентифікатор закладу", "PK (кандидат)", "ні"),
        "merchant_name": ("text", "назва закладу", "—", "ні"),
        "merchant_type": ("text", "тип закладу", "—", "ні"),
        "city": ("text", "місто", "—", "ні"),
        "service_zone_id": ("text", "код зони обслуговування (припущення: довідник service_zones)", "FK? (припущення)", "ні"),
        "opened_at": ("timestamptz", "момент відкриття закладу", "—", "ні"),
        "merchant_status": ("text", "статус закладу", "—", "ні"),
    }),
    "products": ("Товари партнерів.", "один товар закладу", {
        "product_id": ("text", "ідентифікатор товару", "PK (кандидат)", "ні"),
        "merchant_id": ("text", "заклад-власник товару", "FK → merchants.merchant_id", "ні"),
        "product_name": ("text", "назва товару", "—", "ні"),
        "category": ("text", "категорія товару", "—", "ні"),
        "unit_price_uah": ("numeric(12,2)", "поточна ціна одиниці в UAH (не історична ціна замовлення)", "—", "ні"),
        "is_active": ("boolean", "чи товар активний", "—", "ні"),
        "updated_at": ("timestamptz", "момент останнього оновлення запису", "—", "ні"),
    }),
    "orders": ("Замовлення клієнтів.", "одне замовлення", {
        "order_id": ("text", "ідентифікатор замовлення", "PK (кандидат)", "ні"),
        "customer_id": ("text", "клієнт", "FK → customers.customer_id", "ні"),
        "merchant_id": ("text", "заклад", "FK → merchants.merchant_id", "ні"),
        "created_at": ("timestamptz", "момент створення замовлення", "—", "ні"),
        "order_status": ("text", "статус замовлення", "—", "ні"),
        "currency": ("text", "код валюти замовлення (очікувано UAH/USD/EUR — припущення)", "—", "ні"),
        "subtotal_amount": ("numeric(12,2)", "сума позицій до знижки та доставки (у валюті замовлення)", "—", "ні"),
        "delivery_fee": ("numeric(12,2)", "вартість доставки; 0 — звичайне значення", "—", "ні"),
        "discount_amount": ("numeric(12,2)", "знижка на замовлення; 0 — звичайне значення", "—", "ні"),
        "total_amount": ("numeric(12,2)", "підсумкова сума (не дорівнює чистому виторгу)", "—", "ні"),
    }),
}
problems = {}
for f in findings:
    for t in f["targets"]:
        is_key_finding = f["field"] == "ключ рядка"
        col = SOURCES[t] if is_key_finding else f["field"]
        ids = dup_info[t]["ids"] if is_key_finding else f["ids"]
        problems.setdefault((t, col), []).append(f"{f['problem']}: {short_ids(ids, 2)}")

out = ["# Словник даних CityFlow (пакет S08)", "",
       "Типи pandas і приклади взято з виконання блокнота. Логічні типи, зміст і обов'язковість, які "
       "не підтверджені джерелом, позначені як *припущення*.", ""]
for name, (about, grain, cols) in META.items():
    frame = df[name]
    out += [f"## `{name}.csv`", f"{about} **Один рядок =** {grain}. Рядків: {len(frame)}.", "",
            "| Колонка | Тип pandas | Логічний тип | Зміст | Роль ключа | NULL | Приклад | Виявлені проблеми |",
            "|---|---|---|---|---|---|---|---|"]
    for col, (logical, meaning, role, nullable) in cols.items():
        example = txt[name][col].replace("", pd.NA).dropna().iloc[0]
        issues = "; ".join(problems.get((name, col), [])) or "не виявлено"
        out.append(f"| `{col}` | `{frame[col].dtype}` | `{logical}` | {meaning} | {role} | {nullable} | `{example}` | {issues} |")
    out.append("")
(DOCS / "data_dictionary.md").write_text("\n".join(out), encoding="utf-8")

# %%
metrics = {
    "student_id": package_info["student_id"],
    "package_id": package_info["package_id"],
    "python": platform.python_version(),
    "pandas": pd.__version__,
    "archives": checksums.get("archives", {}),
    "summary": summary_rows,
    "statuses": {k: int(v) for k, v in status_counts.items()},
    "currencies": {k: int(v) for k, v in currency_counts.items()},
    "daily": daily_stats,
    "dups": dup_info,
    "missing_phone": phone_missing,
    "zero_price": zero_price.astype(str).to_dict("records"),
    "formula_bad": formula_bad.astype(str).to_dict("records"),
    "date_info": {n: {k: v for k, v in i.items()} for n, i in date_info.items()},
    "missing": [
        {"file": f"{n}.csv", **{k: (v if k == "column" else int(v)) for k, v in row.items() if k != "nan_pct"}}
        for n, rep in missing.items() for row in rep.to_dict("records")
        if row["nan"] or row["empty_field"] or row["whitespace_only"] or row["edge_whitespace"]
    ],
    "numeric": numeric_info,
    "orphans": {
        "orders.customer_id": orphan_orders_customer["order_id"].tolist(),
        "orders.merchant_id": orphan_orders_merchant["order_id"].tolist(),
        "products.merchant_id": orphan_products_merchant["product_id"].tolist(),
    },
    "findings": findings,
}
(DOCS / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
print("Записано docs/lab01/: metrics.json, data_quality_findings.md, data_dictionary.md, orders_by_*.png")
