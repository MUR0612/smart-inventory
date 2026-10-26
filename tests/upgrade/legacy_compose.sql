-- Fixture: database as created by the pre-2026-10 Compose setup
-- (mysql/init/02-schema.sql + 05-migrate-orders.sql + 04-seed.sql) with orders
-- placed by the old code, which deducted stock directly at order creation.
-- The password below is a throwaway fixture value, not a real credential.
CREATE TABLE products (
  id BIGINT PRIMARY KEY AUTO_INCREMENT, sku VARCHAR(64) NOT NULL UNIQUE, name VARCHAR(255) NOT NULL,
  price DECIMAL(10,2) NOT NULL DEFAULT 0.00, safety_stock INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE inventory (
  product_id BIGINT NOT NULL, stock INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, PRIMARY KEY (product_id),
  CONSTRAINT fk_inventory_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE);
CREATE TABLE orders (
  id BIGINT PRIMARY KEY AUTO_INCREMENT, status VARCHAR(32) NOT NULL, total DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE order_items (
  id BIGINT PRIMARY KEY AUTO_INCREMENT, order_id BIGINT NOT NULL, product_id BIGINT NOT NULL, qty INT NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
  CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES products(id));
ALTER TABLE orders ADD COLUMN customer_name VARCHAR(255) NULL, ADD COLUMN customer_email VARCHAR(255) NULL,
  ADD COLUMN shipping_address TEXT NULL, ADD COLUMN notes TEXT NULL,
  ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  ADD COLUMN paid_at TIMESTAMP NULL, ADD COLUMN shipped_at TIMESTAMP NULL;

INSERT INTO products (sku, name, price, safety_stock) VALUES
  ('SKU-1001','Test Widget',19.99,5), ('SKU-1002','Pro Gadget',49.50,3), ('SKU-2001','Mega Tool',129.00,2);
INSERT INTO inventory (product_id, stock) VALUES (1, 48), (2, 49), (3, 49);
INSERT INTO orders (id, status, total, customer_name) VALUES
  (1, 'CREATED', 39.98, 'Legacy A'), (2, 'PAID', 49.50, 'Legacy B'), (3, 'SHIPPED', 129.00, 'Legacy C'),
  (4, 'CANCELLED', 19.99, 'Legacy D');
INSERT INTO order_items (order_id, product_id, qty, unit_price) VALUES
  (1, 1, 1, 19.99), (1, 1, 1, 19.99), (2, 2, 1, 49.50), (3, 3, 1, 129.00), (4, 1, 1, 19.99);

-- The old init script gave the application account ALL PRIVILEGES.
CREATE USER 'inventory_app'@'%' IDENTIFIED BY 'legacy-fixture-only';
GRANT ALL PRIVILEGES ON smart_inventory.* TO 'inventory_app'@'%';
