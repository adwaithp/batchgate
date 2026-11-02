"""Background worker: Claude reads uploaded COAs here, outside the upload request.

Run it next to the API (needs Redis):  uv run arq app.worker.WorkerSettings
"""

import asyncio
import logging

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import COADocument
from app.models.enums import ExtractionStatus
from app.services import batches as svc
from app.services.extraction import events

log = logging.getLogger(__name__)


def _extract(coa_id: int) -> str:
    events.publish(coa_id, events.READING)
    with SessionLocal() as db:
        coa = db.get(COADocument, coa_id)
        if coa is None:
            return "missing"
        try:
            svc.extract_coa(db, coa)
            db.commit()
        except Exception:
            # A bug or a locked database, not a bad document: still hand the COA to a person.
            log.exception("Reading COA %s failed", coa_id)
            db.rollback()
            if coa.extraction_status == ExtractionStatus.PENDING:
                coa.extraction_status = ExtractionStatus.FAILED
                coa.extraction_error = "Something went wrong while reading this COA."
                db.commit()
        event = events.final_event(coa)
    # After the commit, so the browser's reload sees the saved values.
    events.publish(coa_id, event)
    return event["stage"]


async def extract_coa(ctx: dict, coa_id: int) -> str:
    # The SDK call and SQLAlchemy are synchronous; keep them off the worker's event loop.
    return await asyncio.to_thread(_extract, coa_id)


_pool: ArqRedis | None = None


async def enqueue_extraction(coa_id: int) -> None:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await _pool.enqueue_job("extract_coa", coa_id, _job_id=f"extract-coa-{coa_id}")


class WorkerSettings:
    functions = [extract_coa]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = 300
