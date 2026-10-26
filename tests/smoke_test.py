"""End-to-end smoke test through the gateway (Python standard library only).

    python tests/smoke_test.py --base-url http://127.0.0.1:8080 --credentials-file .env.credentials

Works the same from PowerShell, bash or Cloud Shell. Every step asserts the
status code and content; the script exits non-zero on the first failure.
It only creates new records (SKU prefix SMOKE-), it never edits existing ones.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid


class Api:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token = None

    def call(self, method: str, path: str, body=None, headers=None, expect=200):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as err:
            status, raw = err.code, err.read()
        expected = expect if isinstance(expect, tuple) else (expect,)
        if status not in expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {status}: {raw[:300]!r}")
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return raw.decode(errors="replace")


def check(label: str, condition: bool, detail=""):
    if not condition:
        raise AssertionError(f"{label} {detail}")
    print(f"PASS  {label}")


def run(api: Api, user: str, password: str):
    check("frontend served by gateway", "Smart Inventory" in api.call("GET", "/"))
    for svc in ("inventory", "orders"):
        check(f"{svc} ready", api.call("GET", f"/api/{svc}/readyz")["checks"]["database"] == "up")
    api.call("GET", "/api/orders", expect=401)
    print("PASS  anonymous access rejected")

    api.token = api.call("POST", "/api/auth/login", {"username": user, "password": password})["access_token"]
    sku = f"SMOKE-{int(time.time())}-{uuid.uuid4().hex[:4]}"
    product = api.call("POST", "/api/inventory/products", {"sku": sku, "name": "Smoke widget", "price": "4.20",
                                                           "stock": 10, "safety_stock": 2}, expect=201)
    pid = product["id"]
    stock = lambda: api.call("GET", f"/api/inventory/stock/{pid}")["current_stock"]  # noqa: E731
    check("product created", product["price"] == "4.20" and product["stock"] == 10)

    check("stock adjusted", api.call("POST", f"/api/inventory/stock/{pid}/adjust", {"adjustment": -3})
          ["current_stock"] == 7)
    api.call("POST", f"/api/inventory/stock/{pid}/adjust", {"adjustment": -100}, expect=409)
    check("overselling rejected", stock() == 7)

    key = uuid.uuid4().hex
    order_body = {"items": [{"product_id": pid, "qty": 1}, {"product_id": pid, "qty": 1}],
                  "customer_name": "Smoke Test", "customer_email": "smoke@example.com", "shipping_address": "1 Smoke St"}
    order = api.call("POST", "/api/orders", order_body, headers={"Idempotency-Key": key}, expect=201)
    check("order created and stock reserved", order["status"] == "CREATED" and order["total"] == "8.40" and stock() == 5)
    again = api.call("POST", "/api/orders", order_body, headers={"Idempotency-Key": key}, expect=200)
    check("resend with same key is not double-booked", again["id"] == order["id"] and stock() == 5)

    oid = order["id"]
    check("paid", api.call("PATCH", f"/api/orders/{oid}/status", {"status": "PAID"})["status"] == "PAID")
    api.call("POST", f"/api/orders/{oid}/cancel", expect=409)
    print("PASS  paid order cannot be cancelled (refund instead)")
    shipped = api.call("PATCH", f"/api/orders/{oid}/status", {"status": "SHIPPED"})
    check("shipped commits reservation", shipped["inventory_sync"] == "COMMITTED" and stock() == 5)

    second = api.call("POST", "/api/orders", {**order_body, "items": [{"product_id": pid, "qty": 3}]}, expect=201)
    check("second order reserved", stock() == 2)
    cancelled = api.call("POST", f"/api/orders/{second['id']}/cancel")
    check("cancel returns stock", cancelled["inventory_sync"] == "RELEASED" and stock() == 5)
    api.call("POST", f"/api/orders/{second['id']}/cancel", expect=409)
    check("second cancel has no effect", stock() == 5)
    api.call("DELETE", f"/api/orders/{oid}", expect=409)
    api.call("DELETE", f"/api/orders/{second['id']}")
    print("PASS  only closed orders can be deleted")

    stats = api.call("GET", "/api/orders/stats")
    check("order stats available", stats["total_orders"] >= 1 and stats["scope"] == "all orders")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--credentials-file", help="file with STAFF_USER= and STAFF_PASSWORD= lines")
    parser.add_argument("--user")
    parser.add_argument("--password")
    args = parser.parse_args()
    user, password = args.user, args.password
    if args.credentials_file:
        values = dict(line.split("=", 1) for line in open(args.credentials_file, encoding="utf-8").read().split())
        user, password = user or values.get("STAFF_USER"), password or values.get("STAFF_PASSWORD")
    if not (user and password):
        sys.exit("provide --credentials-file or --user/--password for a staff account")
    try:
        run(Api(args.base_url), user, password)
    except (AssertionError, urllib.error.URLError, OSError) as exc:
        print(f"FAIL  {exc}")
        sys.exit(1)
    print("smoke test passed")


if __name__ == "__main__":
    main()
