"""Single source of truth for the MySQL schema (Compose and Kubernetes).

Run once per deployment (Compose ``migrate`` service / Kubernetes Job), never
from the app replicas, so several pods can start at the same time.

* Fresh database           -> creates the current schema.
* Legacy Compose schema    -> (mysql/init/*.sql, before 2026-10) adopted in place.
* Legacy Kubernetes schema -> (old k8s/mysql.yaml: quantity/total_amount/price)
                              converted in place.
* Every step checks the current state first, so re-running never repeats an
  ALTER and an interrupted run can simply be started again.
* Also (re)creates the least-privilege application account (DML only) and
  sets its password from DB_PASSWORD, which is how password rotation works.

Connects with MIGRATE_DB_USER / MIGRATE_DB_PASSWORD (an admin account).
"""
import os
import sys
import time

import pymysql

LOCK_NAME = "smart_inventory_schema_migrate"


def env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        sys.exit(f"migrate: missing required environment variable {name}")
    if "CHANGE_ME" in value:
        sys.exit(f"migrate: {name} still has the placeholder from .env.example")
    return value


def log(msg: str):
    print(f"migrate: {msg}", flush=True)


class Db:
    def __init__(self, conn, schema: str):
        self.conn, self.schema = conn, schema

    def run(self, sql: str, args=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()

    def scalar(self, sql: str, args=None):
        rows = self.run(sql, args)
        return rows[0][0] if rows else None

    def table_exists(self, table: str) -> bool:
        return bool(self.scalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                                (self.schema, table)))

    def column_exists(self, table: str, column: str) -> bool:
        return bool(self.scalar("SELECT COUNT(*) FROM information_schema.columns "
                                "WHERE table_schema=%s AND table_name=%s AND column_name=%s",
                                (self.schema, table, column)))

    def constraint_exists(self, table: str, name: str) -> bool:
        return bool(self.scalar("SELECT COUNT(*) FROM information_schema.table_constraints "
                                "WHERE table_schema=%s AND table_name=%s AND constraint_name=%s",
                                (self.schema, table, name)))

    def foreign_keys(self, table: str) -> list[str]:
        return [r[0] for r in self.run("SELECT constraint_name FROM information_schema.table_constraints "
                                       "WHERE table_schema=%s AND table_name=%s AND constraint_type='FOREIGN KEY'",
                                       (self.schema, table))]

    def add_column(self, table: str, column: str, definition: str):
        if not self.column_exists(table, column):
            self.run(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}")
            log(f"added {table}.{column}")


# ----------------------------------------------------------------------------- 001

