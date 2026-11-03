"""Batch API: batches, COA uploads, reading progress, decisions and the copilot."""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import or_, select

from app import worker
from app.api.deps import DbSession, require
from app.core.config import get_settings
from app.core.permissions import ROLE_LABELS, Permission
from app.models import (
    Batch,
    COADocument,
    Order,
    OrderLine,
    Product,
    Supplier,
    User,
)
from app.models.enums import (
    BatchStatus,
    CoaSource,
    ExtractionStatus,
    OrderStatus,
    SupplierKind,
)
from app.schemas.batches import (
    ActionOut,
    BatchActionIn,
    BatchCreate,
    BatchDetail,
    BatchLineBrief,
    BatchSummary,
    CatalogOptions,
    CoaDataIn,
    CoaOut,
    CoaResultOut,
    LineOption,
    LineOut,
    LineWithSpec,
    ProductRef,
    SpecOut,
    SpecParameterOut,
    SuggestionOut,
    SupplierRef,
    VerdictBrief,
    VerdictOut,
)
from app.schemas.copilot import CopilotOut, CopilotSource
from app.services import audit, copilot
from app.services import batches as svc
from app.services.extraction import events
from app.services.rules.engine import spec_text
from app.services.rules.types import ParamSpec

router = APIRouter(tags=["batches"])

Viewer = Annotated[User, Depends(require(Permission.VIEW_BATCHES))]
Uploader = Annotated[User, Depends(require(Permission.UPLOAD_COA))]


def _line_out(line: OrderLine) -> LineOut:
    """Map an order line to its API view."""
    return LineOut(
        id=line.id,
        order_id=line.order_id,
        po_number=line.order.po_number,
        line_no=line.line_no,
        customer=line.order.customer.name,
        product=line.product.name,
        grade=line.spec.grade,
        quantity=line.quantity,
        unit=line.unit,
        released_quantity=svc.released_quantity(line),
    )


def _spec_out(line: OrderLine) -> SpecOut:
    """Map a spec and its parameters to their API view."""
    spec = line.spec
    return SpecOut(
        id=spec.id,
        grade=spec.grade,
        version=spec.version,
        customer=spec.customer.name,
        product=spec.product.name,
        parameters=[
            SpecParameterOut(
                id=p.id,
                name=p.name,
                rule_type=p.rule_type,
                low=p.low,
                high=p.high,
                unit=p.unit,
                expected_text=p.expected_text,
                critical=p.critical,
                aliases=list(p.aliases or []),
                spec_text=spec_text(
                    ParamSpec(p.id, p.name, p.rule_type, p.low, p.high, p.unit, p.expected_text)
                ),
            )
            for p in spec.parameters
        ],
    )


def _summary(batch: Batch) -> BatchSummary:
    """Map a batch to its list-row view."""
    verdict = svc.latest_verdict(batch)
    line = batch.line
    return BatchSummary(
        id=batch.id,
        batch_number=batch.batch_number,
        product=ProductRef.model_validate(batch.product),
        factory=SupplierRef.model_validate(batch.factory) if batch.factory else None,
        status=batch.status,
        quantity=batch.quantity,
        unit=batch.unit,
        line=BatchLineBrief(
            id=line.id,
            po_number=line.order.po_number,
            line_no=line.line_no,
            grade=line.spec.grade,
            customer=line.order.customer.name,
        )
        if line
        else None,
        decision=verdict.decision if verdict else None,
        summary=verdict.summary if verdict else None,
        coa_sources=sorted({c.source for c in svc.active_coas(batch)}),
        updated_at=batch.updated_at,
    )


def _coa_out(db: DbSession, coa: COADocument) -> CoaOut:
    """Map a COA document and its result rows to their API view."""
    uploader = db.get(User, coa.uploaded_by_id) if coa.uploaded_by_id else None
    checker = db.get(User, coa.checked_by_id) if coa.checked_by_id else None
    low = get_settings().low_confidence_threshold
    return CoaOut(
        id=coa.id,
        source=coa.source,
        issuer=SupplierRef.model_validate(coa.issuer) if coa.issuer else None,
        origin=coa.origin,
        superseded=coa.superseded,
        original_filename=coa.original_filename,
        has_file=coa.storage_path is not None,
        uploaded_at=coa.uploaded_at,
        uploaded_by=uploader.full_name if uploader else None,
        extraction_status=coa.extraction_status,
        extraction_model=coa.extraction_model,
        extraction_error=coa.extraction_error,
        warnings=(coa.raw_extraction or {}).get("warnings", []),
        checked_by=checker.full_name if checker else None,
        issuer_name=coa.issuer_name,
        issuer_confidence=coa.issuer_confidence,
        issuer_needs_check=coa.issuer_name is not None and coa.issuer_confidence < low,
        product_name=coa.product_name,
        cas_number=coa.cas_number,
        batch_number=coa.batch_number,
        po_reference=coa.po_reference,
        mfg_date=coa.mfg_date,
        test_date=coa.test_date,
        expiry_date=coa.expiry_date,
        mfg_date_as_printed=coa.mfg_date_as_printed,
        test_date_as_printed=coa.test_date_as_printed,
        expiry_date_as_printed=coa.expiry_date_as_printed,
        results=[
            CoaResultOut(
                id=r.id,
                name_as_written=r.name_as_written,
                raw_value=r.raw_value,
                unit=r.unit,
                method=r.method,
                confidence=r.confidence,
                needs_check=r.confidence < low,
                matched_parameter_id=r.matched_parameter_id,
            )
            for r in coa.results
        ],
    )


