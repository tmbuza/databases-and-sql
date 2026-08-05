SELECT
    c.segment,
    COUNT(*) AS completed_orders,
    ROUND(SUM(o.order_total), 2) AS revenue,
    ROUND(AVG(o.order_total), 2) AS average_order_value
FROM orders AS o
JOIN customers AS c ON o.customer_id = c.customer_id
WHERE o.status = 'completed'
  AND o.order_date >= :start_date
  AND o.order_date < :end_date
GROUP BY c.segment
ORDER BY revenue DESC;
