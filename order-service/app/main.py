"""Order service entry point.

Background work (Redis subscriber + inventory reconcile loop) is owned by the
lifespan: started after startup, cancelled and awaited on shutdown, and any
unexpected crash of a task is logged instead of disappearing silently.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smart_shared import auth, observability
from smart_shared.config import cors_origins, optional

observability.setup_logging("order-service")
auth.settings()  # validate AUTH_SECRET / SERVICE_TOKEN at startup

from .db import SessionLocal  # noqa: E402
from .routers import health, orders  # noqa: E402
from .services import order_workflow  # noqa: E402
from .services.inventory_client import get_inventory_client  # noqa: E402
from .services.redis_subscriber import redis_subscriber  # noqa: E402

logger = logging.getLogger("order-service")
RECONCILE_INTERVAL = float(optional("RECONCILE_INTERVAL_SECONDS", "30"))


async def reconcile_loop():
    client = get_inventory_client()
    while True:
        await asyncio.sleep(RECONCILE_INTERVAL)
        db = SessionLocal()
        try:
            await order_workflow.reconcile_once(db, client)
        except Exception:
            logger.exception("reconcile pass failed; will retry")
        finally:
            db.close()


def _log_task_end(task: asyncio.Task):
    if not task.cancelled() and task.exception():
        logger.error("background task %s crashed", task.get_name(), exc_info=task.exception())


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = []
    if optional("BACKGROUND_TASKS_ENABLED", "true").lower() == "true":
        tasks = [asyncio.create_task(redis_subscriber.run(), name="redis-subscriber"),
                 asyncio.create_task(reconcile_loop(), name="inventory-reconcile")]
        for task in tasks:
            task.add_done_callback(_log_task_end)
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await get_inventory_client().aclose()


docs = optional("ENABLE_API_DOCS", "true").lower() == "true"
app = FastAPI(title="Order Service", lifespan=lifespan,
              docs_url="/api/orders/docs" if docs else None,
              openapi_url="/api/orders/openapi.json" if docs else None,
              redoc_url=None)
observability.install(app, "order-service")

origins = cors_origins()
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"])

app.include_router(health.router)
app.include_router(orders.router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(optional("PORT", "8002")), log_config=None)
