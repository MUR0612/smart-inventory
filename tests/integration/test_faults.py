"""Fault injection (CACHE-01, OPS-01, EVENT-02, SEC-04). Stops and starts containers.

Only runs with RUN_FAULT_TESTS=1 and COMPOSE_PROJECT / COMPOSE_ENV_FILE set,
against a disposable stack (scripts/test-compose.sh does this).
"""
import json
import os
import subprocess
import time

import pytest

from conftest import ORDER_FIELDS, stock_of

pytestmark = pytest.mark.skipif(os.getenv("RUN_FAULT_TESTS") != "1", reason="set RUN_FAULT_TESTS=1")


def compose(*args) -> str:
    cmd = ["docker", "compose", "-p", os.environ["COMPOSE_PROJECT"], "--env-file", os.environ["COMPOSE_ENV_FILE"], *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8").stdout


def wait_for(predicate, timeout=90, interval=1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def restart_count(service: str) -> int:
    container = compose("ps", "-q", service).strip()
    out = subprocess.run(["docker", "inspect", "-f", "{{.RestartCount}}", container],
                         check=True, capture_output=True, text=True, encoding="utf-8").stdout
    return int(out.strip())


def test_only_the_gateway_is_published():
    published = {}
    for line in compose("ps", "--format", "json").splitlines():
        svc = json.loads(line)
        published[svc["Service"]] = [p for p in svc.get("Publishers") or [] if p.get("PublishedPort")]
    assert published["gateway"], "gateway must be reachable"
    assert all(not ports for name, ports in published.items() if name != "gateway"), published


def test_redis_outage_degrades_but_does_not_break(http, staff, product):
    p = product(stock=5)
    compose("stop", "redis")
    try:
        r = http.get("/api/inventory/products", headers=staff)
        assert r.status_code == 200 and any(x["id"] == p["id"] for x in r.json())
        assert http.get("/api/inventory/readyz").json()["status"] == "degraded"
        assert http.post(f"/api/inventory/stock/{p['id']}/adjust", headers=staff,
                         json={"adjustment": -1}).status_code == 200  # stock writes never need Redis
        order = http.post("/api/orders", headers=staff, json={"items": [{"product_id": p["id"], "qty": 1}],
                                                             **ORDER_FIELDS})
        assert order.status_code == 201  # order correctness does not depend on Pub/Sub
    finally:
        compose("start", "redis")
    # Cache comes back, and the subscriber reconnects by itself.
    assert wait_for(lambda: http.get("/api/inventory/readyz").json()["status"] == "ok")
    assert wait_for(lambda: http.get("/api/orders/events/recent", headers=staff).json()["connected"], timeout=60)
    http.post(f"/api/inventory/stock/{p['id']}/adjust", headers=staff, json={"adjustment": 1})
    assert wait_for(lambda: any(e.get("product_id") == p["id"] and e.get("source") == "manual_adjust"
                                for e in http.get("/api/orders/events/recent", headers=staff).json()["events"]),
                    timeout=15)


def test_database_outage_fails_readiness_without_restart_storm(http):
    before = {s: restart_count(s) for s in ("inventory-service", "order-service")}
    compose("stop", "mysql")
    try:
        assert wait_for(lambda: http.get("/api/inventory/readyz").status_code == 503, timeout=30)
        assert http.get("/api/orders/readyz").status_code == 503
        assert http.get("/api/inventory/livez").status_code == 200
        time.sleep(20)
        assert {s: restart_count(s) for s in before} == before
    finally:
        compose("start", "mysql")
    assert wait_for(lambda: http.get("/api/inventory/readyz").status_code == 200, timeout=120)
    assert wait_for(lambda: http.get("/api/orders/readyz").status_code == 200, timeout=60)


def test_inventory_outage_creates_no_order_and_moves_no_stock(http, staff, product):
    p = product(stock=5)
    before = http.get("/api/orders/stats", headers=staff).json()["total_orders"]
    compose("stop", "inventory-service")
    try:
        r = http.post("/api/orders", headers=staff, json={"items": [{"product_id": p["id"], "qty": 2}],
                                                         **ORDER_FIELDS})
        assert r.status_code == 503
    finally:
        compose("start", "inventory-service")
    assert wait_for(lambda: http.get("/api/inventory/readyz").status_code == 200, timeout=60)
    assert stock_of(http, staff, p["id"]) == 5
    assert http.get("/api/orders/stats", headers=staff).json()["total_orders"] == before
