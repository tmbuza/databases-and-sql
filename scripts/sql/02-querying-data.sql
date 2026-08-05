-- 01: Explicit column selection
SELECT customer_id, customer_name, segment, country
FROM customers
ORDER BY customer_id;

-- 02: Distinct combinations
SELECT DISTINCT segment, country
FROM customers
ORDER BY segment, country;

-- 03: Calculated order values
SELECT
    order_id,
    ROUND(quantity * unit_price_at_order, 2) AS gross_value,
    ROUND(quantity * unit_price_at_order * discount_rate, 2) AS discount_value,
    ROUND(quantity * unit_price_at_order * (1 - discount_rate), 2) AS net_value
FROM orders
ORDER BY order_id;

-- 04: Null-aware filtering
SELECT
    order_id,
    status,
    shipped_date,
    COALESCE(shipped_date, 'not shipped') AS shipping_date
FROM orders
WHERE shipped_date IS NULL
ORDER BY order_id;

-- 05: Sorted and limited products
SELECT product_id, product_name, unit_price
FROM products
WHERE is_active = 1
ORDER BY unit_price DESC, product_id ASC
LIMIT 3;

-- 06: Guided-practical solution
SELECT
    order_id,
    customer_id,
    product_id,
    order_date,
    status,
    ROUND(quantity * unit_price_at_order * (1 - discount_rate), 2) AS net_value
FROM orders
WHERE status IN ('completed', 'shipped')
  AND order_date BETWEEN '2026-01-01' AND '2026-02-15'
  AND quantity * unit_price_at_order * (1 - discount_rate) >= 100
ORDER BY net_value DESC, order_id ASC;

