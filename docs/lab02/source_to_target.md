# Source-to-target mapping (CSV → stg → core)

Усі колонки CSV зберігаються в `stg` як `text` без змін; у таблиці — що потрапляє в `core` і як перетворюється.

| Джерело (CSV) | Колонка | → core | Перетворення |
|---|---|---|---|
| customers.csv | customer_id | customers.customer_id | trim; PK |
| | full_name, city | customers.full_name, city | trim; `NOT NULL` |
| | registered_at | customers.registered_at | `timestamptz`, UTC |
| | email, phone, service_zone_id, customer_status | — | лишаються в `stg` |
| merchants.csv | merchant_id, merchant_name, city | merchants.* | trim; PK; `NOT NULL` |
| | opened_at | merchants.opened_at | `timestamptz`, UTC |
| | merchant_type, service_zone_id, merchant_status | — | лишаються в `stg` |
| products.csv | product_id, merchant_id, product_name | products.* | trim; PK; FK → merchants |
| | unit_price_uah | products.unit_price_uah | `numeric(12,2)`; активний товар `> 0` |
| | is_active | products.is_active | `boolean` |
| | category, updated_at | — | лишаються в `stg` |
| orders.csv | order_id, customer_id, merchant_id | orders.* | trim; PK; FK → customers, merchants |
| | created_at | orders.created_at | `timestamptz`, UTC |
| | order_status | orders.order_status | trim; `NOT NULL` |
| | currency | orders.currency | trim + верхній регістр; `IN (UAH, USD, EUR)` |
| | subtotal_amount, delivery_fee, discount_amount, total_amount | orders.* | `numeric(12,2)`, `≥ 0` |
| order_items.csv | order_item_id, order_id, product_id | order_items.* | trim; PK; FK → orders, products |
| | quantity | order_items.quantity | `integer`, `> 0` |
| | unit_price, line_discount, line_total | order_items.* | `numeric(12,2)`, `≥ 0` |
| | currency | order_items.currency | trim + верхній регістр; `IN (UAH, USD, EUR)` |

`payments`, `refunds`, `couriers`, `deliveries`, `service_zones` у цій роботі не завантажуються.
