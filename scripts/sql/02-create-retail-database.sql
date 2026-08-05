PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    segment       TEXT NOT NULL CHECK (segment IN ('Consumer', 'Business', 'Enterprise')),
    country       TEXT NOT NULL,
    city          TEXT NOT NULL,
    signup_date   TEXT NOT NULL
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category     TEXT NOT NULL,
    unit_price   REAL NOT NULL CHECK (unit_price >= 0),
    is_active    INTEGER NOT NULL CHECK (is_active IN (0, 1))
);

CREATE TABLE orders (
    order_id           INTEGER PRIMARY KEY,
    customer_id        INTEGER NOT NULL REFERENCES customers(customer_id),
    product_id         INTEGER NOT NULL REFERENCES products(product_id),
    order_date         TEXT NOT NULL,
    quantity           INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_order REAL NOT NULL CHECK (unit_price_at_order >= 0),
    discount_rate      REAL NOT NULL DEFAULT 0 CHECK (discount_rate BETWEEN 0 AND 1),
    status              TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'shipped', 'cancelled')),
    shipped_date        TEXT,
    CHECK (shipped_date IS NULL OR shipped_date >= order_date)
);

INSERT INTO customers VALUES
    (1, 'Amina Said',     'Consumer',   'Tanzania', 'Dar es Salaam', '2025-10-04'),
    (2, 'Baraka Mushi',   'Business',   'Tanzania', 'Arusha',        '2025-10-18'),
    (3, 'Chausiku Nyerere','Enterprise','Tanzania', 'Dodoma',        '2025-11-02'),
    (4, 'David Otieno',   'Consumer',   'Kenya',    'Nairobi',       '2025-11-20'),
    (5, 'Esther Banda',   'Business',   'Zambia',   'Lusaka',        '2025-12-01'),
    (6, 'Faraja Mrema',   'Enterprise', 'Tanzania', 'Mwanza',        '2025-12-15'),
    (7, 'Mariam Juma',    'Consumer',   'Tanzania', 'Morogoro',      '2026-01-03'),
    (8, 'Samuel Kato',    'Business',   'Uganda',   'Kampala',       '2026-01-09');

INSERT INTO products VALUES
    (101, 'USB-C Hub',           'Accessories',  45.00, 1),
    (102, 'Mechanical Keyboard', 'Accessories',  95.00, 1),
    (103, '27-inch Monitor',     'Displays',     310.00, 1),
    (104, 'Laptop Stand',        'Accessories',  62.50, 1),
    (105, 'Office Chair',        'Furniture',    240.00, 1),
    (106, 'Webcam',              'Video',         85.00, 1),
    (107, 'Legacy Dock',         'Accessories', 130.00, 0);

INSERT INTO orders VALUES
    (1001, 1, 101, '2026-01-03', 2,  45.00, 0.00, 'completed', '2026-01-04'),
    (1002, 2, 103, '2026-01-05', 3, 310.00, 0.10, 'shipped',   '2026-01-07'),
    (1003, 3, 105, '2026-01-08', 6, 240.00, 0.15, 'completed', '2026-01-10'),
    (1004, 4, 102, '2026-01-12', 1,  95.00, 0.00, 'cancelled', NULL),
    (1005, 5, 104, '2026-01-17', 4,  62.50, 0.05, 'completed', '2026-01-19'),
    (1006, 6, 103, '2026-01-23', 8, 310.00, 0.12, 'shipped',   '2026-01-25'),
    (1007, 7, 106, '2026-01-29', 1,  85.00, 0.00, 'pending',   NULL),
    (1008, 8, 101, '2026-02-02',10,  45.00, 0.08, 'completed', '2026-02-03'),
    (1009, 1, 104, '2026-02-06', 2,  62.50, 0.00, 'completed', '2026-02-08'),
    (1010, 2, 105, '2026-02-11', 2, 240.00, 0.05, 'shipped',   '2026-02-12'),
    (1011, 3, 102, '2026-02-15', 5,  95.00, 0.10, 'completed', '2026-02-17'),
    (1012, 4, 106, '2026-02-18', 2,  85.00, 0.00, 'pending',   NULL),
    (1013, 5, 103, '2026-02-22', 1, 310.00, 0.00, 'completed', '2026-02-24'),
    (1014, 6, 105, '2026-02-26', 4, 240.00, 0.20, 'cancelled', NULL),
    (1015, 7, 101, '2026-03-01', 3,  45.00, 0.00, 'completed', '2026-03-02'),
    (1016, 8, 104, '2026-03-04', 6,  62.50, 0.10, 'shipped',   '2026-03-06'),
    (1017, 1, 102, '2026-03-08', 2,  95.00, 0.05, 'completed', '2026-03-09'),
    (1018, 3, 103, '2026-03-12', 2, 310.00, 0.07, 'completed', '2026-03-14');

