"""Малює docs/lab01/architecture_v0.png: що реалізовано в Лабі 1 (суцільні лінії) і що заплановано (пунктир).

Запуск: uv run python scripts/lab01/build_architecture.py
"""

from pathlib import Path

import matplotlib.patches as patches
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
BLUE, GREEN, GREY, DARK = "#1d4e89", "#2f855a", "#718096", "#1a202c"

fig, ax = plt.subplots(figsize=(11, 6.6), dpi=200)
ax.set_xlim(0, 11)
ax.set_ylim(0, 6.6)
ax.axis("off")


def box(x, y, w, h, text, color, dashed=False, size=11, fill="#ffffff"):
    ax.add_patch(patches.FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.03,rounding_size=0.12",
        linewidth=2, edgecolor=color, facecolor=fill, linestyle="--" if dashed else "-"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=DARK, linespacing=1.35)


def arrow(x1, y1, x2, y2, color=DARK, dashed=False):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", lw=2, color=color, linestyle="--" if dashed else "-", shrinkA=0, shrinkB=0))


ax.text(5.5, 6.35, "CityFlow: архітектура проєкту на етапі Лабораторної роботи №1", ha="center", fontsize=14, weight="bold", color=DARK)

# реалізовано
box(0.2, 4.35, 2.4, 1.35, "4 CSV-файли\ncustomers · merchants\nproducts · orders", BLUE)
box(3.1, 4.35, 2.5, 1.35, "data/raw/base_v1/\nлокальні raw-файли\n(незмінні, поза Git)", BLUE)
box(6.1, 4.35, 2.3, 1.35, "Profiling notebook\n01_source_profiling\n(pandas, matplotlib)", GREEN, fill="#f0fff4")
box(8.8, 5.0, 2.0, 0.7, "data/sample/\n(≤ 100 рядків)", BLUE, size=10)
box(8.8, 3.95, 2.0, 0.85, "docs/lab01/\nсловник, реєстр,\nграфіки, metrics.json", BLUE, size=9.5)
arrow(2.6, 5.02, 3.1, 5.02)
arrow(5.6, 5.02, 6.1, 5.02)
arrow(8.4, 5.35, 8.8, 5.35)
arrow(8.4, 4.6, 8.8, 4.4)

box(3.1, 2.3, 7.7, 1.0, "Git-репозиторій (GitHub): код, notebooks, документація, sample\nraw-дані та .env у репозиторій не потрапляють", DARK, fill="#edf2f7")
arrow(7.25, 4.35, 7.25, 3.3, DARK)        # notebook -> Git
arrow(9.8, 3.95, 9.8, 3.3, DARK)           # docs -> Git
ax.text(0.2, 3.1, "Суцільна лінія — реалізовано\nв Лабораторній №1", fontsize=10, color=DARK, va="top")
ax.text(0.2, 2.55, "Пунктир — заплановано,\nне реалізовано", fontsize=10, color=GREY, va="top")

# заплановано
ax.text(5.5, 1.78, "Заплановані компоненти (на цьому етапі не реалізовані)", ha="center", fontsize=11, color=GREY, style="italic")
names = ["API", "PostgreSQL", "Сховище", "Трансформації", "Оркестрація", "Дашборд"]
w, gap, x = 1.5, 0.32, 0.2
for i, name in enumerate(names):
    box(x, 0.35, w, 0.95, name, GREY, dashed=True, size=11)
    if i:
        arrow(x - gap + 0.04, 0.82, x - 0.04, 0.82, GREY, dashed=True)
    x += w + gap

fig.savefig(ROOT / "docs/lab01/architecture_v0.png", bbox_inches="tight", facecolor="white")
print("Записано docs/lab01/architecture_v0.png")
