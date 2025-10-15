INSERT INTO products (sku, name, price, safety_stock) VALUES
('SKU-1001','Test Widget',19.99,5),
('SKU-1002','Pro Gadget',49.50,3),
('SKU-2001','Mega Tool',129.00,2)
ON DUPLICATE KEY UPDATE name=VALUES(name), price=VALUES(price), safety_stock=VALUES(safety_stock);

INSERT INTO inventory (product_id, stock)
SELECT p.id, 50 FROM products p
ON DUPLICATE KEY UPDATE stock=VALUES(stock);