SELECT
    o.order_id,
    o.ordered_at,
    c.customer_name,
    p.product_name,
    oi.quantity,
    p.unit_price,
    ROUND(oi.quantity * p.unit_price, 2) AS line_total
FROM orders AS o
JOIN customers AS c ON c.customer_id = o.customer_id
JOIN order_items AS oi ON oi.order_id = o.order_id
JOIN products AS p ON p.product_id = oi.product_id
ORDER BY o.order_id, p.product_name;

