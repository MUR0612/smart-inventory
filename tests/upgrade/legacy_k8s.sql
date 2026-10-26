-- Fixture: schema from the pre-2026-10 k8s/mysql.yaml init ConfigMap
-- (inventory.quantity, orders.total_amount, order_items.quantity/price, INT ids).
CREATE TABLE products (
  id INT AUTO_INCREMENT PRIMARY KEY, sku VARCHAR(50) UNIQUE NOT NULL, name VARCHAR(255) NOT NULL,
  price DECIMAL(10,2) NOT NULL, safety_stock INT DEFAULT 10,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);
CREATE TABLE inventory (
  id INT AUTO_INCREMENT PRIMARY KEY, product_id INT NOT NULL, quantity INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE);
CREATE TABLE orders (
  id INT AUTO_INCREMENT PRIMARY KEY, customer_name VARCHAR(255) NOT NULL, customer_email VARCHAR(255) NOT NULL,
  shipping_address TEXT NOT NULL, status ENUM('CREATED', 'PAID', 'SHIPPED', 'CANCELLED') DEFAULT 'CREATED',
  total_amount DECIMAL(10,2) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);
CREATE TABLE order_items (
  id INT AUTO_INCREMENT PRIMARY KEY, order_id INT NOT NULL, product_id INT NOT NULL, quantity INT NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE);

INSERT INTO products (sku, name, price, safety_stock) VALUES
  ('SKU-1001','Test Widget',19.99,5), ('SKU-1002','Pro Gadget',49.50,3), ('SKU-2001','Mega Tool',129.00,2);
-- Two rows for product 1 (the old schema allowed it): they are summed into one.
INSERT INTO inventory (product_id, quantity) VALUES (1, 40), (1, 8), (2, 49), (3, 49);
INSERT INTO orders (id, customer_name, customer_email, shipping_address, status, total_amount) VALUES
  (1, 'Legacy A', 'a@example.com', 'A St', 'CREATED', 39.98), (2, 'Legacy B', 'b@example.com', 'B St', 'PAID', 49.50),
  (3, 'Legacy C', 'c@example.com', 'C St', 'SHIPPED', 129.00), (4, 'Legacy D', 'd@example.com', 'D St', 'CANCELLED', 19.99);
INSERT INTO order_items (order_id, product_id, quantity, price) VALUES
  (1, 1, 2, 19.99), (2, 2, 1, 49.50), (3, 3, 1, 129.00), (4, 1, 1, 19.99);
