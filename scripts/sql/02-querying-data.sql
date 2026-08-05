SELECT
    customer_id,
    customer_name,
    region
FROM customers
WHERE region = :region
ORDER BY customer_name;

