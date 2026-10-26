"""Integration tests against a running stack, always through the gateway.

    BASE_URL=http://127.0.0.1:8080 CREDENTIALS_FILE=.env.credentials pytest tests/integration

Each test creates its own uniquely named data (prefix IT-) and never edits
existing records. Fault-injection tests (test_faults.py) also need
COMPOSE_PROJECT / COMPOSE_ENV_FILE and RUN_FAULT_TESTS=1, because they stop
and start containers. Use a disposable project: scripts/test-compose.sh.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8080")
ORDER_FIELDS = {"customer_name": "IT Customer", "customer_email": "it@example.com", "shipping_address": "1 Test St"}


def _credentials() -> dict:
    creds = {k: os.getenv(k) for k in ("STAFF_USER", "STAFF_PASSWORD", "VIEWER_USER", "VIEWER_PASSWORD")}
    path = os.getenv("CREDENTIALS_FILE")
    if path:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            creds[key.strip()] = value.strip()
    missing = [k for k, v in creds.items() if not v]
    if missing:
        pytest.exit(f"set {', '.join(missing)} or CREDENTIALS_FILE", returncode=2)
    return creds


@pytest.fixture(scope="session")
def http():
    with httpx.Client(base_url=BASE_URL, timeout=20) as client:
        yield client


def _login(http, user, password) -> dict:
    r = http.post("/api/auth/login", json={"username": user, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def tokens(http):
    c = _credentials()
    return {"staff": _login(http, c["STAFF_USER"], c["STAFF_PASSWORD"]),
            "viewer": _login(http, c["VIEWER_USER"], c["VIEWER_PASSWORD"])}


@pytest.fixture(scope="session")
def staff(tokens):
    return tokens["staff"]


@pytest.fixture(scope="session")
def viewer(tokens):
    return tokens["viewer"]


def unique(prefix="IT"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def product(http, staff):
    def make(stock=10, price="9.99", safety_stock=2, name=None):
        sku = unique()
        r = http.post("/api/inventory/products", headers=staff,
                      json={"sku": sku, "name": name or sku, "price": price, "stock": stock,
                            "safety_stock": safety_stock})
        assert r.status_code == 201, r.text
        return r.json()
    return make


def stock_of(http, staff, product_id) -> int:
    return http.get(f"/api/inventory/stock/{product_id}", headers=staff).json()["current_stock"]


def parallel(n, fn):
    """Run fn(i) n times at once; each call uses its own connection."""
    def call(i):
        with httpx.Client(base_url=BASE_URL, timeout=30) as c:
            return fn(c, i)
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(call, range(n)))