PRODUCTS = """CREATE TABLE IF NOT EXISTS products (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  sku VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  safety_stock INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_products_sku (sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""

INVENTORY = """CREATE TABLE IF NOT EXISTS {name} (
  product_id BIGINT NOT NULL PRIMARY KEY,
  stock INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""

ORDERS = """CREATE TABLE IF NOT EXISTS orders (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  status VARCHAR(32) NOT NULL,
  total DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  customer_name VARCHAR(255) NULL,
  customer_email VARCHAR(255) NULL,
  shipping_address TEXT NULL,
  notes TEXT NULL,
  updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  paid_at TIMESTAMP NULL,
  shipped_at TIMESTAMP NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""

ORDER_ITEMS = """CREATE TABLE IF NOT EXISTS order_items (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT NOT NULL,
  product_id BIGINT NOT NULL,
  qty INT NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""


def convert_legacy_kubernetes(db: Db):
    """Old k8s/mysql.yaml schema: inventory.quantity, orders.total_amount, order_items.quantity/price."""
    log("legacy Kubernetes schema detected; converting in place")
    for table in ("order_items", "inventory"):
        for fk in db.foreign_keys(table):
            db.run(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{fk}`")
    db.run(INVENTORY.format(name="inventory_new"))
    db.run("INSERT INTO inventory_new (product_id, stock, updated_at) "
           "SELECT product_id, SUM(quantity), MAX(updated_at) FROM inventory GROUP BY product_id")
    db.run("DROP TABLE inventory")
    db.run("RENAME TABLE inventory_new TO inventory")
    db.run("ALTER TABLE products MODIFY id BIGINT NOT NULL AUTO_INCREMENT, MODIFY sku VARCHAR(64) NOT NULL, "
           "MODIFY price DECIMAL(10,2) NOT NULL DEFAULT 0.00, MODIFY safety_stock INT NOT NULL DEFAULT 0")
    if db.column_exists("products", "updated_at"):
        db.run("ALTER TABLE products DROP COLUMN updated_at")
    db.run("ALTER TABLE orders MODIFY id BIGINT NOT NULL AUTO_INCREMENT, "
           "CHANGE total_amount total DECIMAL(10,2) NOT NULL DEFAULT 0.00, "
           "MODIFY status VARCHAR(32) NOT NULL, MODIFY customer_name VARCHAR(255) NULL, "
           "MODIFY customer_email VARCHAR(255) NULL, MODIFY shipping_address TEXT NULL")
    db.run("ALTER TABLE order_items MODIFY id BIGINT NOT NULL AUTO_INCREMENT, MODIFY order_id BIGINT NOT NULL, "
           "MODIFY product_id BIGINT NOT NULL, CHANGE quantity qty INT NOT NULL, "
           "CHANGE price unit_price DECIMAL(10,2) NOT NULL")


def m001_baseline(db: Db):
    if db.table_exists("inventory") and db.column_exists("inventory", "quantity"):
        convert_legacy_kubernetes(db)
    for ddl in (PRODUCTS, INVENTORY.format(name="inventory"), ORDERS, ORDER_ITEMS):
        db.run(ddl)
    # Legacy Compose databases may predate mysql/init/05-migrate-orders.sql.
    for column, definition in [("customer_name", "VARCHAR(255) NULL"), ("customer_email", "VARCHAR(255) NULL"),
                               ("shipping_address", "TEXT NULL"), ("notes", "TEXT NULL"),
                               ("updated_at", "TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                               ("paid_at", "TIMESTAMP NULL"), ("shipped_at", "TIMESTAMP NULL")]:
        db.add_column("orders", column, definition)
    if not db.column_exists("inventory", "updated_at"):
        db.add_column("inventory", "updated_at", "TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    for table, name, ddl in [
        ("inventory", "fk_inventory_product",
         "FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE"),
        ("order_items", "fk_items_order", "FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE"),
        ("order_items", "fk_items_product", "FOREIGN KEY (product_id) REFERENCES products(id)"),
    ]:
        if not db.constraint_exists(table, name):
            db.run(f"ALTER TABLE `{table}` ADD CONSTRAINT `{name}` {ddl}")


# ----------------------------------------------------------------------------- 002

def add_check(db: Db, table: str, name: str, condition: str):
    if db.constraint_exists(table, name):
        return
    bad = db.scalar(f"SELECT COUNT(*) FROM `{table}` WHERE NOT ({condition})")
    if bad:
        # Do not block the upgrade; the API validates new data. Fix and re-run to add it.
        log(f"WARNING: {bad} row(s) in {table} violate ({condition}); constraint {name} not added")
        return
    db.run(f"ALTER TABLE `{table}` ADD CONSTRAINT `{name}` CHECK ({condition})")


def m002_reservations(db: Db):
    """Idempotent reservations, order bookkeeping, item snapshots, CHECK constraints."""
    db.run("""CREATE TABLE IF NOT EXISTS stock_reservations (
      id VARCHAR(64) NOT NULL PRIMARY KEY,
      status VARCHAR(16) NOT NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    db.run("""CREATE TABLE IF NOT EXISTS stock_reservation_items (
      reservation_id VARCHAR(64) NOT NULL,
      product_id BIGINT NOT NULL,
      qty INT NOT NULL,
      PRIMARY KEY (reservation_id, product_id),
      CONSTRAINT fk_resitems_reservation FOREIGN KEY (reservation_id) REFERENCES stock_reservations(id) ON DELETE CASCADE,
      CONSTRAINT fk_resitems_product FOREIGN KEY (product_id) REFERENCES products(id),
      CONSTRAINT chk_resitems_qty CHECK (qty > 0)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    db.run("ALTER TABLE orders MODIFY total DECIMAL(12,2) NOT NULL DEFAULT 0.00, "
           "MODIFY status VARCHAR(32) NOT NULL DEFAULT 'PENDING'")
    db.add_column("orders", "idempotency_key", "VARCHAR(64) NULL")
    db.add_column("orders", "request_hash", "VARCHAR(64) NULL")
    db.add_column("orders", "reservation_id", "VARCHAR(64) NULL")
    db.add_column("orders", "inventory_sync", "VARCHAR(32) NOT NULL DEFAULT 'NONE'")
    db.add_column("orders", "sync_attempts", "INT NOT NULL DEFAULT 0")
    db.add_column("orders", "sync_error", "VARCHAR(255) NULL")
    for name, column in (("uq_orders_idempotency_key", "idempotency_key"), ("uq_orders_reservation_id", "reservation_id")):
        if not db.constraint_exists("orders", name):
            db.run(f"ALTER TABLE orders ADD CONSTRAINT {name} UNIQUE ({column})")
    db.add_column("order_items", "product_name", "VARCHAR(255) NULL")
    db.add_column("order_items", "product_sku", "VARCHAR(64) NULL")

    add_check(db, "products", "chk_products_price", "price >= 0")
    add_check(db, "products", "chk_products_safety_stock", "safety_stock >= 0")
    add_check(db, "inventory", "chk_inventory_stock", "stock >= 0")
    add_check(db, "order_items", "chk_items_qty", "qty > 0")

    backfill_legacy_orders(db)


def backfill_legacy_orders(db: Db):
    """Give pre-existing orders a reservation record so cancel/refund/ship work uniformly.

    Legacy code deducted stock directly at order creation, so CREATED/PAID orders
    still hold stock (RESERVED) and SHIPPED/REFUNDED consumed it (COMMITTED).
    For legacy CANCELLED orders it is unknown whether stock was returned (the old
    PATCH path did not return it), so they are flagged instead of guessed.
    """
    mapping = {"CREATED": "RESERVED", "PAID": "RESERVED", "SHIPPED": "COMMITTED", "REFUNDED": "COMMITTED"}
    rows = db.run("SELECT id, status FROM orders WHERE reservation_id IS NULL")
    for order_id, status in rows:
        if status in mapping:
            rid = f"legacy-order-{order_id}"
            db.run("INSERT IGNORE INTO stock_reservations (id, status) VALUES (%s, %s)", (rid, mapping[status]))
            db.run("INSERT IGNORE INTO stock_reservation_items (reservation_id, product_id, qty) "
                   "SELECT %s, product_id, SUM(qty) FROM order_items WHERE order_id=%s GROUP BY product_id",
                   (rid, order_id))
            db.run("UPDATE orders SET reservation_id=%s, inventory_sync=%s WHERE id=%s",
                   (rid, mapping[status], order_id))
        elif status == "CANCELLED":
            db.run("UPDATE orders SET sync_error=%s WHERE id=%s",
                   ("legacy cancel: stock return not verifiable", order_id))
    if rows:
        log(f"backfilled reservation bookkeeping for {len(rows)} legacy order(s)")


MIGRATIONS = [
    (1, "baseline schema (adopts legacy Compose / Kubernetes schemas)", m001_baseline),
    (2, "stock reservations, idempotency, item snapshots, CHECK constraints", m002_reservations),
]


# ----------------------------------------------------------------------------- runner

def ensure_app_user(db: Db, schema: str, user: str, password: str):
    """Least privilege: the services only need DML on their schema (no DDL, no GRANT)."""
    db.run("CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s", (user, password))
    db.run("ALTER USER %s@'%%' IDENTIFIED BY %s", (user, password))
    db.run("REVOKE ALL PRIVILEGES, GRANT OPTION FROM %s@'%%'", (user,))
    db.run(f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{schema}`.* TO %s@'%%'", (user,))
    log(f"application account '{user}' has DML-only access to {schema}")


def seed_demo_data(db: Db):
    if db.scalar("SELECT COUNT(*) FROM products"):
        return
    db.run("INSERT INTO products (sku, name, price, safety_stock) VALUES "
           "('SKU-1001','Test Widget',19.99,5), ('SKU-1002','Pro Gadget',49.50,3), ('SKU-2001','Mega Tool',129.00,2)")
    db.run("INSERT INTO inventory (product_id, stock) SELECT id, 50 FROM products")
    log("seeded 3 demo products")


def connect(retries: int = 60):
    for attempt in range(1, retries + 1):
        try:
            return pymysql.connect(host=env("DB_HOST"), port=int(env("DB_PORT", "3306")),
                                   user=env("MIGRATE_DB_USER", "root"), password=env("MIGRATE_DB_PASSWORD"),
                                   autocommit=True, connect_timeout=5, init_command="SET time_zone='+00:00'")
        except pymysql.err.OperationalError as exc:
            if attempt == retries:
                sys.exit(f"migrate: database not reachable after {retries} attempts (error {exc.args[0]})")
            time.sleep(2)


def main():
    schema = env("DB_NAME")
    if not schema.replace("_", "").isalnum():
        sys.exit("migrate: DB_NAME may contain only letters, digits and underscores")
    conn = connect()
    db = Db(conn, schema)
    db.run(f"CREATE DATABASE IF NOT EXISTS `{schema}` CHARACTER SET utf8mb4")
    conn.select_db(schema)
    if db.scalar("SELECT GET_LOCK(%s, 120)", (LOCK_NAME,)) != 1:
        sys.exit("migrate: another migration is running")
    try:
        db.run("CREATE TABLE IF NOT EXISTS schema_migrations (version INT PRIMARY KEY, description VARCHAR(255) "
               "NOT NULL, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        applied = {r[0] for r in db.run("SELECT version FROM schema_migrations")}
        for version, description, step in MIGRATIONS:
            if version in applied:
                continue
            log(f"applying {version}: {description}")
            step(db)
            db.run("INSERT INTO schema_migrations (version, description) VALUES (%s, %s)", (version, description))
        log(f"schema at version {MIGRATIONS[-1][0]}")
        ensure_app_user(db, schema, env("DB_USER"), env("DB_PASSWORD"))
        if os.getenv("SEED_DEMO_DATA", "false").lower() == "true":
            seed_demo_data(db)
    finally:
        db.run("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
        conn.close()


if __name__ == "__main__":
    main()
