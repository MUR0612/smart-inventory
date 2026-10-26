"""Liveness vs readiness.

* livez: the process answers; never touches dependencies, so a DB outage does
  not cause a restart storm.
* readyz: MySQL must answer (core dependency). Redis is optional; when it is
  down the service still reports ready but ``degraded``.
"""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from smart_shared.config import required_schema_version
from .. import redis_client
from ..db import engine

router = APIRouter(prefix="/api/inventory", tags=["health"])
logger = logging.getLogger("inventory-service.health")


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
    checks = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            checks["schema"] = _schema_state(conn)
        checks["database"] = "up"
    except Exception as exc:  # any driver error means "not ready"
        logger.warning("readiness: database check failed (%s)", type(exc).__name__)
        checks["database"] = "down"
    checks.setdefault("schema", "unknown")
    checks["redis"] = "up" if redis_client.ping() else "down"

    if checks["database"] != "up" or checks["schema"] != "ok":
        return JSONResponse(status_code=503, content={"status": "unavailable", "checks": checks})
    return {"status": "ok" if checks["redis"] == "up" else "degraded", "checks": checks}


@router.get("/readyz")
def readyz():
    return _readiness()


@router.get("/healthz")
def healthz():
    return _readiness()
