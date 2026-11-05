-- СТУДЕНТ. Блок А: виконайте три порівняння. Два останні — НАВМИСНО неправильні.
SELECT currency, COUNT(*) AS orders, SUM(total_amount) AS correct_amount
FROM lab03_cf.v_period_orders WHERE order_status = 'delivered'
GROUP BY currency ORDER BY currency;
SELECT o.currency, COUNT(*) AS joined_rows, SUM(o.total_amount) AS wrong_amount
FROM lab03_cf.v_period_orders o JOIN core.order_items i ON i.order_id = o.order_id
WHERE o.order_status = 'delivered' GROUP BY o.currency ORDER BY o.currency;
SELECT o.currency, SUM(DISTINCT o.total_amount) AS not_a_valid_fix
FROM lab03_cf.v_period_orders o JOIN core.order_items i ON i.order_id = o.order_id
WHERE o.order_status = 'delivered' GROUP BY o.currency ORDER BY o.currency;

-- Блок Б: допишіть CREATE OR REPLACE VIEW lab03_cf.v_daily_orders AS ...
-- Не змінюйте core та v_period_orders. Приклад першого CTE:
WITH items_by_order AS (
  SELECT order_id, SUM(quantity) AS units
  FROM core.order_items GROUP BY order_id
)
SELECT * FROM items_by_order ORDER BY order_id LIMIT 10;

-- TODO: 3 CTE у ВАШОМУ запиті:
-- selected_orders: v_period_orders WHERE order_status = 'delivered';
-- items_by_order: один рядок на order_id, сума quantity;
-- orders_with_units: LEFT JOIN selected_orders з items_by_order за order_id.
-- Відсутній units -> COALESCE(units, 0). Відсутнє i.order_id -> ознака без позицій.
-- GROUP BY report_date, merchant_id, currency.
-- Порядок вихідних колонок:
-- report_date, merchant_id, currency, order_count, order_amount,
-- avg_order_amount, accepted_units, orders_without_items.
-- Типи: date, text, text, bigint, numeric, numeric, bigint/numeric, bigint.
-- Правила п'яти метрик наведені в завданні. Створіть VIEW, а не таблицю.
-- Приклад читання ПІСЛЯ створення:
-- SELECT * FROM lab03_cf.v_daily_orders ORDER BY report_date, merchant_id, currency;
