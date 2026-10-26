"""Liveness vs readiness (see inventory-service health.py for the rules).

Readiness only requires MySQL. inventory-service and Redis being down makes
order creation fail with 503 / disables the event log, but reads still work.
"""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from smart_shared.config import required_schema_version
from ..db import engine
from ..services.redis_subscriber import redis_subscriber

router = APIRouter(prefix="/api/orders", tags=["health"])
logger = logging.getLogger("order-service.health")


def _schema_state(conn) -> str:
    required = required_schema_version()
    if not required:
        return "ok"
    version = conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar() or 0
    return "ok" if version >= required else f"outdated ({version} < {required})"


@router.get("/livez")
def livez():
    return {"status": "ok"}


def _readiness():
    checks = {"event_subscriber": "connected" if redis_subscriber.connected else "disconnected"}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            checks["schema"] = _schema_state(conn)
        checks["database"] = "up"
    except Exception as exc:
        logger.warning("readiness: database check failed (%s)", type(exc).__name__)
        checks["database"] = "down"
        return JSONResponse(status_code=503, content={"status": "unavailable", "checks": checks})
    if checks["schema"] != "ok":
        return JSONResponse(status_code=503, content={"status": "unavailable", "checks": checks})
    return {"status": "ok" if redis_subscriber.connected else "degraded", "checks": checks}


@router.get("/readyz")
def readyz():
    return _readiness()


@router.get("/healthz")
def healthz():
    return _readiness()
