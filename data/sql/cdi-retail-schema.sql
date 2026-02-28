-- CDI Retail (mini) schema
-- Designed to teach: keys, joins, aggregation, and normalization

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
  customer_id TEXT PRIMARY KEY,
  full_name   TEXT NOT NULL,
  city        TEXT NOT NULL,
  country     TEXT NOT NULL,
  signup_date DATE NOT NULL
);

CREATE TABLE products (
  product_id   TEXT PRIMARY KEY,
  product_name TEXT NOT NULL,
  category     TEXT NOT NULL,
  unit_price   REAL NOT NULL CHECK (unit_price >= 0)
);

CREATE TABLE orders (
  order_id    TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  order_date  DATE NOT NULL,
  status      TEXT NOT NULL,
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
  order_item_id TEXT PRIMARY KEY,
  order_id      TEXT NOT NULL,
  product_id    TEXT NOT NULL,
  quantity      INTEGER NOT NULL CHECK (quantity > 0),
  unit_price    REAL NOT NULL CHECK (unit_price >= 0),
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (product_id) REFERENCES products(product_id)
);
