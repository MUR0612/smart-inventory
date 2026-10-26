import time

import jwt
import pytest


def stock_of(client, staff, product_id):
    return client.get(f"/api/inventory/stock/{product_id}", headers=staff).json()["current_stock"]


# ---------------------------------------------------------------- SEC-02 access control

def test_anonymous_requests_are_rejected(client):
    assert client.get("/api/inventory/products").status_code == 401
    assert client.post("/api/inventory/products", json={}).status_code == 401
    assert client.post("/api/inventory/stock/1/adjust", json={"adjustment": 1}).status_code == 401


def test_viewer_can_read_but_not_write(client, viewer, make_product):
    p = make_product()
    assert client.get("/api/inventory/products", headers=viewer).status_code == 200
    assert client.post(f"/api/inventory/stock/{p['id']}/adjust", headers=viewer,
                       json={"adjustment": -1}).status_code == 403
    assert client.delete(f"/api/inventory/products/{p['id']}", headers=viewer).status_code == 403


def test_bad_login_and_tampered_or_expired_tokens(client, staff):
    assert client.post("/api/auth/login", json={"username": "alice", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "nobody", "password": "x"}).status_code == 401
    token = staff["Authorization"].split()[1]
    forged = jwt.encode({**jwt.decode(token, options={"verify_signature": False}), "role": "staff"},
                        "another-secret-another-secret-123456", algorithm="HS256")
    assert client.get("/api/inventory/products", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    claims = jwt.decode(token, options={"verify_signature": False})
    from smart_shared import auth
    expired = jwt.encode({**claims, "exp": int(time.time()) - 5}, auth.settings().secret, algorithm="HS256")
    assert client.get("/api/inventory/products", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_service_token_scope(client, staff, service, make_product):
    p = make_product()
    # The service token may read and reserve, but not use staff-only endpoints.
    assert client.get(f"/api/inventory/products/{p['id']}", headers=service).status_code == 200
    assert client.post(f"/api/inventory/stock/{p['id']}/adjust", headers=service,
                       json={"adjustment": 1}).status_code == 403
    assert client.get("/api/inventory/products", headers={"X-Service-Token": "wrong"}).status_code == 401
    # Users (even staff) cannot call the reservation API directly.
    assert client.post("/api/inventory/reservations", headers=staff,
                       json={"reservation_id": "abcdefgh", "items": [{"product_id": p["id"], "qty": 1}]}
                       ).status_code == 403


# ---------------------------------------------------------------- API-01 validation

@pytest.mark.parametrize("override", [
    {"price": "-1"}, {"price": "NaN"}, {"price": "Infinity"}, {"price": "1.999"}, {"price": "123456789.00"},
    {"stock": -1}, {"safety_stock": -5}, {"name": "x" * 256}, {"name": ""}, {"sku": "has space"},
    {"sku": "x" * 65}, {"unexpected": 1},
])
def test_invalid_product_payloads(client, staff, override):
    body = {"sku": "SKU-VALID", "name": "Widget", "price": "1.00", "stock": 1, "safety_stock": 0, **override}
    assert client.post("/api/inventory/products", headers=staff, json=body).status_code == 422


def test_nan_json_literal_is_rejected(client, staff):
    raw = '{"sku": "SKU-NAN", "name": "n", "price": NaN, "stock": 0}'
    r = client.post("/api/inventory/products", headers={**staff, "Content-Type": "application/json"}, content=raw)
    assert r.status_code == 422


def test_duplicate_sku_is_409(client, staff, make_product):
    p = make_product()
    r = client.post("/api/inventory/products", headers=staff,
                    json={"sku": p["sku"], "name": "dup", "price": "1.00"})
    assert r.status_code == 409


def test_prices_are_exact_decimals(client, staff, make_product):
    make_product(price="0.10", stock=1, safety_stock=0)
    make_product(price="0.20", stock=1, safety_stock=0)
    stats = client.get("/api/inventory/stats", headers=staff).json()
    assert stats["total_value"] == "0.30"  # 0.1 + 0.2 as floats would be 0.30000000000000004


def test_adjust_validation(client, staff, make_product):
    p = make_product(stock=5)
    url = f"/api/inventory/stock/{p['id']}/adjust"
    assert client.post(url, headers=staff, json={"adjustment": 0}).status_code == 422
    assert client.post(url, headers=staff, json={"adjustment": 10**7}).status_code == 422
    assert client.post(url, headers=staff, json={"adjustment": -2}).status_code == 200  # negative is allowed
    r = client.post(url, headers=staff, json={"adjustment": -4})
    assert r.status_code == 409 and stock_of(client, staff, p["id"]) == 3


def test_set_stock_with_expected_value(client, staff, make_product):
    p = make_product(stock=5)
    url = f"/api/inventory/stock/{p['id']}/set"
    assert client.post(url, headers=staff, json={"stock": 9, "expected_stock": 4}).status_code == 409
    assert client.post(url, headers=staff, json={"stock": 9, "expected_stock": 5}).status_code == 200
    assert stock_of(client, staff, p["id"]) == 9


# ---------------------------------------------------------------- DATA-02 reservations

def reserve(client, service, rid, items):
    return client.post("/api/inventory/reservations", headers=service,
                       json={"reservation_id": rid, "items": items})


def test_reservation_is_all_or_nothing(client, staff, service, make_product):
    a, b = make_product(stock=10), make_product(stock=1)
    r = reserve(client, service, "res-all-or-nothing", [{"product_id": a["id"], "qty": 3},
                                                        {"product_id": b["id"], "qty": 2}])
    assert r.status_code == 409
    assert r.json()["detail"]["items"] == [{"product_id": b["id"], "requested": 2, "available": 1}]
    assert stock_of(client, staff, a["id"]) == 10  # first item not deducted


def test_reservation_replay_does_not_deduct_twice(client, staff, service, make_product):
    p = make_product(stock=10)
    items = [{"product_id": p["id"], "qty": 4}]
    assert reserve(client, service, "res-replay-001", items).status_code == 201
    replay = reserve(client, service, "res-replay-001", items)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert stock_of(client, staff, p["id"]) == 6
    assert reserve(client, service, "res-replay-001", [{"product_id": p["id"], "qty": 5}]).status_code == 409


def test_release_returns_stock_exactly_once(client, staff, service, make_product):
    p = make_product(stock=10)
    reserve(client, service, "res-release-1", [{"product_id": p["id"], "qty": 4}])
    first = client.post("/api/inventory/reservations/res-release-1/release", headers=service).json()
    second = client.post("/api/inventory/reservations/res-release-1/release", headers=service).json()
    assert first["released_now"] is True and second["released_now"] is False
    assert stock_of(client, staff, p["id"]) == 10


def test_release_before_reserve_blocks_late_reserve(client, staff, service, make_product):
    """Timeout case: order-service releases an id whose reserve request is still in flight."""
    p = make_product(stock=10)
    r = client.post("/api/inventory/reservations/res-late-arrival/release", headers=service)
    assert r.status_code == 200 and r.json()["released_now"] is False
    late = reserve(client, service, "res-late-arrival", [{"product_id": p["id"], "qty": 4}])
    assert late.status_code == 409
    assert stock_of(client, staff, p["id"]) == 10


def test_commit_blocks_release(client, staff, service, make_product):
    p = make_product(stock=10)
    reserve(client, service, "res-commit-01", [{"product_id": p["id"], "qty": 4}])
    assert client.post("/api/inventory/reservations/res-commit-01/commit", headers=service).status_code == 200
    assert client.post("/api/inventory/reservations/res-commit-01/commit", headers=service).status_code == 200
    assert client.post("/api/inventory/reservations/res-commit-01/release", headers=service).status_code == 409
    assert stock_of(client, staff, p["id"]) == 6


def test_reservation_input_rules(client, service, make_product):
    p = make_product()
    dup = [{"product_id": p["id"], "qty": 1}, {"product_id": p["id"], "qty": 1}]
    assert reserve(client, service, "res-dup-items", dup).status_code == 422
    assert reserve(client, service, "bad id!", [{"product_id": p["id"], "qty": 1}]).status_code == 422
    assert reserve(client, service, "res-unknown-p", [{"product_id": 999999, "qty": 1}]).status_code == 404


# ---------------------------------------------------------------- CACHE-01

def test_cache_hit_and_invalidation(client, staff, make_product):
    p = make_product(name="Before")
    first = client.get("/api/inventory/products", headers=staff)
    assert first.headers["X-Cache"] == "miss"
    assert client.get("/api/inventory/products", headers=staff).headers["X-Cache"] == "hit"
    client.put(f"/api/inventory/products/{p['id']}", headers=staff, json={"name": "After"})
    after = client.get("/api/inventory/products", headers=staff)
    assert after.headers["X-Cache"] == "miss" and after.json()[0]["name"] == "After"


def test_redis_down_falls_back_to_database(client, staff, make_product, fake_redis):
    make_product()
    fake_redis.fail = True
    r = client.get("/api/inventory/products", headers=staff)
    assert r.status_code == 200 and len(r.json()) == 1 and r.headers["X-Cache"] == "bypass"
    ready = client.get("/api/inventory/readyz")
    assert ready.status_code == 200 and ready.json()["status"] == "degraded"


def test_redis_recovers_after_breaker(client, staff, make_product, fake_redis):
    from app import redis_client
    make_product()
    fake_redis.fail = True
    client.get("/api/inventory/products", headers=staff)
    fake_redis.fail = False
    redis_client._open_until = 0.0  # breaker window elapsed
    assert client.get("/api/inventory/products", headers=staff).headers["X-Cache"] == "miss"
    assert client.get("/api/inventory/products", headers=staff).headers["X-Cache"] == "hit"


def test_corrupt_cache_entry_is_not_an_empty_list(client, staff, make_product, fake_redis):
    make_product()
    client.get("/api/inventory/products", headers=staff)
    key = next(k for k in fake_redis.store if k.startswith("products:list:v2:"))
    fake_redis.store[key] = "{not json"
    r = client.get("/api/inventory/products", headers=staff)
    assert r.status_code == 200 and len(r.json()) == 1


# ---------------------------------------------------------------- EVENT-01

def test_adjust_publishes_complete_stock_event(client, staff, make_product, fake_redis):
    p = make_product(stock=5, safety_stock=2)
    client.post(f"/api/inventory/stock/{p['id']}/adjust", headers=staff, json={"adjustment": -4})
    channels = [c for c, _ in fake_redis.published]
    assert "stock_changes" in channels and "low_stock_alerts" in channels
    event = next(e for c, e in fake_redis.published if c == "stock_changes")
    assert (event["old_stock"], event["new_stock"], event["adjustment"]) == (5, 1, -4)
    assert event["timestamp"].endswith("+00:00")


def test_publish_failure_is_logged_not_fatal(client, staff, make_product, fake_redis, caplog):
    p = make_product(stock=5)
    fake_redis.fail = True
    r = client.post(f"/api/inventory/stock/{p['id']}/adjust", headers=staff, json={"adjustment": -1})
    assert r.status_code == 200
    assert any("event not published" in rec.getMessage() for rec in caplog.records)


# ---------------------------------------------------------------- OPS-01

def test_liveness_does_not_depend_on_database(client, monkeypatch):
    from app.routers import health

    class Broken:
        def connect(self):
            raise RuntimeError("db down")
    monkeypatch.setattr(health, "engine", Broken())
    assert client.get("/api/inventory/livez").status_code == 200
    r = client.get("/api/inventory/readyz")
    assert r.status_code == 503 and r.json()["checks"]["database"] == "down"


def test_unhandled_errors_do_not_leak_details(client, staff, monkeypatch):
    from app.routers import products

    def boom(*args, **kwargs):
        raise RuntimeError("mysql+pymysql://user:secret@internal-host/db")
    monkeypatch.setattr(products, "_joined", boom)
    r = client.get("/api/inventory/products/1", headers=staff)
    assert r.status_code == 500
    assert "secret" not in r.text and "internal-host" not in r.text
    assert r.json()["request_id"]


def test_missing_required_config_names_variable(monkeypatch):
    from smart_shared import auth
    from smart_shared.config import ConfigError
    monkeypatch.delenv("AUTH_SECRET")
    auth.reset_settings_for_tests()
    with pytest.raises(ConfigError, match="AUTH_SECRET"):
        auth.settings()
    monkeypatch.setenv("AUTH_SECRET", "CHANGE_ME" + "x" * 40)
    with pytest.raises(ConfigError, match="placeholder"):
        auth.settings()
    auth.reset_settings_for_tests()
