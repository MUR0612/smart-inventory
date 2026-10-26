"""Structured logging, request IDs and safe error responses."""
import contextvars
import json
import logging
import sys
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(service: str):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger(service).info("logging configured")


def log_fields(**fields) -> dict:
    """Usage: logger.info("msg", extra=log_fields(order_id=1))."""
    return {"fields": fields}


def install(app: FastAPI, service: str):
    """Attach request-ID propagation and a generic 500 handler."""
    logger = logging.getLogger(service)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if 0 < len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex
        request.state.request_id = rid
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # The default handler echoes the rejected input back, which leaks values
        # such as passwords and crashes on NaN. Return only where/what failed.
        errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "invalid"), "type": e.get("type")}
                  for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        # Full details go to the log only; clients never see stack traces,
        # connection strings or internal host names.
        rid = getattr(request.state, "request_id", "-")
        token = request_id_var.set(rid)
        try:
            logger.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        finally:
            request_id_var.reset(token)
        return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": rid})
