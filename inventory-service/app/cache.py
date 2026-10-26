"""Product-list cache (fail-open).

Consistency rule: a write bumps ``products:list:gen`` after its DB commit;
readers only use the key of the generation they saw *before* querying MySQL,
so a slow reader can never put an older list back under the current key.
If the bump itself fails (Redis down), the TTL bounds staleness to 30 s.
The cache is display-only; stock checks and reservations always use MySQL.
"""
import json
import logging

import redis

from . import redis_client

logger = logging.getLogger("inventory-service.cache")

TTL_SECONDS = 30
_GEN_KEY = "products:list:gen"


def _key(gen: str) -> str:
    return f"products:list:v2:{gen}"


def current_generation() -> str | None:
    c = redis_client.client()
    if c is None:
        return None
    try:
        return c.get(_GEN_KEY) or "0"
    except redis.RedisError as exc:
        redis_client.record_failure("cache.generation", exc)
        return None


def get_products(gen: str) -> list | None:
    c = redis_client.client()
    if c is None:
        return None
    try:
        raw = c.get(_key(gen))
    except redis.RedisError as exc:
        redis_client.record_failure("cache.get", exc)
        return None
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("cached value is not a list")
        return data
    except ValueError:
        logger.warning("discarding corrupt product cache entry")
        try:
            c.delete(_key(gen))
        except redis.RedisError as exc:
            redis_client.record_failure("cache.delete", exc)
        return None


def store_products(gen: str, products: list):
    c = redis_client.client()
    if c is None:
        return
    try:
        c.setex(_key(gen), TTL_SECONDS, json.dumps(products))
    except redis.RedisError as exc:
        redis_client.record_failure("cache.set", exc)


def invalidate_products():
    c = redis_client.client()
    if c is None:
        logger.warning("product cache not invalidated (redis unavailable); stale for up to %ss", TTL_SECONDS)
        return
    try:
        c.incr(_GEN_KEY)
    except redis.RedisError as exc:
        redis_client.record_failure("cache.invalidate", exc)