def _detail(db: DbSession, batch: Batch, user: User) -> BatchDetail:
    """Build the full batch view, including what `user` may do next."""
    verdict = svc.latest_verdict(batch)
    suggestions = []
    if batch.line is None:
        suggestions = [
            SuggestionOut(
                line=_line_out(s.line), decision=s.decision, summary=s.summary, failing=s.failing
            )
            for s in svc.suggest_lines(db, batch)
        ]
    history = sorted(batch.verdicts, key=lambda v: v.id, reverse=True)
    return BatchDetail(
        **_summary(batch).model_dump(),
        line_detail=LineWithSpec(**_line_out(batch.line).model_dump(), spec=_spec_out(batch.line))
        if batch.line
        else None,
        coas=[_coa_out(db, c) for c in sorted(batch.coas, key=lambda c: c.id, reverse=True)],
        verdict=VerdictOut(
            id=verdict.id,
            decision=verdict.decision,
            summary=verdict.summary,
            details=verdict.details,
            engine_version=verdict.engine_version,
            created_at=verdict.created_at,
        )
        if verdict
        else None,
        history=[
            VerdictBrief(id=v.id, decision=v.decision, summary=v.summary, created_at=v.created_at)
            for v in history
        ],
        actions=[
            ActionOut(
                id=a.id,
                action=a.action,
                actor=a.actor.full_name,
                actor_role=ROLE_LABELS[a.actor.role],
                note=a.note,
                created_at=a.created_at,
            )
            for a in batch.actions
        ],
        allowed_actions=svc.allowed_actions(batch, user),
        suggestions=suggestions,
    )


def _get_batch(db: DbSession, batch_id: int) -> Batch:
    """Load a batch or raise 404."""
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
    return batch


@router.get("/catalog/options", response_model=CatalogOptions)
def catalog_options(db: DbSession, _: Viewer) -> CatalogOptions:
    """Products, factories, labs and open order lines for the batch forms."""
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
    lines = db.scalars(
        select(OrderLine)
        .join(Order)
        .where(Order.status != OrderStatus.SHIPPED)
        .order_by(Order.order_date.desc(), OrderLine.line_no)
    )
    products = db.scalars(select(Product).order_by(Product.name))
    return CatalogOptions(
        products=[ProductRef.model_validate(p) for p in products],
        factories=[
            SupplierRef.model_validate(s) for s in suppliers if s.kind == SupplierKind.FACTORY
        ],
        labs=[SupplierRef.model_validate(s) for s in suppliers if s.kind == SupplierKind.LAB],
        open_lines=[
            LineOption(
                id=ln.id,
                product_id=ln.product_id,
                label=f"{ln.order.po_number} · line {ln.line_no} · {ln.spec.grade}",
                po_number=ln.order.po_number,
                line_no=ln.line_no,
                grade=ln.spec.grade,
                customer=ln.order.customer.name,
                quantity=ln.quantity,
                unit=ln.unit,
            )
            for ln in lines
        ],
    )


@router.get("/batches", response_model=list[BatchSummary])
def list_batches(
    db: DbSession,
    _: Viewer,
    status_filter: Annotated[list[BatchStatus] | None, Query(alias="status")] = None,
    q: str | None = None,
) -> list[BatchSummary]:
    """List batches, most recently updated first, filtered by status or search text."""
    query = select(Batch).order_by(Batch.updated_at.desc(), Batch.id.desc())
    if status_filter:
        query = query.where(Batch.status.in_(status_filter))
    if q:
        like = f"%{q.strip()}%"
        query = query.join(Product).where(
            or_(Batch.batch_number.ilike(like), Product.name.ilike(like))
        )
    return [_summary(b) for b in db.scalars(query)]


