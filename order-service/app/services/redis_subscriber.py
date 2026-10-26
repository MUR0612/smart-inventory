"""Non-blocking Redis Pub/Sub subscriber (demo event log).

Uses ``redis.asyncio`` so waiting for messages never blocks the event loop,
reconnects with back-off after Redis restarts, and stops cleanly when the
lifespan cancels the task.

Scope (be honest in docs/demos): handlers only log a compact summary and keep
the last few events in memory for ``GET /api/orders/events/recent``. There is
no e-mail, auto-replenishment or live browser push, and Pub/Sub does not
store messages, so events published while this subscriber is offline are lost.
Order and stock correctness never depend on these events.
"""
import asyncio
import json
import logging
from collections import deque

import redis
import redis.asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from smart_shared.config import redis_settings
from smart_shared.observability import log_fields

logger = logging.getLogger("order-service.subscriber")

CHANNELS = ("low_stock_alerts", "stock_changes")
_SUMMARY_FIELDS = ("product_id", "sku", "old_stock", "new_stock", "adjustment", "current_stock",
                   "safety_stock", "source", "timestamp")


class RedisSubscriber:
    def __init__(self):
        self.recent: deque[dict] = deque(maxlen=20)
        self.connected = False

    def handle(self, channel: str, raw: str):
        try:
            data = json.loads(raw)
        except ValueError:
            logger.warning("ignoring malformed event", extra=log_fields(channel=channel))
            return
        summary = {"channel": channel, **{k: data.get(k) for k in _SUMMARY_FIELDS if k in data}}
        self.recent.appendleft(summary)
        logger.info("event received", extra=log_fields(**summary))

    async def run(self):
        delay = 1.0
        settings = redis_settings()
        while True:
            client = aioredis.Redis(host=settings["host"], port=settings["port"], decode_responses=True,
                                    socket_connect_timeout=2, health_check_interval=15,
                                    retry=Retry(NoBackoff(), 0))  # reconnects are handled below
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            try:
                await pubsub.subscribe(*CHANNELS)
                self.connected = True
                delay = 1.0
                logger.info("subscribed", extra=log_fields(channels=list(CHANNELS)))
                while True:
                    message = await pubsub.get_message(timeout=1.0)
                    if message and message.get("type") == "message":
                        self.handle(message["channel"], message["data"])
            except (redis.RedisError, OSError) as exc:
                logger.warning("subscription lost; reconnecting",
                               extra=log_fields(error=type(exc).__name__, retry_in_seconds=delay))
            finally:
                self.connected = False
                await pubsub.aclose()
                await client.aclose()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


redis_subscriber = RedisSubscriber()
