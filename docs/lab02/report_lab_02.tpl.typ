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
    Студент %%COURSE_YEAR%%\
    групи %%GROUP%%\
    %%STUDENT%%\
    \
    Перевірив:\
    %%TEACHER%%
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

%%CONFIG%%

= Джерела та контрольні суми
%%SOURCES%%

= Реляційна модель і рівень деталізації
Три простори імен: `stg` — оригінальні значення як `TEXT` з `batch_id`, `source_file`, `source_row_number`, `loaded_at`; `core` — перевірена реляційна копія (не DWH); `audit` — журнал запусків, облік вхідних пакетів, рішення по кожному рядку та звірка. Business key = точний ID із джерела; нових випадкових ID немає.

#align(center)[
  #figure(
    image("erd_lab02.png", width: 80%),
    caption: [ER-діаграма core: сутності, первинні та зовнішні ключі]
  )
]

%%MODEL_TABLE%%

= Правила приймання
%%RULES%%

= Облік п'яти файлів
%%ACCOUNTING%%

= Контрольні SQL-перевірки
%%CHECKS%%

= Повторний запуск
%%IDEMPOTENCY%%

= Rollback і журнал збоїв
%%ROLLBACK%%

= Висновки
%%CONCLUSIONS%%

= Використання ШІ
%%AI_TEXT%%

= Відповіді на контрольні запитання
%%QUESTIONS%%
