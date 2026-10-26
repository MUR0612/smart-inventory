import asyncio

import pytest

ORDER = {"customer_name": "Ada", "customer_email": "ada@example.com", "shipping_address": "1 Test St"}


def create(client, staff, items, idem=None, **extra):
    headers = {**staff, **({"Idempotency-Key": idem} if idem else {})}
    return client.post("/api/orders", headers=headers, json={"items": items, **ORDER, **extra})


def order_row(db, order_id):
    from app.models import Order
    db.expire_all()
    return db.get(Order, order_id)


def count_orders(db):
    from app.models import Order
    db.expire_all()
    return db.query(Order).count()


# ---------------------------------------------------------------- happy path + API-01

def test_create_merges_duplicates_and_uses_exact_decimals(client, staff, inventory):
    r = create(client, staff, [{"product_id": 2, "qty": 1}, {"product_id": 2, "qty": 2}, {"product_id": 1, "qty": 1}])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "CREATED" and body["inventory_sync"] == "RESERVED"
    assert body["total"] == "20.29"  # 19.99 + 3 * 0.10, no float drift
    assert sorted((i["product_id"], i["qty"]) for i in body["items"]) == [(1, 1), (2, 3)]
    assert inventory.stock == {1: 9, 2: 2}
    assert body["created_at"].endswith(("Z", "+00:00"))  # explicit UTC


@pytest.mark.parametrize("payload", [
    {"items": []}, {"items": [{"product_id": 1, "qty": 0}]}, {"items": [{"product_id": 1, "qty": 10001}]},
    {"items": [{"product_id": 1, "qty": 1}] * 51}, {"items": [{"product_id": 1, "qty": 1}], "customer_email": "x"},
    {"items": [{"product_id": 1, "qty": 1}], "customer_name": "x" * 256},
])
def test_invalid_orders_rejected(client, staff, payload):
    assert client.post("/api/orders", headers=staff, json=payload).status_code == 422


def test_merged_quantity_limit(client, staff):
    r = create(client, staff, [{"product_id": 1, "qty": 6000}, {"product_id": 1, "qty": 6000}])
    assert r.status_code == 422


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "skip=-1", "status=BOGUS"])
def test_list_query_bounds(client, staff, query):
    assert client.get(f"/api/orders?{query}", headers=staff).status_code == 422


# ---------------------------------------------------------------- SEC-02

def test_order_access_control(client, staff, viewer):
    assert client.get("/api/orders").status_code == 401
    assert client.get("/api/orders/1").status_code == 401
    assert client.get("/api/orders", headers=viewer).status_code == 200
    assert create(client, viewer, [{"product_id": 1, "qty": 1}]).status_code == 403
    order_id = create(client, staff, [{"product_id": 1, "qty": 1}]).json()["id"]
    assert client.post(f"/api/orders/{order_id}/cancel", headers=viewer).status_code == 403
    assert client.delete(f"/api/orders/{order_id}", headers=viewer).status_code == 403
    # The service token is for inventory-service only; it never opens order endpoints.
    assert client.get("/api/orders", headers={"X-Service-Token": "unit-test-service-token-0123456789"}).status_code == 403


# ---------------------------------------------------------------- DATA-02 failure cases

def test_second_item_insufficient_no_partial_deduction(client, staff, inventory, db):
    r = create(client, staff, [{"product_id": 1, "qty": 2}, {"product_id": 2, "qty": 99}])
    assert r.status_code == 409
    assert inventory.stock == {1: 10, 2: 5}
    assert count_orders(db) == 0  # the draft order is discarded


def test_unknown_product_is_404(client, staff, inventory, db):
    assert create(client, staff, [{"product_id": 42, "qty": 1}]).status_code == 404
    assert count_orders(db) == 0 and not inventory.calls


def test_reserve_timeout_before_apply(client, staff, inventory, db):
    inventory.fail("reserve", "before")
    r = create(client, staff, [{"product_id": 1, "qty": 3}])
    assert r.status_code == 503
    order = order_row(db, r.json()["detail"]["order_id"])
    assert (order.status, order.inventory_sync) == ("FAILED", "RELEASED")
    assert inventory.stock[1] == 10
    assert inventory.reservations[order.reservation_id]["status"] == "RELEASED"  # tombstone


