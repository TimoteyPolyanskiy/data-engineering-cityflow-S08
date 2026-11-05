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

-- Solution: one row = day x merchant x currency, delivered orders only.
CREATE OR REPLACE VIEW lab03_cf.v_daily_orders AS
WITH selected_orders AS (
  -- grain: one order; delivered orders of the selected month
  SELECT order_id, merchant_id, currency, total_amount, report_date
  FROM lab03_cf.v_period_orders
  WHERE order_status = 'delivered'
), items_by_order AS (
  -- pre-aggregate items to the order grain: at most one row per order_id
  SELECT order_id, SUM(quantity) AS units
  FROM core.order_items
  GROUP BY order_id
), orders_with_units AS (
  -- LEFT JOIN keeps orders without items; 1:1 join, so no row multiplication
  SELECT s.report_date, s.merchant_id, s.currency, s.order_id, s.total_amount,
         COALESCE(i.units, 0) AS units,
         (i.order_id IS NULL) AS has_no_items
  FROM selected_orders s
  LEFT JOIN items_by_order i ON i.order_id = s.order_id
)
SELECT report_date,
       merchant_id,
       currency,
       COUNT(*) AS order_count,
       SUM(total_amount) AS order_amount,
       ROUND(SUM(total_amount) / COUNT(*), 2) AS avg_order_amount,
       SUM(units) AS accepted_units,
       COUNT(*) FILTER (WHERE has_no_items) AS orders_without_items
FROM orders_with_units
GROUP BY report_date, merchant_id, currency;

-- First 10 rows of the daily report
SELECT * FROM lab03_cf.v_daily_orders ORDER BY report_date, merchant_id, currency LIMIT 10;
