-- Seed data (small on purpose for teaching)

INSERT INTO customers (customer_id, full_name, city, country, signup_date) VALUES
  ('C1001','Amina Hassan','Dar es Salaam','Tanzania','2025-10-02'),
  ('C1002','Joseph Kimaro','Arusha','Tanzania','2025-11-14'),
  ('C1003','Neema Msuya','Mwanza','Tanzania','2025-12-01'),
  ('C1004','Grace Nyerere','Nairobi','Kenya','2025-12-20'),
  ('C1005','David Okello','Kampala','Uganda','2026-01-10');

INSERT INTO products (product_id, product_name, category, unit_price) VALUES
  ('P2001','Notebook A5','Stationery',2.50),
  ('P2002','Pen Blue','Stationery',0.80),
  ('P2003','USB Drive 32GB','Electronics',8.90),
  ('P2004','Headphones','Electronics',19.50),
  ('P2005','Water Bottle','Lifestyle',6.25);

INSERT INTO orders (order_id, customer_id, order_date, status) VALUES
  ('O3001','C1001','2026-01-15','paid'),
  ('O3002','C1001','2026-02-02','paid'),
  ('O3003','C1002','2026-02-05','paid'),
  ('O3004','C1003','2026-02-11','cancelled'),
  ('O3005','C1004','2026-02-14','paid');

INSERT INTO order_items (order_item_id, order_id, product_id, quantity, unit_price) VALUES
  ('OI4001','O3001','P2001',2,2.50),
  ('OI4002','O3001','P2002',5,0.80),
  ('OI4003','O3002','P2003',1,8.90),
  ('OI4004','O3002','P2002',2,0.80),
  ('OI4005','O3003','P2004',1,19.50),
  ('OI4006','O3003','P2005',1,6.25),
  ('OI4007','O3004','P2001',1,2.50),
  ('OI4008','O3005','P2003',2,8.90);
