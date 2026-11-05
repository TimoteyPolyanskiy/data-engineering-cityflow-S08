// Шаблон звіту Лаби 2. Не редагуйте report_lab_02.typ вручну: його створює scripts/lab02/generate_report.py.
#set page(
  paper: "a4",
  margin: (top: 2cm, bottom: 2cm, left: 2.5cm, right: 1.5cm),
  header: none,
  footer: context {
    if counter(page).get().first() > 1 [
      #align(right)[
        #text(size: 9pt, fill: rgb("#334155"))[#counter(page).display("1")]
      ]
    ]
  }
)

#set text(
  font: "Liberation Serif",
  size: 11pt,
  lang: "uk"
)
#set par(justify: true, leading: 0.7em)

#align(center)[
  #text(size: 12pt, weight: "bold")[
    МІНІСТЕРСТВО ОСВІТИ І НАУКИ УКРАЇНИ\
    ЛЬВІВСЬКИЙ НАЦІОНАЛЬНИЙ УНІВЕРСИТЕТ ІМЕНІ ІВАНА ФРАНКА\
  ]
  #v(1mm)
  #text(size: 11pt)[Факультет електроніки та комп'ютерних технологій]
]

#v(4cm)

#align(center)[
  #text(size: 16pt, weight: "bold")[ЗВІТ]\
  #v(2.5mm)
  #text(size: 13pt, weight: "bold")[З ЛАБОРАТОРНОЇ РОБОТИ №2]\
  #v(2.5mm)
  #text(size: 11pt)[з дисципліни "Методи та технології інженерії даних"]\
  #v(1.5mm)
  #text(size: 11pt, weight: "medium")[на тему: "PostgreSQL у конвеєрі даних: завантаження, цілісність і транзакції"]
]

#v(3.5cm)

#align(right)[
  #text(size: 11pt)[
    Виконав:\
    Студент 3 курсу\
    групи ФЕП-34\
    Полянський Тимотей\
    \
    Перевірив:\
    ас. Фостяк Маркіян Романович
  ]
]

#v(1fr)

#align(center)[
  #text(size: 11pt)[Львів 2026]
]

#pagebreak()
#counter(page).update(1)

#set text(
  font: "Liberation Sans",
  size: 9.5pt,
  lang: "uk"
)
#set par(justify: true, leading: 0.6em)
#set heading(numbering: "1.1.")
#show heading: it => block(above: 1.0em, below: 0.6em)[#it]
#set list(spacing: 0.85em)

= Мета роботи, версії та посилання
*Мета роботи:* відтворювано перенести CSV у PostgreSQL: розділити приймання (`stg`) і публікацію (`core`), контролювати ключі та зв'язки, вести облік кожного запису й спроб запуску (`audit`), публікувати результат однією транзакцією та довести повторний запуск і відкат.

- Студент: Полянський Тимотей, група ФЕП-34\; #raw("student_id: S08"), batch #raw("S08-V1"), останній успішний запуск #raw("run_id = 30").
- Python #raw("3.14.7"), драйвер #raw("psycopg 3.3.6") (libpq #raw("180006")), PostgreSQL сервер #raw("16.15"), клієнт #raw("psql (PostgreSQL) 16.15") (Docker #raw("postgres:16-alpine")), тести #raw("pytest").
- Пароль і параметри підключення — у #raw(".env") поза Git (#raw(".env.example") без секретів)\; повні дані й дампи в Git не потрапляють.
- Гілка #raw("lab/02-postgresql-load"), тег #raw("lab-02-v1").
- Репозиторій: #link("https://github.com/TimoteyPolyanskiy/data-engineering-cityflow-S08")[https://github.com/TimoteyPolyanskiy/data-engineering-cityflow-S08]
- Pull Request: #link("https://github.com/TimoteyPolyanskiy/data-engineering-cityflow-S08/pull/2")[https://github.com/TimoteyPolyanskiy/data-engineering-cityflow-S08/pull/2]

= Джерела та контрольні суми
Пакети студента #raw("S08") зберігаються в різних каталогах і не змішуються з іншими SXX\; raw-файли не змінювались. #raw("payments"), #raw("refunds"), #raw("couriers"), #raw("deliveries"), #raw("service_zones") у core не завантажуються.

