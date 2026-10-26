"""DATA-01/02/03 and UI-01 against real MySQL row locking."""
import time
import uuid

import pytest

from conftest import ORDER_FIELDS as ORDER, parallel, stock_of, unique


@pytest.mark.parametrize("round_", range(5))
def test_concurrent_decrements_never_oversell(http, staff, product, round_):
    p = product(stock=1)
    results = parallel(20, lambda c, i: c.post(f"/api/inventory/stock/{p['id']}/adjust", headers=staff,
                                               json={"adjustment": -1}).status_code)
    assert results.count(200) == 1 and results.count(409) == 19, results
    assert stock_of(http, staff, p["id"]) == 0


def test_concurrent_increments_lose_no_update(http, staff, product):
    p = product(stock=0)
    results = parallel(25, lambda c, i: c.post(f"/api/inventory/stock/{p['id']}/adjust", headers=staff,
                                               json={"adjustment": 2}).status_code)
    assert results.count(200) == 25
    assert stock_of(http, staff, p["id"]) == 50


def test_concurrent_orders_reserve_exactly_available_stock(http, staff, product):
    p = product(stock=3)
    codes = parallel(15, lambda c, i: c.post("/api/orders", headers=staff,
                                             json={"items": [{"product_id": p["id"], "qty": 1}], **ORDER}).status_code)
    assert codes.count(201) == 3 and codes.count(409) == 12, codes
    assert stock_of(http, staff, p["id"]) == 0


def test_multi_item_order_is_all_or_nothing(http, staff, product):
    a, b = product(stock=10), product(stock=1)
    r = http.post("/api/orders", headers=staff,
                  json={"items": [{"product_id": a["id"], "qty": 2}, {"product_id": b["id"], "qty": 5}], **ORDER})
    assert r.status_code == 409
    assert stock_of(http, staff, a["id"]) == 10 and stock_of(http, staff, b["id"]) == 1


def test_same_idempotency_key_in_parallel_creates_one_order(http, staff, product):
    p = product(stock=10)
    key = uuid.uuid4().hex
    body = {"items": [{"product_id": p["id"], "qty": 2}], **ORDER}
    results = parallel(8, lambda c, i: c.post("/api/orders", headers={**staff, "Idempotency-Key": key}, json=body))
    codes = [r.status_code for r in results]
    assert set(codes) <= {200, 201} and codes.count(201) >= 1, codes
    assert len({r.json()["id"] for r in results}) == 1
    assert stock_of(http, staff, p["id"]) == 8


def test_parallel_cancels_return_stock_once(http, staff, product):
    p = product(stock=10)
    order = http.post("/api/orders", headers=staff, json={"items": [{"product_id": p["id"], "qty": 4}], **ORDER}).json()
    codes = parallel(10, lambda c, i: c.post(f"/api/orders/{order['id']}/cancel", headers=staff).status_code)
    assert codes.count(200) == 1 and codes.count(409) == 9, codes
    assert stock_of(http, staff, p["id"]) == 10


def test_order_lifecycle_and_stock_rules(http, staff, product):
    p = product(stock=10)
    create = lambda: http.post("/api/orders", headers=staff,  # noqa: E731
                               json={"items": [{"product_id": p["id"], "qty": 3}], **ORDER}).json()["id"]
    status = lambda oid, s: http.patch(f"/api/orders/{oid}/status", headers=staff, json={"status": s})  # noqa: E731

    shipped = create()
    assert status(shipped, "PAID").status_code == 200
    assert http.post(f"/api/orders/{shipped}/cancel", headers=staff).status_code == 409  # paid -> refund instead
    assert status(shipped, "SHIPPED").json()["inventory_sync"] == "COMMITTED"
    assert status(shipped, "REFUNDED").json()["status"] == "REFUNDED"
    assert stock_of(http, staff, p["id"]) == 7  # refund after shipping does not restock

    refunded_before_ship = create()
    status(refunded_before_ship, "PAID")
    assert status(refunded_before_ship, "REFUNDED").json()["inventory_sync"] == "RELEASED"
    assert stock_of(http, staff, p["id"]) == 7

    open_order = create()
    assert http.delete(f"/api/orders/{open_order}", headers=staff).status_code == 409
    assert status(open_order, "CANCELLED").status_code == 200
    assert http.delete(f"/api/orders/{open_order}", headers=staff).status_code == 200
    assert stock_of(http, staff, p["id"]) == 7


def test_product_with_orders_cannot_be_deleted(http, staff, product):
    p = product(stock=5)
    http.post("/api/orders", headers=staff, json={"items": [{"product_id": p["id"], "qty": 1}], **ORDER})
    assert http.delete(f"/api/inventory/products/{p['id']}", headers=staff).status_code == 409


def test_duplicate_sku_race_has_one_winner(http, staff):
    sku = unique()
    codes = parallel(10, lambda c, i: c.post("/api/inventory/products", headers=staff,
                                             json={"sku": sku, "name": "race", "price": "1.00"}).status_code)
    assert codes.count(201) == 1 and codes.count(409) == 9, codes


def test_totals_count_all_orders_not_one_page(http, staff, product):
    p = product(stock=500)
    before = http.get("/api/orders/stats", headers=staff).json()["total_orders"]
    for _ in range(105):
        assert http.post("/api/orders", headers=staff,
                         json={"items": [{"product_id": p["id"], "qty": 1}], **ORDER}).status_code == 201
    stats = http.get("/api/orders/stats", headers=staff).json()
    page = http.get("/api/orders?limit=50", headers=staff).json()
    assert stats["total_orders"] == before + 105 == page["total"]
    assert len(page["items"]) == 50


def test_stock_change_events_reach_the_subscriber(http, staff, product):
    p = product(stock=5, safety_stock=1)
    http.post(f"/api/inventory/stock/{p['id']}/adjust", headers=staff, json={"adjustment": -2})
    deadline = time.time() + 10
    while time.time() < deadline:
        events = http.get("/api/orders/events/recent", headers=staff).json()["events"]
        match = [e for e in events if e.get("product_id") == p["id"] and e["channel"] == "stock_changes"]
        if match:
            e = match[0]
            assert (e["old_stock"], e["new_stock"], e["adjustment"]) == (5, 3, -2) and e["timestamp"]
            return
        time.sleep(0.5)
    pytest.fail("stock_changes event not observed by order-service subscriber")
