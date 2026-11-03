"""Audit log API (read-only, newest first)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.permissions import Permission
from app.models import (
    AuditLog,
    Batch,
    COADocument,
    Customer,
    KnowledgeDocument,
    Order,
    Spec,
    User,
)
from app.schemas.audit import AuditEntry, AuditPage

router = APIRouter(prefix="/audit", tags=["audit"])

Auditor = Annotated[User, Depends(require(Permission.VIEW_AUDIT_LOG))]

# Entity types covered by each filter.
GROUPS = {
    "batch": ["batch", "coa"],
    "order": ["order", "customer"],
    "spec": ["spec"],
    "user": ["user"],
    "knowledge": ["knowledge"],
}


def _describe(db, entry: AuditLog) -> tuple[str | None, str | None]:
    """Return a readable label and an in-app link for the audited entity."""
    if entry.entity_id is None:
        return None, None
    match entry.entity_type:
        case "batch":
            b = db.get(Batch, entry.entity_id)
            return (b.batch_number, f"/batches/{b.id}") if b else (None, None)
        case "coa":
            c = db.get(COADocument, entry.entity_id)
            if c and c.batch:
                return f"{c.batch.batch_number} · {c.source.value} COA", f"/batches/{c.batch.id}"
        case "order":
            o = db.get(Order, entry.entity_id)
            return (o.po_number, f"/orders/{o.id}") if o else (None, None)
        case "spec":
            s = db.get(Spec, entry.entity_id)
            if s:
                return f"{s.product.name} · {s.grade} v{s.version}", f"/specs/{s.id}"
        case "knowledge":
            d = db.get(KnowledgeDocument, entry.entity_id)
            return (d.title, f"/knowledge/documents/{d.id}") if d else (None, None)
        case "customer":
            c = db.get(Customer, entry.entity_id)
            return (c.name, None) if c else (None, None)
        case "user":
            u = db.get(User, entry.entity_id)
            return (u.full_name, None) if u else (None, None)
    return None, None


@router.get("", response_model=AuditPage)
def list_audit(
    db: DbSession,
    _: Auditor,
    kind: Annotated[str | None, Query(description="batch, order, spec, user or knowledge")] = None,
    before: Annotated[int | None, Query(description="only entries older than this id")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    """List audit entries, newest first, optionally filtered by kind."""
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit + 1)
    if kind in GROUPS:
        q = q.where(AuditLog.entity_type.in_(GROUPS[kind]))
    if before is not None:
        q = q.where(AuditLog.id < before)
    rows = list(db.scalars(q))
    more = len(rows) > limit
    rows = rows[:limit]

    names = {u.id: u.full_name for u in db.scalars(select(User))}
    entries = []
    for e in rows:
        label, link = _describe(db, e)
        entries.append(
            AuditEntry(
                id=e.id,
                at=e.created_at,
                actor=names.get(e.actor_id) if e.actor_id else None,
                action=e.action,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                entity_label=label,
                link=link,
                data=e.data or {},
            )
        )
    return AuditPage(entries=entries, next_before=rows[-1].id if more and rows else None)