- #raw("cityflow_S08_base_v1.zip") — SHA-256 #raw("8a8eb3777248c41e1ffc424ca055ecde9ece81efe5a5e93e4d464bede4b661ac") (збігається з наданою викладачем)
- #raw("cityflow_S08_lab02_relational_v1.zip") — SHA-256 #raw("a6f77a3ad9dcffb14a45440406be571b74051f14ed11d2372e62cdfac046a762") (суму викладача не надано\; записано обчислену)

#block(breakable: false)[
#text(size: 7.5pt)[
#table(
  columns: (1.2fr, 1.6fr, 2.4fr),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: (x: 4pt, y: 4pt),
  align: (col, row) => (left, left, left).at(col) + horizon,
  [*Файл*], [*Каталог*], [*SHA-256 (початок, за PACKAGE\_INFO.json)*],
  [#raw("customers.csv")], [#raw("data/raw/base_v1")], [#raw("51273484b70350ac299e5ede…")],
  [#raw("merchants.csv")], [#raw("data/raw/base_v1")], [#raw("2d3c403f6b59446645c83dd0…")],
  [#raw("products.csv")], [#raw("data/raw/base_v1")], [#raw("7ea189b9c7beb7e89b404f53…")],
  [#raw("orders.csv")], [#raw("data/raw/base_v1")], [#raw("42547e7641607e97b4e24f14…")],
  [#raw("order_items.csv")], [#raw("data/raw/lab02_relational")], [#raw("abef5cefc583391e7ca10d4d…")]
)
]
]

= Реляційна модель і рівень деталізації
Три простори імен: `stg` — оригінальні значення як `TEXT` з `batch_id`, `source_file`, `source_row_number`, `loaded_at`; `core` — перевірена реляційна копія (не DWH); `audit` — журнал запусків, облік вхідних пакетів, рішення по кожному рядку та звірка. Business key = точний ID із джерела; нових випадкових ID немає.

#align(center)[
  #figure(
    image("erd_lab02.png", width: 80%),
    caption: [ER-діаграма core: сутності, первинні та зовнішні ключі]
  )
]