def test_reserve_timeout_after_apply_is_compensated(client, staff, inventory, db):
    inventory.fail("reserve", "after")  # applied, but the response was lost
    r = create(client, staff, [{"product_id": 1, "qty": 3}])
    assert r.status_code == 503
    assert inventory.stock[1] == 10  # released exactly once
    assert order_row(db, r.json()["detail"]["order_id"]).status == "FAILED"


def test_unknown_outcome_and_failed_release_is_recovered_later(client, staff, inventory, db):
    from app.services import order_workflow as wf
    inventory.fail("reserve", "after")
    inventory.fail("release", "before")
    r = create(client, staff, [{"product_id": 1, "qty": 3}])
    order_id = r.json()["detail"]["order_id"]
    order = order_row(db, order_id)
    assert (order.status, order.inventory_sync) == ("PENDING", "RESERVE_PENDING")
    assert order.sync_error and inventory.stock[1] == 7

    result = asyncio.run(wf.reconcile_once(db, inventory, reserve_grace_seconds=0))
    assert result["completed"] == 1
    order = order_row(db, order_id)
    assert (order.status, order.inventory_sync) == ("FAILED", "RELEASED")
    assert inventory.stock[1] == 10
    asyncio.run(wf.reconcile_once(db, inventory, reserve_grace_seconds=0))
    assert inventory.stock[1] == 10  # a second pass changes nothing


def test_db_failure_after_reserve_then_retry_with_same_key(client, staff, inventory, db, monkeypatch):
    from app.services import order_workflow as wf
    real_cas, calls = wf._cas, {"n": 0}

    def flaky_cas(db_, order_id, expected, **values):
        if values.get("status") == "CREATED" and calls["n"] == 0:
            calls["n"] += 1
            raise RuntimeError("database went away")
        return real_cas(db_, order_id, expected, **values)
    monkeypatch.setattr(wf, "_cas", flaky_cas)

    first = create(client, staff, [{"product_id": 1, "qty": 4}], idem="key-db-failure-1")
    assert first.status_code == 500 and "database" not in first.text
    assert inventory.stock[1] == 6
    retry = create(client, staff, [{"product_id": 1, "qty": 4}], idem="key-db-failure-1")
    assert retry.status_code == 201 and retry.json()["status"] == "CREATED"
    assert inventory.stock[1] == 6  # replayed reservation, not a second deduction
    assert count_orders(db) == 1


def test_response_build_failure_never_releases_stock(client, staff, inventory, db, monkeypatch):
    from app.routers import orders
    real = orders.order_out
    state = {"failed": False}

    def flaky(db_, order_id):
        if not state["failed"]:
            state["failed"] = True
            raise RuntimeError("serialisation bug")
        return real(db_, order_id)
    monkeypatch.setattr(orders, "order_out", flaky)

    assert create(client, staff, [{"product_id": 1, "qty": 2}], idem="key-response-fail").status_code == 500
    assert inventory.stock[1] == 8
    assert not [c for c in inventory.calls if c[0] == "release"]
    replay = create(client, staff, [{"product_id": 1, "qty": 2}], idem="key-response-fail")
    assert replay.status_code == 200 and replay.headers["Idempotent-Replayed"] == "true"
    assert inventory.stock[1] == 8 and count_orders(db) == 1


def test_same_request_resent(client, staff, inventory, db):
    a = create(client, staff, [{"product_id": 1, "qty": 1}], idem="key-resend-0001")
    b = create(client, staff, [{"product_id": 1, "qty": 1}], idem="key-resend-0001")
    assert (a.status_code, b.status_code) == (201, 200) and a.json()["id"] == b.json()["id"]
    assert inventory.stock[1] == 9
    different = create(client, staff, [{"product_id": 1, "qty": 2}], idem="key-resend-0001")
    assert different.status_code == 422


def test_failed_attempt_requires_new_key(client, staff, inventory):
    inventory.fail("reserve", "before")
    assert create(client, staff, [{"product_id": 1, "qty": 1}], idem="key-failed-0001").status_code == 503
    assert create(client, staff, [{"product_id": 1, "qty": 1}], idem="key-failed-0001").status_code == 409
    assert create(client, staff, [{"product_id": 1, "qty": 1}], idem="key-failed-0002").status_code == 201


# ---------------------------------------------------------------- DATA-03 workflow

def status(client, staff, order_id, target):
    return client.patch(f"/api/orders/{order_id}/status", headers=staff, json={"status": target})