@router.post("/batches", response_model=BatchDetail, status_code=status.HTTP_201_CREATED)
def create_batch(db: DbSession, user: Uploader, body: BatchCreate) -> BatchDetail:
    """Register a batch."""
    existing = db.scalar(
        select(Batch).where(
            Batch.factory_id == body.factory_id, Batch.batch_number == body.batch_number.strip()
        )
    )
    if existing:
        raise svc.WorkflowError(
            f"Batch {existing.batch_number} from this factory already exists (#{existing.id}).",
            409,
        )
    batch = svc.get_or_create_batch(
        db,
        batch_number=body.batch_number,
        product_id=body.product_id,
        factory_id=body.factory_id,
        line_id=body.line_id,
        quantity=body.quantity,
        actor=user,
    )
    db.commit()
    return _detail(db, batch, user)


@router.get("/batches/{batch_id}", response_model=BatchDetail)
def get_batch(db: DbSession, user: Viewer, batch_id: int) -> BatchDetail:
    """Return one batch in full."""
    return _detail(db, _get_batch(db, batch_id), user)


@router.post("/batches/{batch_id}/actions", response_model=BatchDetail)
def batch_action(db: DbSession, user: Viewer, batch_id: int, body: BatchActionIn) -> BatchDetail:
    """Apply a person's decision to a batch."""
    batch = _get_batch(db, batch_id)
    svc.apply_action(db, batch, body.action, actor=user, note=body.note, line_id=body.line_id)
    db.commit()
    return _detail(db, batch, user)


STREAM_SECONDS = 180  # after this the browser is told to check back later


def _sse(event: dict) -> str:
    """Format one server-sent event."""
    return f"data: {json.dumps(event)}\n\n"


def _reading(coa: COADocument) -> bool:
    """Return True when the worker is expected to read this COA."""
    return (
        coa.extraction_status == ExtractionStatus.PENDING
        and coa.storage_path is not None
        and bool(get_settings().anthropic_api_key)
    )


async def _relay(first: list[dict], sub: events.Subscription | None) -> AsyncIterator[str]:
    """Relay reading progress from Redis until a final event or the timeout."""
    try:
        for event in first:
            yield _sse(event)
        if sub is None or first[-1]["stage"] in events.FINAL:
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + STREAM_SECONDS
        while (left := deadline - loop.time()) > 0:
            event = await sub.next(timeout=min(15, left))
            if event is None:
                yield ": still reading\n\n"  # keeps proxies from closing a quiet stream
                continue
            yield _sse(event)
            if event["stage"] in events.FINAL:
                return
        yield _sse(events.WAITING)
    finally:
        if sub is not None:
            await sub.close()


POLL_SECONDS = 2.0


async def _poll_until_read(db: DbSession, coa_id: int, first: list[dict]) -> AsyncIterator[str]:
    """Follow a reading by polling the database (used without Redis)."""
    for event in first:
        yield _sse(event)
    yield _sse(events.READING)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + STREAM_SECONDS
    while loop.time() < deadline:
        db.expire_all()
        coa = db.get(COADocument, coa_id)
        if coa is None or not _reading(coa):
            yield _sse(events.final_event(coa) if coa else events.MANUAL)
            return
        await asyncio.sleep(POLL_SECONDS)
        yield ": still reading\n\n"
    yield _sse(events.WAITING)


