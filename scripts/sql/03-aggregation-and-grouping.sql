SELECT
    o.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    ROUND(SUM(oi.quantity * p.unit_price), 2) AS revenue
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.order_id
JOIN products AS p ON p.product_id = oi.product_id
GROUP BY o.customer_id
HAVING SUM(oi.quantity * p.unit_price) > 0
ORDER BY revenue DESC;

