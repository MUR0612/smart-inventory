"""After migrating a legacy fixture: legacy orders follow the new stock rules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smoke_test import Api, check  # noqa: E402

base_url, creds_file = sys.argv[1], sys.argv[2]
creds = dict(line.split("=", 1) for line in open(creds_file, encoding="utf-8").read().split())
api = Api(base_url)
api.token = api.call("POST", "/api/auth/login", {"username": creds["STAFF_USER"],
                                                 "password": creds["STAFF_PASSWORD"]})["access_token"]
stock = lambda pid: api.call("GET", f"/api/inventory/stock/{pid}")["current_stock"]  # noqa: E731

check("legacy stock carried over", (stock(1), stock(2), stock(3)) == (48, 49, 49))
legacy = api.call("GET", "/api/orders/1")
check("legacy CREATED order got a reservation", legacy["inventory_sync"] == "RESERVED" and legacy["total"] == "39.98")
check("legacy items merged into one reservation line", sum(i["qty"] for i in legacy["items"]) == 2)
api.call("POST", "/api/orders/1/cancel")
check("cancelling a legacy order returns its stock", stock(1) == 50)
api.call("PATCH", "/api/orders/2/status", {"status": "REFUNDED"})
check("refunding a legacy PAID order returns its stock", stock(2) == 50)
api.call("PATCH", "/api/orders/3/status", {"status": "REFUNDED"})
check("refunding a legacy SHIPPED order does not restock", stock(3) == 49)
check("legacy CANCELLED order is flagged, not guessed", "legacy" in (api.call("GET", "/api/orders/4")["sync_error"] or ""))
print("legacy upgrade verified")
