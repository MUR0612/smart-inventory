"""Inventory service entry point.

The schema is created/upgraded by the one-off migration job (db/migrate.py),
not here, so several replicas can start at once without racing on DDL.
Missing configuration fails fast with the variable name (never its value).
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smart_shared import auth, observability
from smart_shared.config import cors_origins, optional

observability.setup_logging("inventory-service")
auth.settings()  # validate AUTH_SECRET / SERVICE_TOKEN at startup

from .routers import auth as auth_routes, health, products, reservations, stock  # noqa: E402

docs = optional("ENABLE_API_DOCS", "true").lower() == "true"
app = FastAPI(title="Inventory Service",
              docs_url="/api/inventory/docs" if docs else None,
              openapi_url="/api/inventory/openapi.json" if docs else None,
              redoc_url=None)
observability.install(app, "inventory-service")

origins = cors_origins()
if origins:
    # Only needed when the UI is served from another origin; bearer tokens, no cookies.
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"])

app.include_router(health.router)
app.include_router(auth_routes.router)
app.include_router(products.router)
app.include_router(stock.router)
app.include_router(reservations.router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(optional("PORT", "8001")), log_config=None)