def test_cancel_returns_stock_once(client, staff, inventory):
    order_id = create(client, staff, [{"product_id": 1, "qty": 4}]).json()["id"]
    first = client.post(f"/api/orders/{order_id}/cancel", headers=staff)
    assert first.status_code == 200 and first.json()["inventory_sync"] == "RELEASED"
    assert client.post(f"/api/orders/{order_id}/cancel", headers=staff).status_code == 409
    assert status(client, staff, order_id, "CANCELLED").status_code == 409
    assert inventory.stock[1] == 10


def test_patch_cancel_equals_cancel_endpoint(client, staff, inventory):
    a = create(client, staff, [{"product_id": 1, "qty": 2}]).json()["id"]
    b = create(client, staff, [{"product_id": 1, "qty": 2}]).json()["id"]
    via_patch = status(client, staff, a, "CANCELLED").json()
    via_cancel = client.post(f"/api/orders/{b}/cancel", headers=staff).json()
    keys = ("status", "inventory_sync", "valid_transitions")
    assert [via_patch[k] for k in keys] == [via_cancel[k] for k in keys]
    assert inventory.stock[1] == 10


def test_paid_order_must_be_refunded_not_cancelled(client, staff, inventory):
    order_id = create(client, staff, [{"product_id": 1, "qty": 3}]).json()["id"]
    status(client, staff, order_id, "PAID")
    r = client.post(f"/api/orders/{order_id}/cancel", headers=staff)
    assert r.status_code == 409 and "refund" in r.json()["detail"]
    assert inventory.stock[1] == 7  # illegal transition has no side effect
    refunded = status(client, staff, order_id, "REFUNDED").json()
    assert refunded["status"] == "REFUNDED" and inventory.stock[1] == 10


def test_refund_after_shipping_does_not_restock(client, staff, inventory):
    order_id = create(client, staff, [{"product_id": 1, "qty": 3}]).json()["id"]
    status(client, staff, order_id, "PAID")
    shipped = status(client, staff, order_id, "SHIPPED").json()
    assert shipped["inventory_sync"] == "COMMITTED"
    assert status(client, staff, order_id, "REFUNDED").json()["status"] == "REFUNDED"
    assert inventory.stock[1] == 7


def test_illegal_transition_has_no_side_effect(client, staff, inventory):
    order_id = create(client, staff, [{"product_id": 1, "qty": 3}]).json()["id"]
    inventory.calls.clear()
    assert status(client, staff, order_id, "SHIPPED").status_code == 409
    assert status(client, staff, order_id, "BOGUS").status_code == 422
    assert not inventory.calls


def test_release_failure_is_retried_by_reconcile(client, staff, inventory, db):
    from app.services import order_workflow as wf
    order_id = create(client, staff, [{"product_id": 1, "qty": 4}]).json()["id"]
    inventory.fail("release", "after")  # applied, response lost
    r = client.post(f"/api/orders/{order_id}/cancel", headers=staff).json()
    assert r["status"] == "CANCELLED" and r["inventory_sync"] == "RELEASE_PENDING" and r["sync_error"]
    assert inventory.stock[1] == 10
    asyncio.run(wf.reconcile_once(db, inventory))
    assert order_row(db, order_id).inventory_sync == "RELEASED"
    assert inventory.stock[1] == 10  # idempotent release: still returned only once


def test_delete_only_closed_orders(client, staff, inventory):
    order_id = create(client, staff, [{"product_id": 1, "qty": 4}]).json()["id"]
    assert client.delete(f"/api/orders/{order_id}", headers=staff).status_code == 409
    inventory.fail("release", "before")
    client.post(f"/api/orders/{order_id}/cancel", headers=staff)
    assert client.delete(f"/api/orders/{order_id}", headers=staff).status_code == 409  # release pending
    client.post("/api/orders/admin/reconcile", headers=staff)
    assert client.delete(f"/api/orders/{order_id}", headers=staff).status_code == 200
    assert inventory.stock[1] == 10


# ---------------------------------------------------------------- UI-01 totals

def test_totals_cover_more_than_one_page(client, staff, inventory):
    inventory.stock[2] = 1000
    for _ in range(120):
        assert create(client, staff, [{"product_id": 2, "qty": 1}]).status_code == 201
    page = client.get("/api/orders?limit=50", headers=staff).json()
    assert page["total"] == 120 and len(page["items"]) == 50
    stats = client.get("/api/orders/stats", headers=staff).json()
    assert stats["total_orders"] == 120 and stats["by_status"] == {"CREATED": 120}
    assert stats["revenue"] == "0.00"  # unpaid orders are not revenue
