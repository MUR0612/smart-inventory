"""Redis Pub/Sub publisher for the demo event log.

Pub/Sub is fire-and-forget: if no subscriber is connected, or Redis is down,
the event is lost. Nothing in order/stock correctness depends on these events.
Failures are logged (never silently ignored) and never fail the request.
"""
import json
import logging

import redis

from . import redis_client
from .db import as_utc, utcnow
from smart_shared.observability import log_fields

logger = logging.getLogger("inventory-service.events")

STOCK_CHANGES = "stock_changes"
LOW_STOCK_ALERTS = "low_stock_alerts"


def publish(channel: str, payload: dict) -> bool:
    c = redis_client.client()
    if c is None:
        logger.warning("event not published (redis unavailable)", extra=log_fields(channel=channel))
        return False
    try:
        c.publish(channel, json.dumps(payload, default=str))
        return True
    except redis.RedisError as exc:
        redis_client.record_failure("events.publish", exc)
        logger.warning("event not published", extra=log_fields(channel=channel))
        return False


def stock_changed(product, old_stock: int, new_stock: int, source: str, reference: str | None = None):
    """Single place that builds stock events, used by adjust, set and reservations."""
    timestamp = as_utc(utcnow()).isoformat()
    is_low = new_stock <= product.safety_stock
    publish(STOCK_CHANGES, {
        "product_id": product.id,
        "sku": product.sku,
        "old_stock": old_stock,
        "new_stock": new_stock,
        "adjustment": new_stock - old_stock,
        "is_low_stock": is_low,
        "source": source,
        "reference": reference,
        "timestamp": timestamp,
    })
    if is_low:
        publish(LOW_STOCK_ALERTS, {
            "product_id": product.id,
            "sku": product.sku,
            "current_stock": new_stock,
            "safety_stock": product.safety_stock,
            "timestamp": timestamp,
        })
