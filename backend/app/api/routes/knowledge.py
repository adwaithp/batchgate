"""Knowledge base API: documents, past cases and search."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import DbSession, require
from app.core.permissions import Permission, permissions_for
from app.models import KnowledgeDocument, KnowledgePassage, QCCase, User
from app.models.enums import DocumentKind
from app.schemas.knowledge import (
    CaseOut,
    DocumentDetail,
    DocumentSummary,
    KnowledgeOverview,
    PassageOut,
    SearchHit,
)
from app.services import audit
from app.services import knowledge as kb

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

Reader = Annotated[User, Depends(require(Permission.VIEW_KNOWLEDGE))]
Editor = Annotated[User, Depends(require(Permission.EDIT_KNOWLEDGE))]


def _summary(db: DbSession, d: KnowledgeDocument) -> DocumentSummary:
    """Map a document to its list view."""
    count = db.scalar(
        select(func.count(KnowledgePassage.id)).where(KnowledgePassage.document_id == d.id)
    )
    added_by = db.get(User, d.uploaded_by_id) if d.uploaded_by_id else None
    return DocumentSummary(
        id=d.id,
        title=d.title,
        kind=d.kind,
        customer=d.customer.name if d.customer else None,
        product=d.product.name if d.product else None,
        passages=count or 0,
        has_file=bool(d.storage_path),
        added_by=added_by.full_name if added_by else None,
        created_at=d.created_at,
    )


def _case(c: QCCase) -> CaseOut:
    """Map a past case to its API view."""
    return CaseOut(
        id=c.id,
        batch_number=c.batch_number,
        batch_id=c.batch_id,
        customer=c.customer.name if c.customer else None,
        product=c.product.name if c.product else None,
        factory=c.factory_name,
        problem=c.problem,
        actions=c.actions,
        outcome=c.outcome,
        closed_on=c.closed_on,
        source=c.source,
    )


def _can_edit(user: User) -> bool:
    """Return True when `user` may add or archive documents."""
    return Permission.EDIT_KNOWLEDGE in permissions_for(user.role)


@router.get("", response_model=KnowledgeOverview)
def overview(db: DbSession, user: Reader) -> KnowledgeOverview:
    """List active documents and past cases."""
    docs = db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.archived.is_(False))
        .order_by(KnowledgeDocument.title)
    )
    cases = db.scalars(select(QCCase).order_by(QCCase.closed_on.desc(), QCCase.id.desc()))
    return KnowledgeOverview(
        documents=[_summary(db, d) for d in docs],
        cases=[_case(c) for c in cases],
        can_edit=_can_edit(user),
    )


@router.get("/search", response_model=list[SearchHit])
def search(
    db: DbSession,
    _: Reader,
    q: Annotated[str, Query(min_length=2, max_length=300)],
    customer_id: int | None = None,
    product_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[SearchHit]:
    """Search documents and cases, scoped to a customer and product."""
    hits = kb.search(db, q, customer_id=customer_id, product_id=product_id, limit=limit)
    return [
        SearchHit(
            ref=h.ref,
            score=h.score,
            source=h.source,
            kind="document" if h.passage.document_id else "case",
            section=h.passage.section,
            text=h.passage.text,
            link=h.link,
            matched=h.matched,
        )
        for h in hits
    ]


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
def get_document(db: DbSession, user: Reader, doc_id: int) -> DocumentDetail:
    """Return a document with its searchable passages."""
    d = db.get(KnowledgeDocument, doc_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return DocumentDetail(
        **_summary(db, d).model_dump(),
        passages_list=[
            PassageOut(id=p.id, ref=f"K{p.id}", section=p.section, text=p.text) for p in d.passages
        ],
        can_edit=_can_edit(user) and not d.archived,
    )


@router.get("/documents/{doc_id}/file")
def document_file(db: DbSession, _: Reader, doc_id: int) -> FileResponse:
    """Serve a document's original file."""
    d = db.get(KnowledgeDocument, doc_id)
    if d is None or not d.storage_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No file for this document")
    return FileResponse(
        d.storage_path, media_type=d.content_type, filename=d.original_filename or "document"
    )


@router.post("/documents", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
async def upload_document(
    db: DbSession,
    user: Editor,
    title: Annotated[str, Form(max_length=255)],
    kind: Annotated[DocumentKind, Form()],
    file: Annotated[UploadFile, File()],
    customer_id: Annotated[int | None, Form()] = None,
    product_id: Annotated[int | None, Form()] = None,
) -> DocumentDetail:
    """Add a document (PDF or text) to the knowledge base."""
    doc = kb.add_document(
        db,
        title=title,
        kind=kind,
        customer_id=customer_id,
        product_id=product_id,
        filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        data=await file.read(),
        actor=user,
    )
    db.commit()
    return get_document(db, user, doc.id)


@router.post("/documents/{doc_id}/archive", response_model=DocumentSummary)
def archive_document(db: DbSession, user: Editor, doc_id: int) -> DocumentSummary:
    """Remove a document from search; past citations still open."""
    d = db.get(KnowledgeDocument, doc_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    d.archived = True
    audit.record(
        db, actor=user, action="knowledge_document_archived", entity_type="knowledge",
        entity_id=d.id, title=d.title,
    )  # fmt: skip
    db.commit()
    return _summary(db, d)