async def _coa_stream(
    db: DbSession, coa: COADocument, first: list[dict], status_code: int = 200
) -> StreamingResponse:
    """Stream a COA's reading progress; always ends with a final event."""
    sub = None
    if not _reading(coa):
        last = events.final_event(coa)
    else:
        try:
            if get_settings().extraction_mode == "inline":
                raise RedisError("inline mode: no queue to follow")
            sub = await events.subscribe(
                coa.id
            )  # subscribe before re-checking the COA so no event is missed
        except (RedisError, OSError):
            # Without Redis the API reads COAs itself; watch the database instead.
            return StreamingResponse(
                _poll_until_read(db, coa.id, first),
                status_code=status_code,
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        else:
            db.refresh(coa)
            if _reading(coa):
                last = await sub.last()
                if last is None or last["stage"] in events.FINAL:
                    last = events.QUEUED  # a final event for a pending COA is stale
            else:
                last = events.final_event(coa)
    return StreamingResponse(
        _relay([*first, last], sub),
        status_code=status_code,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/batches/{batch_id}/coas", status_code=201, response_class=StreamingResponse)
async def upload_coa(
    db: DbSession,
    user: Uploader,
    batch_id: int,
    source: Annotated[CoaSource, Form()],
    issuer_id: Annotated[int | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> StreamingResponse:
    """Attach a COA to a batch and stream its reading as server-sent events.

    Without a file it creates an entry for typing values in. Events: `received`, `queued` or
    `reading`, then `done`, `failed`, `manual` or `waiting`.
    """
    batch = _get_batch(db, batch_id)
    incoming = None
    if file is not None and file.filename:
        incoming = svc.IncomingFile(
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            data=await file.read(),
        )
    coa = svc.ingest_coa(
        db, batch=batch, source=source, issuer_id=issuer_id, file=incoming, actor=user
    )
    db.commit()

    received = {
        "stage": "received",
        "coa_id": coa.id,
        "batch": _detail(db, batch, user).model_dump(mode="json"),
    }
    if _reading(coa):
        mode = get_settings().extraction_mode
        if mode == "inline":
            return _read_inline(db, coa, received)
        try:
            await worker.enqueue_extraction(coa.id)
        except (RedisError, OSError):
            if mode == "auto":  # no Redis: read it here instead
                return _read_inline(db, coa, received)
            coa.extraction_status = ExtractionStatus.FAILED
            coa.extraction_error = "The COA reader isn't running. Enter the values by hand."
            db.commit()
    return await _coa_stream(db, coa, [received], status_code=201)


def _read_inline(db: DbSession, coa: COADocument, received: dict) -> StreamingResponse:
    """Read the COA inside this request, streaming the worker's events."""

    async def stream() -> AsyncIterator[str]:
        """Yield progress events while the reading runs in a thread."""
        yield _sse(received)
        yield _sse(events.READING)
        task = asyncio.create_task(asyncio.to_thread(worker.extract_now, coa.id))
        while not task.done():
            await asyncio.wait({task}, timeout=15)
            if not task.done():
                yield ": still reading\n\n"
        db.expire_all()
        yield _sse(events.final_event(db.get(COADocument, coa.id)))

    return StreamingResponse(
        stream(),
        status_code=201,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/coas/{coa_id}/events", response_class=StreamingResponse)
async def coa_events(db: DbSession, _: Viewer, coa_id: int) -> StreamingResponse:
    """Re-attach to a COA's reading progress, e.g. after a page reload."""
    coa = db.get(COADocument, coa_id)
    if coa is None or coa.batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "COA not found")
    return await _coa_stream(db, coa, [])


@router.put("/coas/{coa_id}/data", response_model=BatchDetail)
def save_coa_data(db: DbSession, user: Uploader, coa_id: int, body: CoaDataIn) -> BatchDetail:
    """Save COA values typed or corrected by a person and re-check."""
    coa = db.get(COADocument, coa_id)
    if coa is None or coa.batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "COA not found")
    header = svc.CoaHeader(**body.model_dump(exclude={"results"}))
    rows = [svc.CoaRow(**r.model_dump()) for r in body.results]
    svc.save_coa_data(db, coa, header, rows, actor=user)
    db.commit()
    return _detail(db, coa.batch, user)


@router.get("/coas/{coa_id}/file")
def coa_file(db: DbSession, _: Viewer, coa_id: int) -> FileResponse:
    """Serve the uploaded COA file."""
    coa = db.get(COADocument, coa_id)
    if coa is None or not coa.storage_path or not Path(coa.storage_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No file for this COA")
    return FileResponse(
        coa.storage_path,
        media_type=coa.content_type or "application/octet-stream",
        filename=coa.original_filename,
        content_disposition_type="inline",
    )


Checker = Annotated[User, Depends(require(Permission.RUN_CHECK))]


@router.post("/batches/{batch_id}/copilot", response_model=CopilotOut)
def batch_copilot(db: DbSession, user: Checker, batch_id: int) -> CopilotOut:
    """Have Claude explain why the batch needs a person (changes nothing)."""
    batch = _get_batch(db, batch_id)
    try:
        result = copilot.review_batch(db, batch)
    except copilot.CopilotError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    audit.record(
        db,
        actor=user,
        action="copilot_brief",
        entity_type="batch",
        entity_id=batch.id,
        model=result.model,
        looked_at=result.looked_at,
        email_to=result.brief.email.to if result.brief.email else None,
        cited=[src.ref for src in result.sources],
    )
    db.commit()
    return CopilotOut(
        **result.brief.model_dump(exclude={"email", "sources"}),
        email=result.brief.email,
        sources=[CopilotSource(**vars(src)) for src in result.sources],
        looked_at=result.looked_at,
        model=result.model,
    )
