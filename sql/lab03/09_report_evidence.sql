-- Extra read-only queries for the lab 3 report (run after 00-04). Nothing is created or changed.

-- 2.1 Why SUM(DISTINCT) matched by chance: are all delivered amounts distinct?
SELECT currency, COUNT(*) AS delivered_orders, COUNT(DISTINCT total_amount) AS distinct_amounts
FROM lab03_cf.v_period_orders WHERE order_status = 'delivered'
GROUP BY currency ORDER BY currency;

-- 2.2 Orders with several item rows (query from the manual)
SELECT order_id, COUNT(*) AS item_rows
FROM core.order_items
GROUP BY order_id
HAVING COUNT(*) > 1
ORDER BY order_id
LIMIT 10;

-- 2.2 Manual check: delivered UAH orders of one merchant and one day
SELECT o.order_id, o.total_amount,
       COUNT(i.order_item_id) AS item_rows,
       COALESCE(SUM(i.quantity), 0) AS units
FROM lab03_cf.v_period_orders o
LEFT JOIN core.order_items i ON i.order_id = o.order_id
WHERE o.order_status = 'delivered' AND o.currency = 'UAH'
  AND o.merchant_id = 'S08-M00038' AND o.report_date = DATE '2025-09-01'
GROUP BY o.order_id, o.total_amount
ORDER BY o.order_id;

-- 2.2 The same orders: correct sum vs sum after JOIN with items
SELECT (SELECT SUM(total_amount) FROM lab03_cf.v_period_orders
        WHERE order_status = 'delivered' AND currency = 'UAH'
          AND merchant_id = 'S08-M00038' AND report_date = DATE '2025-09-01') AS correct_amount,
       (SELECT SUM(o.total_amount) FROM lab03_cf.v_period_orders o
        JOIN core.order_items i ON i.order_id = o.order_id
        WHERE o.order_status = 'delivered' AND o.currency = 'UAH'
          AND o.merchant_id = 'S08-M00038' AND o.report_date = DATE '2025-09-01') AS joined_amount;

-- The same day and merchant in the daily report
SELECT * FROM lab03_cf.v_daily_orders
WHERE merchant_id = 'S08-M00038' AND currency = 'UAH' AND report_date = DATE '2025-09-01';

-- 3.2 Whole-month totals of the daily report
SELECT COUNT(*) AS daily_rows, SUM(order_count) AS orders, SUM(accepted_units) AS units,
       SUM(orders_without_items) AS orders_without_items
FROM lab03_cf.v_daily_orders;

-- 4.1 Running total of one merchant and currency (merchant with the most report days)
SELECT * FROM lab03_cf.v_running_orders
WHERE merchant_id = 'S08-M00016' AND currency = 'UAH'
ORDER BY report_date;

SELECT SUM(order_amount) AS group_total
FROM lab03_cf.v_daily_orders
WHERE merchant_id = 'S08-M00016' AND currency = 'UAH';

-- 4.2 All orders of one customer in the month and the chosen latest one
SELECT order_id, created_at, order_status, currency, total_amount,
       ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC, order_id DESC) AS rn
FROM lab03_cf.v_period_orders
WHERE customer_id = 'S08-C000352'
ORDER BY rn;

SELECT * FROM lab03_cf.v_latest_customer_order WHERE customer_id = 'S08-C000352';

-- 4.2 Are there ties on created_at inside one customer?
SELECT COUNT(*) AS customers_with_tied_created_at
FROM (SELECT customer_id, created_at FROM lab03_cf.v_period_orders
      GROUP BY customer_id, created_at HAVING COUNT(*) > 1) t;
