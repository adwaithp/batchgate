from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select

from app.api.deps import DbSession, require
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
from app.models.enums import BatchStatus, CoaSource, OrderStatus, SupplierKind
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
from app.services import batches as svc
from app.services.rules.engine import spec_text
from app.services.rules.types import ParamSpec

router = APIRouter(tags=["batches"])

Viewer = Annotated[User, Depends(require(Permission.VIEW_BATCHES))]
Uploader = Annotated[User, Depends(require(Permission.UPLOAD_COA))]


# ---- Mapping -----------------------------------------------------------------------------


def _line_out(line: OrderLine) -> LineOut:
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
    uploader = db.get(User, coa.uploaded_by_id) if coa.uploaded_by_id else None
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
        product_name=coa.product_name,
        cas_number=coa.cas_number,
        batch_number=coa.batch_number,
        po_reference=coa.po_reference,
        mfg_date=coa.mfg_date,
        test_date=coa.test_date,
        expiry_date=coa.expiry_date,
        results=coa.results,
    )


def _detail(db: DbSession, batch: Batch, user: User) -> BatchDetail:
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
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
    return batch


# ---- Routes ------------------------------------------------------------------------------


@router.get("/catalog/options", response_model=CatalogOptions)
def catalog_options(db: DbSession, _: Viewer) -> CatalogOptions:
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
    existing = db.scalar(
        select(Batch).where(
            Batch.factory_id == body.factory_id, Batch.batch_number == body.batch_number.strip()
        )
    )
    if existing:
        raise svc.WorkflowError(
            f"Batch {existing.batch_number} from this factory already exists (#{existing.id}).", 409
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
    return _detail(db, _get_batch(db, batch_id), user)


@router.post("/batches/{batch_id}/actions", response_model=BatchDetail)
def batch_action(db: DbSession, user: Viewer, batch_id: int, body: BatchActionIn) -> BatchDetail:
    batch = _get_batch(db, batch_id)
    svc.apply_action(db, batch, body.action, actor=user, note=body.note, line_id=body.line_id)
    db.commit()
    return _detail(db, batch, user)


@router.post("/batches/{batch_id}/coas", response_model=BatchDetail, status_code=201)
async def upload_coa(
    db: DbSession,
    user: Uploader,
    batch_id: int,
    source: Annotated[CoaSource, Form()],
    issuer_id: Annotated[int | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> BatchDetail:
    """Attach a COA to a batch. Without a file, it creates an entry to type values into."""
    batch = _get_batch(db, batch_id)
    incoming = None
    if file is not None and file.filename:
        incoming = svc.IncomingFile(
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            data=await file.read(),
        )
    svc.ingest_coa(db, batch=batch, source=source, issuer_id=issuer_id, file=incoming, actor=user)
    db.commit()
    return _detail(db, batch, user)


@router.put("/coas/{coa_id}/data", response_model=BatchDetail)
def save_coa_data(db: DbSession, user: Uploader, coa_id: int, body: CoaDataIn) -> BatchDetail:
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
    coa = db.get(COADocument, coa_id)
    if coa is None or not coa.storage_path or not Path(coa.storage_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No file for this COA")
    return FileResponse(
        coa.storage_path,
        media_type=coa.content_type or "application/octet-stream",
        filename=coa.original_filename,
        content_disposition_type="inline",
    )
