"""COA reading progress over Redis: the worker publishes, the SSE endpoint relays.

The latest event is also stored under a key for listeners that join late.
"""

import asyncio
import json

import redis
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.models import COADocument
from app.models.enums import ExtractionStatus

QUEUED = {"stage": "queued", "message": "Waiting for the COA reader to pick it up…"}
READING = {"stage": "reading", "message": "Claude is reading the COA…"}
MANUAL = {"stage": "manual", "message": "Not read automatically. Enter the values by hand."}
WAITING = {
    "stage": "waiting",
    "message": "Still waiting for the COA reader. Check back later, or enter the values by hand.",
}

# Events that end a stream.
FINAL = {"done", "failed", "manual", "waiting"}


def final_event(coa: COADocument) -> dict:
    """Return the closing event for a COA whose reading is over."""
    if coa.extraction_status == ExtractionStatus.DONE:
        if coa.extraction_model in (None, "manual"):
            return {"stage": "done", "message": "Values are in."}
        n = len(coa.results)
        return {"stage": "done", "message": f"Claude read {n} results. The check has run."}
    if coa.extraction_status == ExtractionStatus.FAILED:
        message = coa.extraction_error or "Something went wrong while reading this COA."
        return {"stage": "failed", "message": message}
    return MANUAL


def _channel(coa_id: int) -> str:
    """Return the pub/sub channel for a COA."""
    return f"batchgate:coa:{coa_id}:events"


def _last_key(coa_id: int) -> str:
    """Return the key holding a COA's latest event."""
    return f"batchgate:coa:{coa_id}:last"


def publish(coa_id: int, event: dict) -> None:
    """Publish a progress event; ignored when Redis is unavailable."""
    payload = json.dumps(event)
    try:
        with redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2) as r:
            r.set(_last_key(coa_id), payload, ex=3600)
            r.publish(_channel(coa_id), payload)
    except (redis.RedisError, OSError):
        pass


class Subscription:
    """A live subscription to one COA's events."""

    def __init__(self, coa_id: int):
        """Prepare a subscription for one COA."""
        self.coa_id = coa_id
        self._redis = aioredis.Redis.from_url(get_settings().redis_url)
        self._pubsub = self._redis.pubsub()

    async def start(self) -> "Subscription":
        """Connect and subscribe."""
        await self._pubsub.subscribe(_channel(self.coa_id))
        return self

    async def last(self) -> dict | None:
        """Return the latest stored event, or None."""
        raw = await self._redis.get(_last_key(self.coa_id))
        return json.loads(raw) if raw else None

    async def next(self, timeout: float) -> dict | None:
        """Return the next event, or None after `timeout` seconds."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while (left := deadline - loop.time()) > 0:
            msg = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=left)
            if msg is not None:
                return json.loads(msg["data"])
        return None

    async def close(self) -> None:
        """Unsubscribe and close the connection."""
        await self._pubsub.aclose()
        await self._redis.aclose()


async def subscribe(coa_id: int) -> Subscription:
    """Return a started subscription to a COA's events."""
    return await Subscription(coa_id).start()
