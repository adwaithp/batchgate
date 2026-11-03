"""Knowledge base schemas."""

from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import CaseOutcome, DocumentKind


class DocumentSummary(BaseModel):
    """A knowledge base document in lists."""

    id: int
    title: str
    kind: DocumentKind
    customer: str | None
    product: str | None
    passages: int
    has_file: bool
    added_by: str | None
    created_at: datetime


class PassageOut(BaseModel):
    """A searchable passage of a document."""

    id: int
    ref: str
    section: str | None
    text: str


class DocumentDetail(DocumentSummary):
    """A document with its passages."""

    passages_list: list[PassageOut]
    can_edit: bool


class CaseOut(BaseModel):
    """A past case."""

    id: int
    batch_number: str
    batch_id: int | None
    customer: str | None
    product: str | None
    factory: str | None
    problem: str
    actions: str
    outcome: CaseOutcome
    closed_on: date
    source: str


class SearchHit(BaseModel):
    """A search result with the words it matched."""

    ref: str
    score: float
    source: str
    kind: str  # "document" or "case"
    section: str | None
    text: str
    link: str
    matched: list[str]


class KnowledgeOverview(BaseModel):
    """All active documents and past cases."""

    documents: list[DocumentSummary]
    cases: list[CaseOut]
    can_edit: bool
