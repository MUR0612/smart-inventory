"""HTTP client for inventory-service (authenticated with the service token).

Errors are split by what they tell us about the remote side effect:

* ``InventoryRejected``   - a definite 4xx answer: nothing was applied.
* ``InventoryUnavailable`` - timeout, connection error or 5xx: the outcome is
  UNKNOWN (the request may have been applied and only the response lost).
"""
import logging

import httpx

from smart_shared import auth
from smart_shared.config import optional, require
from smart_shared.observability import log_fields, request_id_var

logger = logging.getLogger("order-service.inventory-client")


class InventoryError(Exception):
    pass


class InventoryRejected(InventoryError):
    def __init__(self, status_code: int, detail):
        super().__init__(f"inventory rejected request ({status_code})")
        self.status_code = status_code
        self.detail = detail


class InventoryUnavailable(InventoryError):
    pass


class InventoryClient:
    def __init__(self, base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url or require("INVENTORY_BASE_URL")
        self.timeout = httpx.Timeout(float(optional("INVENTORY_TIMEOUT_SECONDS", "5")))
        self.transport = transport
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self.transport,
                                             headers={"X-Service-Token": auth.settings().service_token})
        return self._client

    async def aclose(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs):
        try:
            response = await self._http().request(method, path, headers={"X-Request-ID": request_id_var.get()},
                                                  **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("inventory request failed", extra=log_fields(path=path, error=type(exc).__name__))
            raise InventoryUnavailable(type(exc).__name__) from exc
        if response.status_code >= 500 or response.status_code in (401, 403):
            # 401/403 means a service-token misconfiguration; surface it as unavailable.
            logger.warning("inventory error response", extra=log_fields(path=path, status=response.status_code))
            raise InventoryUnavailable(f"status {response.status_code}")
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = None
            raise InventoryRejected(response.status_code, detail)
        return response.json()

    async def get_product(self, product_id: int) -> dict:
        return await self._request("GET", f"/api/inventory/products/{product_id}")

    async def reserve(self, reservation_id: str, items: list[dict]) -> dict:
        return await self._request("POST", "/api/inventory/reservations",
                                   json={"reservation_id": reservation_id, "items": items})

    async def release(self, reservation_id: str) -> dict:
        return await self._request("POST", f"/api/inventory/reservations/{reservation_id}/release")

    async def commit(self, reservation_id: str) -> dict:
        return await self._request("POST", f"/api/inventory/reservations/{reservation_id}/commit")


_client: InventoryClient | None = None


def get_inventory_client() -> InventoryClient:
    """FastAPI dependency (tests override it with a fake)."""
    global _client
    if _client is None:
        _client = InventoryClient()
    return _client
