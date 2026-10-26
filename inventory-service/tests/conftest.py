"""Unit-test setup: SQLite instead of MySQL, a fake Redis, fixed test secrets.

Row locking is not exercised here (SQLite ignores FOR UPDATE); the real
concurrency tests run against MySQL in tests/integration.
"""
import json
import os
import pathlib
import sys
import tempfile

import pytest
import redis

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "shared"), str(ROOT / "inventory-service")]

from smart_shared.passwords import hash_password  # noqa: E402

STAFF_PW = "staff-password-123"
VIEWER_PW = "viewer-password-123"
SERVICE_TOKEN = "unit-test-service-token-0123456789"

os.environ.update(
    REQUIRED_SCHEMA_VERSION="0",  # SQLite test DB is created by the ORM, not by db/migrate.py
    DB_URL=f"sqlite:///{tempfile.mkdtemp()}/inventory.db",
    AUTH_SECRET="unit-test-auth-secret-0123456789-abcdef",
    SERVICE_TOKEN=SERVICE_TOKEN,
    AUTH_USERS=f"alice:staff:{hash_password(STAFF_PW, iterations=1000)},"
               f"victor:viewer:{hash_password(VIEWER_PW, iterations=1000)}",
)


class FakeRedis:
    def __init__(self):
        self.store, self.published, self.fail = {}, [], False

    def _check(self):
        if self.fail:
            raise redis.ConnectionError("redis down (test)")

    def get(self, key):
        self._check()
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self._check()
        self.store[key] = value

    def incr(self, key):
        self._check()
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])

    def delete(self, key):
        self._check()
        self.store.pop(key, None)

    def publish(self, channel, message):
        self._check()
        self.published.append((channel, json.loads(message)))

    def ping(self):
        self._check()
        return True


@pytest.fixture
def fake_redis():
    from app import redis_client
    fake = FakeRedis()
    redis_client._client = fake
    redis_client._open_until = 0.0
    return fake


@pytest.fixture
def client(fake_redis):
    from fastapi.testclient import TestClient
    from app.db import engine
    from app.main import app
    from app.models import Base
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _login(client, user, pw):
    r = client.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def staff(client):
    return _login(client, "alice", STAFF_PW)


@pytest.fixture
def viewer(client):
    return _login(client, "victor", VIEWER_PW)


@pytest.fixture
def service():
    return {"X-Service-Token": SERVICE_TOKEN}


@pytest.fixture
def make_product(client, staff):
    counter = iter(range(1, 10_000))

    def make(stock=10, price="19.99", safety_stock=2, name=None):
        n = next(counter)
        r = client.post("/api/inventory/products", headers=staff,
                        json={"sku": f"SKU-T{n}", "name": name or f"Product {n}", "price": price,
                              "safety_stock": safety_stock, "stock": stock})
        assert r.status_code == 201, r.text
        return r.json()
    return make
