-- sql/lab02/02_checks.sql
-- Чотири контрольні SQL-перевірки + діагностика формул.
-- Запуск: docker compose exec -T postgres psql -U cityflow_user -d cityflow_s08 < sql/lab02/02_checks.sql

\echo '=== 1. Дублікати PK у core (очікується 0 рядків) ==='
SELECT 'core.customers' AS target_table, customer_id AS duplicate_key, count(*) AS n FROM core.customers GROUP BY customer_id HAVING count(*) > 1
UNION ALL SELECT 'core.merchants', merchant_id, count(*) FROM core.merchants GROUP BY merchant_id HAVING count(*) > 1
UNION ALL SELECT 'core.products', product_id, count(*) FROM core.products GROUP BY product_id HAVING count(*) > 1
UNION ALL SELECT 'core.orders', order_id, count(*) FROM core.orders GROUP BY order_id HAVING count(*) > 1
UNION ALL SELECT 'core.order_items', order_item_id, count(*) FROM core.order_items GROUP BY order_item_id HAVING count(*) > 1;

\echo '=== 2. Відсутні FK у core (очікується 0 у кожному рядку) ==='
SELECT 'orders -> customers' AS foreign_key, count(*) AS missing FROM core.orders o LEFT JOIN core.customers c USING (customer_id) WHERE c.customer_id IS NULL
UNION ALL SELECT 'orders -> merchants', count(*) FROM core.orders o LEFT JOIN core.merchants m USING (merchant_id) WHERE m.merchant_id IS NULL
UNION ALL SELECT 'products -> merchants', count(*) FROM core.products p LEFT JOIN core.merchants m USING (merchant_id) WHERE m.merchant_id IS NULL
UNION ALL SELECT 'order_items -> orders', count(*) FROM core.order_items i LEFT JOIN core.orders o USING (order_id) WHERE o.order_id IS NULL
UNION ALL SELECT 'order_items -> products', count(*) FROM core.order_items i LEFT JOIN core.products p USING (product_id) WHERE p.product_id IS NULL;

\echo '=== 3a. orders: прийняте у staging vs core, окремо за валютами ==='
WITH last_run AS (
    SELECT max(run_id) AS run_id FROM audit.pipeline_runs WHERE status = 'SUCCESS' AND batch_id = 'S08-V1'
), stg_accepted AS (
    SELECT upper(btrim(s.currency)) AS currency, count(*) AS n, sum(btrim(s.total_amount)::numeric) AS total
    FROM stg.orders s
    JOIN audit.row_decisions d ON d.source_file = 'orders.csv' AND d.source_row_number = s.source_row_number AND d.final_status = 'accepted'
    JOIN last_run l ON l.run_id = d.run_id
    GROUP BY 1
), core_agg AS (
    SELECT currency, count(*) AS n, sum(total_amount) AS total FROM core.orders GROUP BY 1
)
SELECT coalesce(s.currency, c.currency) AS currency, s.n AS stg_rows, c.n AS core_rows,
       s.total AS stg_total, c.total AS core_total, (s.n = c.n AND s.total = c.total) AS match
FROM stg_accepted s FULL JOIN core_agg c ON c.currency = s.currency ORDER BY 1;

\echo '=== 3b. order_items: прийняте у staging vs core, окремо за валютами ==='
WITH last_run AS (
    SELECT max(run_id) AS run_id FROM audit.pipeline_runs WHERE status = 'SUCCESS' AND batch_id = 'S08-V1'
), stg_accepted AS (
    SELECT upper(btrim(s.currency)) AS currency, count(*) AS n, sum(btrim(s.line_total)::numeric) AS total
    FROM stg.order_items s
    JOIN audit.row_decisions d ON d.source_file = 'order_items.csv' AND d.source_row_number = s.source_row_number AND d.final_status = 'accepted'
    JOIN last_run l ON l.run_id = d.run_id
    GROUP BY 1
), core_agg AS (
    SELECT currency, count(*) AS n, sum(line_total) AS total FROM core.order_items GROUP BY 1
)
SELECT coalesce(s.currency, c.currency) AS currency, s.n AS stg_rows, c.n AS core_rows,
       s.total AS stg_total, c.total AS core_total, (s.n = c.n AND s.total = c.total) AS match
FROM stg_accepted s FULL JOIN core_agg c ON c.currency = s.currency ORDER BY 1;

\echo '=== 4. Fan-out: завищена сума після JOIN та правильний запит (за валютами, без DISTINCT) ==='
-- Рівень деталізації: orders = 1 рядок на замовлення, order_items = 1 рядок на позицію.
-- JOIN orders x order_items повторює total_amount для кожної позиції; тому позиції спершу
-- агрегуються до рівня замовлення (CTE items_agg), і лише потім з'єднуються 1:1.
WITH wrong AS (
    SELECT o.currency, count(*) AS joined_rows, sum(o.total_amount) AS inflated_sum
    FROM core.orders o JOIN core.order_items i ON i.order_id = o.order_id GROUP BY o.currency
), truth AS (
    SELECT currency, count(*) AS order_rows, sum(total_amount) AS true_sum FROM core.orders GROUP BY currency
), items_agg AS (
    SELECT order_id, sum(line_total) AS items_sum FROM core.order_items GROUP BY order_id
), correct AS (
    SELECT o.currency, count(*) AS orders_with_items, sum(o.total_amount) AS orders_total, sum(a.items_sum) AS items_total
    FROM core.orders o JOIN items_agg a ON a.order_id = o.order_id GROUP BY o.currency
)
SELECT t.currency, t.order_rows, w.joined_rows, t.true_sum, w.inflated_sum, c.orders_with_items, c.orders_total, c.items_total
FROM truth t LEFT JOIN wrong w USING (currency) LEFT JOIN correct c USING (currency) ORDER BY 1;

\echo '=== Діагностика (значення джерела не змінюються): subtotal + delivery_fee - discount <> total ==='
SELECT order_id, currency, subtotal_amount, delivery_fee, discount_amount, total_amount,
       subtotal_amount + delivery_fee - discount_amount - total_amount AS difference
FROM core.orders
WHERE abs(subtotal_amount + delivery_fee - discount_amount - total_amount) > 0.01
ORDER BY order_id;
