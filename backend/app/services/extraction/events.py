"""Live progress of COA reading: the worker publishes, the SSE endpoint relays it to the browser.

Redis pub/sub only reaches listeners that are subscribed at the time, so the latest event is
also kept under a key for anyone who starts watching halfway through.
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

# The stream ends on these; the browser then reloads the batch.
FINAL = {"done", "failed", "manual", "waiting"}


def final_event(coa: COADocument) -> dict:
    """The closing event for a COA whose reading is over (or will not happen)."""
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
    return f"batchgate:coa:{coa_id}:events"


def _last_key(coa_id: int) -> str:
    return f"batchgate:coa:{coa_id}:last"


def publish(coa_id: int, event: dict) -> None:
    """Called from the worker (sync code)."""
    payload = json.dumps(event)
    with redis.Redis.from_url(get_settings().redis_url) as r:
        r.set(_last_key(coa_id), payload, ex=3600)
        r.publish(_channel(coa_id), payload)


class Subscription:
    def __init__(self, coa_id: int):
        self.coa_id = coa_id
        self._redis = aioredis.Redis.from_url(get_settings().redis_url)
        self._pubsub = self._redis.pubsub()

    async def start(self) -> "Subscription":
        await self._pubsub.subscribe(_channel(self.coa_id))
        return self

    async def last(self) -> dict | None:
        raw = await self._redis.get(_last_key(self.coa_id))
        return json.loads(raw) if raw else None

    async def next(self, timeout: float) -> dict | None:
        """The next event, or None if nothing arrived within `timeout` seconds."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while (left := deadline - loop.time()) > 0:
            msg = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=left)
            if msg is not None:
                return json.loads(msg["data"])
        return None

    async def close(self) -> None:
        await self._pubsub.aclose()
        await self._redis.aclose()


async def subscribe(coa_id: int) -> Subscription:
    return await Subscription(coa_id).start()
