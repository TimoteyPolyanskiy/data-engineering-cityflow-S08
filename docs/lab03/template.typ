// template.typ — FIXED layout. Edit only when the layout standard itself changes.
// Usage in report.typ:
//   #import "template.typ": *
//   #show: report.with(lab-number: "1", discipline: "...", ...)

#let slate = rgb("#334155")
#let head-fill = rgb("#f1f5f9")
#let line-color = rgb("#cbd5e1")

// ---------- helpers (used inside report bodies) ----------

// Figure with a controlled width. Default 80%; use 55-65% when space is tight,
// 78-85% when a page is too empty.
#let fig(path, caption, width: 80%) = figure(
  image(path, width: width),
  caption: caption,
)

// Table following the standard: header centered, columns listed in `centered`
// are centered (ids, numbers, statuses), all other columns are left-aligned.
// The first row passed in `..cells` is the header row.
// keep: true (default) = the whole table moves to the next page if it does not
// fit, instead of being split. A table taller than one page cannot be kept
// whole: use keep: false for it.
#let rtable(
  columns: (),
  centered: (),
  inset: (x: 5pt, y: 5pt),
  keep: true,
  ..cells,
) = {
  show table.cell.where(y: 0): strong
  let t = table(
    columns: columns,
    fill: (_, row) => if row == 0 { head-fill },
    stroke: 0.5pt + line-color,
    inset: inset,
    align: (col, row) => if row == 0 or col in centered {
      center + horizon
    } else {
      left + horizon
    },
    ..cells,
  )
  if keep { block(breakable: false, t) } else { t }
}

// Dense mode: smaller text / tighter leading for crowded pages.
#let dense(body, size: 9pt, leading: 0.54em) = {
  set text(size: size)
  set par(leading: leading)
  body
}

// ---------- main template ----------

#let report(
  lab-number: "",
  discipline: "",
  topic: "",
  course: "",
  group: "",
  student: "",
  reviewer: "",
  year: 2026,
  pages: none, // expected TOTAL page count incl. title page; none = no check
  body,
) = {
  set document(title: topic, author: student)
  set text(lang: "uk")

  // ----- title page -----
  set page(
    paper: "a4",
    margin: (top: 2cm, bottom: 2cm, left: 2.5cm, right: 1.5cm),
    header: none,
    footer: none,
  )
  set text(font: ("Times New Roman", "Liberation Serif"), size: 11pt)
  set par(justify: false, leading: 0.7em)

  align(center)[
    #text(size: 12pt, weight: "bold")[
      МІНІСТЕРСТВО ОСВІТИ І НАУКИ УКРАЇНИ \
      ЛЬВІВСЬКИЙ НАЦІОНАЛЬНИЙ УНІВЕРСИТЕТ ІМЕНІ ІВАНА ФРАНКА
    ]
    #v(1mm)
    #text(size: 11pt)[Факультет електроніки та комп'ютерних технологій]
  ]

  v(4.5cm)

  align(center)[
    #text(size: 16pt, weight: "bold")[ЗВІТ]
    #v(2.5mm)
    #text(size: 13pt, weight: "bold")[З ЛАБОРАТОРНОЇ РОБОТИ №#lab-number]
    #v(2.5mm)
    #text(size: 11pt)[з дисципліни "#discipline"]
    #v(1.5mm)
    #text(size: 11pt, weight: "medium")[на тему: "#topic"]
  ]

  v(3.5cm)

  align(right)[
    #text(size: 11pt)[
      Виконав: \
      Студент #course курсу \
      групи #group \
      #student \
      \
      Перевірив: \
      #reviewer
    ]
  ]

  v(1fr)
  align(center, text(size: 11pt)[Львів #year])

  // ----- main part (set page below starts a new page automatically) -----
  // The title page counts as page 1 but shows no number; the first content
  // page is numbered 2.
  set page(
    footer: context align(
      right,
      text(size: 9pt, fill: slate, counter(page).display("1")),
    ),
  )
  set text(font: "Liberation Sans", size: 9.5pt)
  set par(justify: true, leading: 0.6em)
  set heading(numbering: "1.1.")
  show heading: set block(above: 1.2em, below: 0.7em)
  set list(spacing: 0.85em)

  body

  if pages != none {
    context {
      let n = counter(page).final().first()
      assert(
        n == pages,
        message: "Page count is " + str(n) + ", expected " + str(pages),
      )
    }
  }
}
