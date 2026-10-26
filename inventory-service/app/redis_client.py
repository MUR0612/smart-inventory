"""Redis access with short timeouts and a tiny circuit breaker.

Redis is an optional dependency for this service (cache + event log). When it
is down, callers get ``None`` and fall back to MySQL instead of failing.
"""
import logging
import time

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from smart_shared.config import redis_settings
from smart_shared.observability import log_fields

logger = logging.getLogger("inventory-service.redis")

_client: redis.Redis | None = None
_open_until = 0.0
BREAKER_SECONDS = 5.0


def client() -> redis.Redis | None:
    """Return the client, or None while the breaker is open after a failure."""
    global _client
    if time.monotonic() < _open_until:
        return None
    if _client is None:
        # No client-side retries: a failed call falls back immediately and the
        # breaker decides when to try again (redis-py retries 3x by default).
        _client = redis.Redis(decode_responses=True, retry=Retry(NoBackoff(), 0), **redis_settings())
    return _client


def record_failure(operation: str, exc: Exception):
    global _open_until
    _open_until = time.monotonic() + BREAKER_SECONDS
    logger.warning("redis operation failed; using fallback", extra=log_fields(operation=operation,
                                                                             error=type(exc).__name__))


def ping() -> bool:
    c = client()
    if c is None:
        return False
    try:
        return bool(c.ping())
    except redis.RedisError as exc:
        record_failure("ping", exc)
        return False
