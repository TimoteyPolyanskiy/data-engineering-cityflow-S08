from pathlib import Path
import matplotlib.patches as patches
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = [
    "DejaVu Sans",
    "Liberation Sans",
    "sans-serif",
]
fig, ax = plt.subplots(figsize=(13, 8), dpi=300)
ax.set_facecolor("#f8fafc")
fig.patch.set_facecolor("#ffffff")


def draw_table(ax, x, y, width, height, title, columns):
    header_box = patches.FancyBboxPatch(
        (x, y + height - 0.5),
        width,
        0.5,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor="#1e293b",
        edgecolor="#0f172a",
        linewidth=1.2,
    )
    ax.add_patch(header_box)
    ax.text(
        x + width / 2,
        y + height - 0.25,
        title,
        color="#ffffff",
        fontsize=10.5,
        weight="bold",
        ha="center",
        va="center",
    )

    body_box = patches.FancyBboxPatch(
        (x, y),
        width,
        height - 0.5,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor="#ffffff",
        edgecolor="#cbd5e1",
        linewidth=1.2,
    )
    ax.add_patch(body_box)

    cur_y = y + height - 0.75
    for col_name, col_type, is_pk, is_fk in columns:
        badge = ""
        badge_color = "#64748b"
        if is_pk:
            badge = "[PK] "
            badge_color = "#b91c1c"
        elif is_fk:
            badge = "[FK] "
            badge_color = "#0369a1"

        ax.text(
            x + 0.15,
            cur_y,
            badge + col_name,
            fontsize=8.5,
            color=badge_color if (is_pk or is_fk) else "#334155",
            weight="bold" if is_pk else "normal",
            va="center",
        )
        ax.text(
            x + width - 0.15,
            cur_y,
            col_type,
            fontsize=8.0,
            color="#64748b",
            ha="right",
            va="center",
            style="italic",
        )
        cur_y -= 0.32


# Таблиці Core
draw_table(
    ax,
    0.5,
    5.0,
    3.4,
    2.2,
    "core.customers",
    [
        ("customer_id", "TEXT", True, False),
        ("full_name", "TEXT", False, False),
        ("city", "TEXT", False, False),
        ("registered_at", "TIMESTAMPTZ", False, False),
    ],
)

draw_table(
    ax,
    0.5,
    1.5,
    3.4,
    2.2,
    "core.merchants",
    [
        ("merchant_id", "TEXT", True, False),
        ("merchant_name", "TEXT", False, False),
        ("city", "TEXT", False, False),
        ("opened_at", "TIMESTAMPTZ", False, False),
    ],
)

draw_table(
    ax,
    4.8,
    1.2,
    3.4,
    2.5,
    "core.products",
    [
        ("product_id", "TEXT", True, False),
        ("merchant_id", "TEXT", False, True),
        ("product_name", "TEXT", False, False),
        ("unit_price_uah", "NUMERIC(12,2)", False, False),
        ("is_active", "BOOLEAN", False, False),
    ],
)

draw_table(
    ax,
    4.8,
    4.4,
    3.4,
    3.3,
    "core.orders",
    [
        ("order_id", "TEXT", True, False),
        ("customer_id", "TEXT", False, True),
        ("merchant_id", "TEXT", False, True),
        ("created_at", "TIMESTAMPTZ", False, False),
        ("order_status", "TEXT", False, False),
        ("currency", "VARCHAR(3)", False, False),
        ("subtotal_amount", "NUMERIC(12,2)", False, False),
        ("total_amount", "NUMERIC(12,2)", False, False),
    ],
)

draw_table(
    ax,
    9.1,
    2.6,
    3.4,
    3.2,
    "core.order_items",
    [
        ("order_item_id", "TEXT", True, False),
        ("order_id", "TEXT", False, True),
        ("product_id", "TEXT", False, True),
        ("quantity", "INTEGER", False, False),
        ("unit_price", "NUMERIC(12,2)", False, False),
        ("line_discount", "NUMERIC(12,2)", False, False),
        ("line_total", "NUMERIC(12,2)", False, False),
        ("currency", "VARCHAR(3)", False, False),
    ],
)


# Зв'язки (FK Connections)
def draw_rel(ax, start, end, label="1:N"):
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops=dict(
            arrowstyle="-|>",
            color="#475569",
            lw=1.5,
            ls="--",
            mutation_scale=12,
        ),
    )
    mid_x = (start[0] + end[0]) / 2
    mid_y = (start[1] + end[1]) / 2
    ax.text(
        mid_x,
        mid_y + 0.12,
        label,
        fontsize=7.5,
        color="#0f172a",
        weight="bold",
        ha="center",
        bbox=dict(
            boxstyle="round,pad=0.2",
            fc="#ffffff",
            ec="#cbd5e1",
            lw=0.8,
            alpha=0.9,
        ),
    )


draw_rel(ax, (3.9, 6.2), (4.8, 6.2), "1:N (cust_id)")
draw_rel(ax, (3.9, 2.5), (4.8, 5.2), "1:N (merch_id)")
draw_rel(ax, (3.9, 2.0), (4.8, 2.0), "1:N (merch_id)")
draw_rel(ax, (8.2, 5.8), (9.1, 4.4), "1:N (order_id)")
draw_rel(ax, (8.2, 2.4), (9.1, 3.6), "1:N (product_id)")

ax.set_xlim(0, 13)
ax.set_ylim(0.5, 8.2)
ax.axis("off")

plt.title(
    "CityFlow S08: Реляційна модель Core-шару (PK, FK та Grain)",
    fontsize=14,
    weight="bold",
    pad=15,
    color="#0f172a",
)
output_path = Path("docs/lab02/erd_lab02.png")
output_path.parent.mkdir(parents=True, exist_ok=True)
plt.tight_layout()
plt.savefig(output_path, dpi=300)
plt.close()
print(f"ER-діаграму збережено у {output_path}")
