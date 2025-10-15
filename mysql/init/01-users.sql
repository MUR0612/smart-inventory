-- Create database user and grant permissions
CREATE USER IF NOT EXISTS 'inventory_user'@'%' IDENTIFIED BY 'inventory_password';
CREATE USER IF NOT EXISTS 'inventory_user'@'localhost' IDENTIFIED BY 'inventory_password';
GRANT ALL PRIVILEGES ON smart_inventory.* TO 'inventory_user'@'%';
GRANT ALL PRIVILEGES ON smart_inventory.* TO 'inventory_user'@'localhost';
FLUSH PRIVILEGES;