#block(breakable: false)[
#text(size: 8pt)[
#table(
  columns: (1fr, 1fr, 1.7fr, 2.3fr),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: (x: 6pt, y: 6pt),
  align: (col, row) => (left, left, left, left).at(col) + horizon,
  [*Таблиця core*], [*PK*], [*Grain*], [*FK, NOT NULL та CHECK*],
  [#raw("customers")], [#raw("customer_id")], [один клієнт], [#raw("full_name"), #raw("city"), #raw("registered_at") NOT NULL],
  [#raw("merchants")], [#raw("merchant_id")], [один заклад-партнер], [#raw("merchant_name"), #raw("city"), #raw("opened_at") NOT NULL],
  [#raw("products")], [#raw("product_id")], [один товар закладу], [FK #raw("merchant_id")\; #raw("unit_price_uah ≥ 0")\; активний товар має ціну \> 0 (#raw("NOT is_active OR unit_price_uah > 0"))],
  [#raw("orders")], [#raw("order_id")], [одне замовлення], [FK #raw("customer_id"), #raw("merchant_id")\; #raw("currency IN (UAH, USD, EUR)")\; усі суми ≥ 0],
  [#raw("order_items")], [#raw("order_item_id")], [одна товарна позиція], [FK #raw("order_id"), #raw("product_id")\; #raw("quantity > 0")\; #raw("unit_price"), #raw("line_discount"), #raw("line_total") ≥ 0\; валюта з того ж переліку]
)
]
]

= Правила приймання
- Типи: ID — #raw("text"), кількість — #raw("integer"), суми — #raw("numeric(12,2)"), час — #raw("timestamptz"). Порожній ключ і непридатна дата відхиляються\; порожній телефон помилкою не є, невідоме число нулем не замінюється.
- Дати: ISO 8601 із #raw("Z") або зсувом (→ UTC)\; #raw("DD/MM/YYYY HH:MM") явно читається як UTC (день, потім місяць)\; ISO без зсуву й неможливі дати відхиляються. Частки секунди довші за мікросекунди відкидаються в core, оригінал лишається в staging.
- Валюти: #raw("UAH"), #raw("USD"), #raw("EUR") (дозволена нормалізація — лише обрізання пробілів по краях і верхній регістр)\; код #raw("UA H") не виправляється й відхиляється як #raw("INVALID_CURRENCY").
- Активний товар із ціною ≤ 0 відхиляється (#raw("INVALID_PRICE"))\; для неактивного нуль допустимий. #raw("quantity > 0"), суми ≥ 0.
- Повтори: точна бізнес-копія → перша лишається, решта #raw("duplicate")\; той самий ключ із різними значеннями → уся група #raw("rejected / KEY_CONFLICT") (вибору «останнього» рядка немає).
- Зв'язки: дочірній запис із відсутнім або відхиленим батьком не потрапляє в core (#raw("ORPHAN_*_FK"), #raw("PARENT_REJECTED_ORDER"), #raw("PARENT_REJECTED_PRODUCT"))\; INNER JOIN мовчки нічого не губить. Повна політика — #raw("docs/lab02/load_policy.md").

= Облік п'яти файлів
#block(breakable: false)[
#text(size: 8pt)[
#table(
  columns: (1.4fr, 0.8fr, 0.9fr, 0.9fr, 0.9fr, 1.9fr),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: (x: 6pt, y: 6pt),
  align: (col, row) => (left, center, center, center, center, center).at(col) + horizon,
  [*Файл*], [*Вхід (input)*], [*Прийнято*], [*Відхилено*], [*Дублікати*], [*input = accepted + rejected + duplicate*],
  [#raw("customers.csv")], [801], [800], [0], [1], [так],
  [#raw("merchants.csv")], [43], [42], [0], [1], [так],
  [#raw("products.csv")], [534], [531], [2], [1], [так],
  [#raw("orders.csv")], [6 001], [5 996], [4], [1], [так],
  [#raw("order_items.csv")], [14 062], [14 027], [35], [0], [так]
)
]
]

Кількість і набір ключів у core звіряються саме з #raw("accepted"). Кожен рядок має один фінальний статус у #raw("audit.row_decisions")\; відхилені: #raw("S08-O0002449") (INVALID\_CURRENCY), #raw("S08-O0003385") (INVALID\_DATE), #raw("S08-O0004825") (ORPHAN\_CUSTOMER\_FK), #raw("S08-O0005136") (ORPHAN\_MERCHANT\_FK), #raw("S08-P000074") (INVALID\_PRICE), #raw("S08-P000331") (ORPHAN\_MERCHANT\_FK). Нормалізація пробілів (рядок лишається #raw("accepted")): #raw("customers.csv"): WHITESPACE\_TRIMMED — 1, #raw("products.csv"): WHITESPACE\_TRIMMED — 1. Каскад для #raw("order_items") (35 позицій): #raw("PARENT_REJECTED_ORDER") — 8 (#raw("S08-O0002449") INVALID\_CURRENCY — 2, #raw("S08-O0003385") INVALID\_DATE — 1, #raw("S08-O0004825") ORPHAN\_CUSTOMER\_FK — 1, #raw("S08-O0005136") ORPHAN\_MERCHANT\_FK — 4)\; #raw("PARENT_REJECTED_PRODUCT") — 27 (#raw("S08-P000074") INVALID\_PRICE — 23, #raw("S08-P000331") ORPHAN\_MERCHANT\_FK — 4).

#block(breakable: false)[
#text(size: 8pt)[
#table(
  columns: (1.5fr, 1fr, 2.2fr, 0.8fr),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: (x: 3.5pt, y: 3.5pt),
  align: (col, row) => (left, left, left, center).at(col) + horizon,
  [*Файл*], [*Статус*], [*Причина*], [*К-сть*],
  [#raw("customers.csv")], [duplicate], [#raw("FULL_DUPLICATE")], [1],
  [#raw("merchants.csv")], [duplicate], [#raw("FULL_DUPLICATE")], [1],
  [#raw("order_items.csv")], [rejected], [#raw("PARENT_REJECTED_ORDER")], [8],
  [#raw("order_items.csv")], [rejected], [#raw("PARENT_REJECTED_PRODUCT")], [27],
  [#raw("orders.csv")], [duplicate], [#raw("FULL_DUPLICATE")], [1],
  [#raw("orders.csv")], [rejected], [#raw("INVALID_CURRENCY")], [1],
  [#raw("orders.csv")], [rejected], [#raw("INVALID_DATE")], [1],
  [#raw("orders.csv")], [rejected], [#raw("ORPHAN_CUSTOMER_FK")], [1],
  [#raw("orders.csv")], [rejected], [#raw("ORPHAN_MERCHANT_FK")], [1],
  [#raw("products.csv")], [duplicate], [#raw("FULL_DUPLICATE")], [1],
  [#raw("products.csv")], [rejected], [#raw("INVALID_PRICE")], [1],
  [#raw("products.csv")], [rejected], [#raw("ORPHAN_MERCHANT_FK")], [1]
)
]
]

= Контрольні SQL-перевірки
#strong[1\. Дублікати PK:] #raw("customers") — 0, #raw("merchants") — 0, #raw("products") — 0, #raw("orders") — 0, #raw("order_items") — 0 (очікується 0).

#strong[2\. Відсутні FK:] orders → customers: 0, orders → merchants: 0, products → merchants: 0, order\_items → orders: 0, order\_items → products: 0 (очікується 0).

#strong[3\. Прийнятий набір у staging ↔ core: кількість, набір ключів і суми окремо за валютою] (валюти не об'єднуються). Набір ключів: кількість ключів, які є лише з одного боку (accepted без core або core без accepted), — #raw("customers.csv") — 0, #raw("merchants.csv") — 0, #raw("products.csv") — 0, #raw("orders.csv") — 0, #raw("order_items.csv") — 0 (очікується 0).

#block(breakable: false)[
#text(size: 7.5pt)[
#table(
  columns: (1.2fr, 0.8fr, 1.5fr, 2.6fr, 0.6fr),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: (x: 3.5pt, y: 3.5pt),
  align: (col, row) => (left, center, center, center, center).at(col) + horizon,
  [*Таблиця*], [*Валюта*], [*Рядків (stg / core)*], [*Сума (#raw("total_amount") / #raw("line_total")) (stg / core)*], [*Збіг*],
  [#raw("orders")], [#raw("EUR")], [32 / 32], [354\.17 / 354.17], [так],
  [#raw("orders")], [#raw("UAH")], [5 924 / 5 924], [3 619 371.87 / 3 619 371.87], [так],
  [#raw("orders")], [#raw("USD")], [40 / 40], [575\.10 / 575.10], [так],
  [#raw("order_items")], [#raw("EUR")], [71 / 71], [305\.42 / 305.42], [так],
  [#raw("order_items")], [#raw("UAH")], [13 869 / 13 869], [3 179 134.01 / 3 179 134.01], [так],
  [#raw("order_items")], [#raw("USD")], [87 / 87], [511\.46 / 511.46], [так]
)
]
]

#strong[4\. Чому ]#raw("SUM(orders.total_amount)") після JOIN із #raw("order_items") завищена.#strong[ ]#raw("orders") має рівень «одне замовлення», #raw("order_items") — «одна позиція»\; JOIN повторює #raw("total_amount") для кожної позиції. Правильний запит спершу зводить позиції до рівня замовлення (CTE #raw("items_agg")) і лише потім з'єднує 1:1\; #raw("SUM(DISTINCT total_amount)") не підходить, бо відкидає різні замовлення з однаковою сумою.

#block(breakable: false)[
#text(size: 7.5pt)[
#table(
  columns: (0.8fr, 0.9fr, 0.9fr, 1.4fr, 1.4fr, 1.4fr, 1.4fr),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: (x: 3.5pt, y: 3.5pt),
  align: (col, row) => (center, center, center, center, center, center, center).at(col) + horizon,
  [*Валюта*], [*Рядків orders*], [*Рядків після JOIN*], [*Істинна #raw("SUM(total)")*], [*#raw("SUM") після JOIN*], [*#raw("SUM(total)") (CTE)*], [*#raw("SUM(line_total)") (CTE)*],
  [#raw("EUR")], [32], [71], [354\.17], [956\.78], [354\.17], [305\.42],
  [#raw("UAH")], [5 924], [13 869], [3 619 371.87], [10 273 021.62], [3 618 934.66], [3 179 134.01],
  [#raw("USD")], [40], [87], [575\.10], [1 611.21], [575\.10], [511\.46]
)
]
]

#raw("WITH items_agg AS (SELECT order_id, sum(line_total) AS items_sum FROM core.order_items GROUP BY order_id)\nSELECT o.currency, count(*) AS orders_with_items, sum(o.total_amount) AS orders_total, sum(a.items_sum) AS items_total\nFROM core.orders o JOIN items_agg a ON a.order_id = o.order_id GROUP BY o.currency;", block: true, lang: "sql")

#strong[Чому ]#raw("SUM(total_amount)") не дорівнює #raw("SUM(line_total)")#strong[ (для UAH 3 618 934.66 проти 3 179 134.01, лише замовлення з позиціями). Це різні величини: ]#raw("total_amount = subtotal + delivery_fee − discount"), а #raw("line_total") — позиція після своєї знижки, без доставки. Складові окремо за валютою:

#block(breakable: false)[
#text(size: 7.5pt)[
#table(
  columns: (0.7fr, 0.8fr, 1.3fr, 1.2fr, 1.1fr, 1.3fr, 1.3fr, 1.1fr),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: (x: 3.5pt, y: 3.5pt),
  align: (col, row) => (center, center, center, center, center, center, center, center).at(col) + horizon,
  [*Валюта*], [*Замовлень*], [*#raw("Σ subtotal")*], [*#raw("Σ delivery_fee")*], [*#raw("Σ discount")*], [*#raw("Σ total")*], [*#raw("Σ line_total")*], [*#raw("Σ line_discount")*],
  [#raw("EUR")], [32], [319\.73], [48\.74], [14\.32], [354\.17], [305\.42], [14\.29],
  [#raw("UAH")], [5 922], [3 284 693.81], [437 154.29], [103 050.61], [3 618 934.66], [3 179 134.01], [102 919.39],
  [#raw("USD")], [40], [522\.46], [63\.65], [11\.01], [575\.10], [511\.46], [11\.00]
)
]
]

#strong[Діагностика (значення джерела не змінювались).] Формула #raw("subtotal + delivery_fee − discount = total") не виконується в 1 замовленні: #raw("S08-O0001712") (UAH, різниця -137.17). Рівність #raw("subtotal_amount = Σ line_total") не виконується в 1813 із 5994 замовлень, бо #raw("line_total") уже без знижки позиції\; натомість #raw("subtotal_amount = Σ(line_total + line_discount)") порушено лише в 25, а #raw("discount_amount = Σ line_discount") — у 8 замовленнях (можливі незалежні округлення\; причину дані не пояснюють). #raw("total_amount") не вважається чистим виторгом. Замовлень у core без жодної прийнятої позиції: 2 (#raw("S08-O0000842"): позиції відхилено як PARENT\_REJECTED\_PRODUCT через товар S08-P000331\; #raw("S08-O0001142"): позиції відхилено як PARENT\_REJECTED\_PRODUCT через товар S08-P000074)\; через це «Рядків orders» і кількість замовлень у CTE-запиті відрізняються.

= Повторний запуск
Той самий пакет #raw("S08-V1") оброблено двічі: #raw("run_id = 22") і #raw("run_id = 23"). Бізнес-стан не змінився (так), рішення по рядках ідентичні (так)\; у журналі з'явився новий #raw("run"). Політика — повний snapshot: у транзакції очищується лише список core-таблиць (без #raw("CASCADE"), #raw("audit") не зачіпається) і вставляється прийнятий набір. Той самий #raw("batch_id") із #strong[іншим] вмістом файла відхиляється (SHA-256 у #raw("audit.batch_sources")).

#block(breakable: false)[
#text(size: 7.5pt)[
#table(
  columns: (2fr, 1fr, 1fr, 1.2fr, 1.2fr, 0.5fr),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: (x: 3.5pt, y: 3.5pt),
  align: (col, row) => (left, center, center, center, center, center).at(col) + horizon,
  [*Показник*], [*Після run 1*], [*Після run 2*], [*Відбиток ключів 1*], [*Відбиток ключів 2*], [*Збіг*],
  [#raw("core.customers")], [800], [800], [#raw("da4d55524d")], [#raw("da4d55524d")], [так],
  [#raw("core.merchants")], [42], [42], [#raw("7cc35a5d84")], [#raw("7cc35a5d84")], [так],
  [#raw("core.products")], [531], [531], [#raw("6b620b826d")], [#raw("6b620b826d")], [так],
  [#raw("core.orders")], [5 996], [5 996], [#raw("6390824fa5")], [#raw("6390824fa5")], [так],
  [#raw("core.order_items")], [14 027], [14 027], [#raw("dd5d65c8ed")], [#raw("dd5d65c8ed")], [так],
  [сума #raw("orders"), #raw("EUR")], [354\.17], [354\.17], [—], [—], [так],
  [сума #raw("orders"), #raw("UAH")], [3 619 371.87], [3 619 371.87], [—], [—], [так],
  [сума #raw("orders"), #raw("USD")], [575\.10], [575\.10], [—], [—], [так]
)
]
]

= Rollback і журнал збоїв
Збій імітується #strong[після] початку зміни core: у тій самій транзакції, де вже виконано #raw("TRUNCATE") і вставку нових рядків, додається дочірній рядок з #raw("quantity = -1"), що порушує #raw("CHECK (quantity > 0)"). Транзакція відкочується повністю\; запис #raw("FAILED") (#raw("run_id = 24")) робиться окремою транзакцією й зберігається разом із помилкою: #raw("CheckViolation: new row for relation \"order_items\" violates check constraint \"order_items_quantity_check\""). Потім виправлений запуск успішний (#raw("run_id = 25")).

#block(breakable: false)[
#text(size: 8pt)[
#table(
  columns: (2fr, 1fr, 1fr, 0.6fr),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: (x: 3.5pt, y: 3.5pt),
  align: (col, row) => (left, center, center, center).at(col) + horizon,
  [*Таблиця*], [*До збою*], [*Після rollback*], [*Збіг*],
  [#raw("core.customers")], [800], [800], [так],
  [#raw("core.merchants")], [42], [42], [так],
  [#raw("core.products")], [531], [531], [так],
  [#raw("core.orders")], [5 996], [5 996], [так],
  [#raw("core.order_items")], [14 027], [14 027], [так]
)
]
]

Негативні тести: збій має зупинити роботу #strong[до] публікації, core залишається незмінним, а #raw("FAILED") лишається в журналі.

#block(breakable: false)[
#text(size: 7.5pt)[
#table(
  columns: (2fr, 0.6fr, 0.8fr, 3fr, 0.9fr),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: (x: 3.5pt, y: 3.5pt),
  align: (col, row) => (left, center, center, left, center).at(col) + horizon,
  [*Сценарій*], [*run\_id*], [*Статус*], [*Помилка*], [*core без змін*],
  [неправильний заголовок CSV], [26], [#raw("FAILED")], [#raw("ValueError: Порушення схеми CSV у customers.csv. Очікувалось: ['customer_id', 'full_name', 'email', 'phone', '…")], [так],
  [відсутній обов'язковий файл], [27], [#raw("FAILED")], [#raw("FileNotFoundError: Обов'язковий файл …/orders.csv відсутній.")], [так],
  [змінений вміст під тим самим #raw("batch_id")], [29], [#raw("FAILED")], [#raw("ValueError: Вміст orders.csv змінився під тим самим batch_id=S08-V1: було 42547e764160…, стало ffd3a3800e9f….…")], [так]
)
]
]

= Висновки
+ Усі 21 441 вхідних записів мають рівно один фінальний статус: 21 396 прийнято, 41 відхилено, 4 повторів\; нічого не видалено зі staging.
+ Core публікується однією транзакцією\; усі 44 звірок (кількості, набори ключів, суми окремо за валютою, відсутні FK) пройдено.
+ Повторний запуск не змінює бізнес-стан, а збої (у журналі #raw("FAILED"): 12) не залишають часткового результату.
+ Суми по JOIN #raw("orders") × #raw("order_items") без попередньої агрегації завищуються\; контрольні суми рахуються окремо за валютою.
+ Обмеження: snapshot-модель (без UPSERT і SCD)\; #raw("payments"), #raw("refunds"), #raw("couriers"), #raw("deliveries"), #raw("service_zones") не завантажуються\; перевірка швидкості не виконувалась.

= Використання ШІ
Інструменти: Gemini і Claude. Gemini використано для чернеток DDL, завантажувача на #raw("psycopg") і тестів\; Claude — для звірки коду й звіту з вимогами методички та підготовки відтворюваного скрипта перебудови. Поставлені завдання: підготувати чернетку завантаження через #raw("COPY") у staging і таблиці #raw("audit.row_decisions")\; порівняти код конвеєра і звіт із методичкою та перелічити розбіжності. Внесок автора: постановка завдань, вибір між запропонованими варіантами та перевірка результатів запусків. Прийняті в роботі правила: #raw("UA H") відхиляється як #raw("INVALID_CURRENCY"), #raw("DD/MM/YYYY") читається явно як UTC, ціна перевіряється разом з #raw("is_active"), суми звіряються окремо за валютою. Перевірка на локальному PostgreSQL 16: юніт-тести правил, регресійний тест на пакеті S08, звірка ключів accepted ↔ core в обидва боки, rollback-тест\; відхилені ID збігаються з реєстром проблем Лаби 1.

= Відповіді на контрольні запитання
*1\. Чим бізнес-ключ відрізняється від технічного ідентифікатора надходження?*\
Бізнес-ключ (#raw("customer_id"), #raw("order_id") …) ідентифікує сутність у джерелі й переходить у core. #raw("batch_id"), #raw("source_file"), #raw("source_row_number"), #raw("loaded_at") описують конкретне надходження рядка\; один і той самий бізнес-ключ може надійти кілька разів, тож технічний ідентифікатор ключем сутності не є.

*2\. Чому staging може містити повтори й #raw("text"), хоча core має суворі типи та ключі?*\
Staging — доказ того, що надійшло: прийняти треба #strong[всі] записи, зокрема непридатні (неможлива дата, #raw("UA H")), інакше #raw("COPY") перервався б, а втрати стали б непомітними. Типи, ключі й #raw("CHECK") захищають лише перевірену копію в core.

*3\. Чим відрізняються точний дублікат, конфлікт ключа й оновлення?*\
Точний дублікат — усі бізнес-значення збігаються: лишається перша копія, решта #raw("duplicate"). Конфлікт — той самий ключ із різними значеннями без достовірної версії: уся група #raw("rejected / KEY_CONFLICT"). Оновлення — нова версія тієї самої сутності з надійною ознакою версії\; у цьому пакеті такої ознаки немає, тому оновлення не припускається.

*4\. Чому #raw("CHECK") не завжди замінює #raw("NOT NULL")? Які правила не покриває FK?*\
Для #raw("NULL") вираз #raw("CHECK (x > 0)") дає #raw("unknown"), і рядок проходить, тому потрібні обидва обмеження. FK перевіряє лише існування батька\; він не перевіряє валюту, суми, активність товару чи відповідність валюти позиції валюті замовлення.

*5\. Що станеться, якщо батьківський запис відхилено, а дочірній сам по собі валідний?*\
Дочірній запис у core не потрапляє: він отримує #raw("rejected") з #raw("PARENT_REJECTED_ORDER") або #raw("PARENT_REJECTED_PRODUCT") і лишається в staging та #raw("audit.row_decisions"). Мовчазний INNER JOIN втратив би його без сліду.

*6\. Що саме охоплює ваша транзакція? Як доведено rollback після часткового виконання?*\
Запис рішень у #raw("audit.row_decisions"), очищення й заповнення п'яти core-таблиць, звірку та #raw("SUCCESS"). Rollback доведено тестом: після #raw("TRUNCATE") і вставки нових рядків додається позиція з #raw("quantity = -1")\; кількості й відбитки ключів усіх таблиць після відкату збігаються з початковими (таблиця вище).

*7\. Чому failed-run потрібно записувати поза транзакцією, яку відкотили?*\
#raw("ROLLBACK") скасував би й запис про збій. Тому #raw("FAILED") пишеться окремим з'єднанням і транзакцією після відкату, а #raw("RUNNING") реєструється ще до публікації.

*8\. Чому збіг кількості рядків або однієї загальної суми недостатній?*\
Помилки можуть компенсувати одна одну (зайвий і відсутній рядок), а суми різних валют не можна складати. Тому звіряється набір ключів в обидва боки, суми окремо за валютою й відсутні FK.

*9\. Чому повторний run не змінює бізнес-стан? Чим це відрізняється від нового snapshot?*\
Той самий пакет (SHA-256 файлів збігається) і детермінований повний snapshot дають однаковий core\; лише з'являється новий #raw("run_id"). Новий snapshot — це інший пакет або вміст\; змінений вміст під тим самим #raw("batch_id") конвеєр відхиляє.

*10\. Як ви перевірили AI-assisted рішення і яку помилку воно могло приховати?*\
Правила перевірено юніт-тестами на синтетичних fixtures, регресійним тестом на пакеті S08, звіркою відхилених ID з реєстром проблем Лаби 1 (pandas) і звіркою ключів accepted ↔ core в обидва боки, а збої — тестами rollback. Приховати могли б: нормалізацію #raw("UA H") → #raw("UAH"), читання #raw("04/09/2025") як 9 квітня та змішування валют в одній сумі — усі три випадки виявлено й виправлено.
