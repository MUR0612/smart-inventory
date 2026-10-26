"""Unit-test setup: SQLite + an in-memory fake of inventory-service.

FakeInventory implements the same reserve/release/commit semantics as the
real reservation API (all-or-nothing, idempotent, release tombstones) and can
inject failures *before* or *after* applying a change, which is how the
"timeout but the other side committed" cases are reproduced.
"""
import os
import pathlib
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "shared"), str(ROOT / "order-service")]

os.environ.update(
    REQUIRED_SCHEMA_VERSION="0",  # SQLite test DB is created by the ORM, not by db/migrate.py
    DB_URL=f"sqlite:///{tempfile.mkdtemp()}/orders.db",
    AUTH_SECRET="unit-test-auth-secret-0123456789-abcdef",
    SERVICE_TOKEN="unit-test-service-token-0123456789",
    INVENTORY_BASE_URL="http://inventory.invalid",
    BACKGROUND_TASKS_ENABLED="false",
)

from app.services.inventory_client import InventoryRejected, InventoryUnavailable  # noqa: E402


class FakeInventory:
    def __init__(self):
        self.products = {
            1: {"id": 1, "sku": "SKU-1", "name": "Widget", "price": "19.99"},
            2: {"id": 2, "sku": "SKU-2", "name": "Bolt", "price": "0.10"},
        }
        self.stock = {1: 10, 2: 5}
        self.reservations: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.failures: dict[str, list[str]] = {}  # method -> ["before" | "after", ...]

    def fail(self, method: str, *modes: str):
        self.failures.setdefault(method, []).extend(modes)

    def _mode(self, method):
        modes = self.failures.get(method)
        return modes.pop(0) if modes else None

    async def get_product(self, product_id):
        if product_id not in self.products:
            raise InventoryRejected(404, "Product not found")
        return self.products[product_id]

    async def reserve(self, rid, items):
        self.calls.append(("reserve", rid))
        mode = self._mode("reserve")
        if mode == "before":
            raise InventoryUnavailable("timeout")
        wanted = {i["product_id"]: i["qty"] for i in items}
        existing = self.reservations.get(rid)
        if existing:
            if existing["status"] == "RELEASED":
                raise InventoryRejected(409, "Reservation already released")
        else:
            short = [p for p, q in wanted.items() if self.stock.get(p, 0) < q]
            if short:
                raise InventoryRejected(409, {"message": "Insufficient stock", "items": short})
            for p, q in wanted.items():
                self.stock[p] -= q
            self.reservations[rid] = {"status": "RESERVED", "items": wanted}
        if mode == "after":
            raise InventoryUnavailable("response lost")
        return {"reservation_id": rid, "status": self.reservations[rid]["status"]}

    async def release(self, rid):
        self.calls.append(("release", rid))
        mode = self._mode("release")
        if mode == "before":
            raise InventoryUnavailable("timeout")
        res = self.reservations.get(rid)
        if res is None:
            self.reservations[rid] = {"status": "RELEASED", "items": {}}
        elif res["status"] == "COMMITTED":
            raise InventoryRejected(409, "already committed")
        elif res["status"] == "RESERVED":
            for p, q in res["items"].items():
                self.stock[p] += q
            res["status"] = "RELEASED"
        if mode == "after":
            raise InventoryUnavailable("response lost")
        return {"status": "RELEASED"}

    async def commit(self, rid):
        self.calls.append(("commit", rid))
        if self._mode("commit") == "before":
            raise InventoryUnavailable("timeout")
        self.reservations[rid]["status"] = "COMMITTED"
        return {"status": "COMMITTED"}

    async def aclose(self):
        pass


@pytest.fixture
def inventory():
    return FakeInventory()


@pytest.fixture
def client(inventory):
    from fastapi.testclient import TestClient
    from app.db import engine
    from app.main import app
    from app.models import Base
    from app.services.inventory_client import get_inventory_client
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_inventory_client] = lambda: inventory
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _token(role: str) -> dict:
    from smart_shared import auth
    token, _ = auth.issue_token(auth.Principal(f"test-{role}", role))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def staff():
    return _token("staff")


@pytest.fixture
def viewer():
    return _token("viewer")


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    yield s
    s.close()
