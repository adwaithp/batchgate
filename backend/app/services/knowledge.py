"""Knowledge base: documents split into sections, cases from resolved batches, search.

Search is BM25 over passages scoped to a customer and product, with queries expanded by the test
and product names the specs already know.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Batch,
    Customer,
    KnowledgeDocument,
    KnowledgePassage,
    Product,
    QCCase,
    SpecParameter,
    User,
)
from app.models.enums import BatchActionType, BatchStatus, CaseOutcome, Decision, DocumentKind
from app.services import audit
from app.services.batches import WorkflowError

MAX_PASSAGE_CHARS = 1200


_NUMBERED = re.compile(r"^(?:§\s*)?\d+(?:\.\d+)*[.)]?\s+\S")
_CLAUSE = re.compile(r"^(\d+\.\d+(?:\.\d+)*)\s+(\S.{20,})$")  # e.g. "4.2 Retests. When an ..."
_CLAUSE_TITLE = re.compile(r"^([A-Z][\w ,/'()-]{2,40}?)\.\s+(\S.*)$")
_NAMED = re.compile(r"^(?:section|clause|article|annex|appendix)\s+[\w.]+", re.IGNORECASE)


def _is_heading(line: str) -> bool:
    """Return True for a numbered or all-caps heading line."""
    line = line.strip()
    if not line or len(line) > 90 or line.endswith((".", ",", ";")):
        return False
    if _NUMBERED.match(line) or _NAMED.match(line):
        return True
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters) and len(line) <= 60


def split_sections(text: str) -> list[tuple[str | None, str]]:
    """Split a document into (heading, text) passages."""
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    parent: str | None = None
    for raw in text.replace("\r", "").split("\n"):
        line = raw.rstrip()
        clause = _CLAUSE.match(line.strip())
        if _is_heading(line):
            parent = line.strip()
            sections.append((parent, []))
        elif clause:
            # Numbered clauses are their own passages, cited by number and title.
            number, rest = clause.groups()
            titled = _CLAUSE_TITLE.match(rest)
            if titled:
                label, body = f"{number} {titled.group(1)}", titled.group(2)
            else:
                topic = re.sub(r"^(?:§\s*)?\d+(?:\.\d+)*[.)]?\s+", "", parent or "").strip()
                label, body = (f"{number} ({topic})" if topic else number), rest
            sections.append((label, [body]))
        else:
            sections[-1][1].append(line)

    pieces: list[tuple[str | None, str]] = []
    for heading, lines in sections:
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        if not body:
            continue
        for chunk in _cut(body):
            pieces.append((heading, chunk))
    return pieces


def _cut(body: str) -> list[str]:
    """Cut a long section at paragraph or sentence ends."""
    if len(body) <= MAX_PASSAGE_CHARS:
        return [body]
    parts = re.split(r"\n\s*\n|(?<=[.!?])\s+(?=[A-Z])", body)
    chunks, current = [], ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if current and len(current) + len(part) + 1 > MAX_PASSAGE_CHARS:
            chunks.append(current)
            current = part
        else:
            current = f"{current} {part}".strip() if current else part
    if current:
        chunks.append(current)
    return chunks


def document_text(path: Path, content_type: str) -> str:
    """Return a document's text from its PDF or text file."""
    if content_type == "application/pdf" or path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        try:
            return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        except Exception as e:
            raise WorkflowError("This PDF couldn't be opened.", 422) from e
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise WorkflowError("Upload a PDF or a plain text file.", 422) from e


ALLOWED_TYPES = {"application/pdf", "text/plain", "text/markdown"}


def add_document(
    db: Session,
    *,
    title: str,
    kind: DocumentKind,
    customer_id: int | None,
    product_id: int | None,
    filename: str,
    content_type: str,
    data: bytes | None = None,
    text: str | None = None,
    actor: User | None,
) -> KnowledgeDocument:
    """Store a document and its searchable passages."""
    title = (title or "").strip()
    if not title:
        raise WorkflowError("Give the document a title.", 422)
    if customer_id is not None and db.get(Customer, customer_id) is None:
        raise WorkflowError("Unknown customer.", 422)
    if product_id is not None and db.get(Product, product_id) is None:
        raise WorkflowError("Unknown product.", 422)

    storage_path = None
    if data is not None:
        if content_type not in ALLOWED_TYPES and not filename.lower().endswith((".txt", ".md")):
            raise WorkflowError("Upload a PDF or a plain text file.", 415)
        if len(data) > get_settings().max_upload_mb * 1024 * 1024:
            raise WorkflowError(f"Files are limited to {get_settings().max_upload_mb} MB.", 413)
        folder = Path(get_settings().upload_dir) / "knowledge"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{uuid4().hex}{Path(filename).suffix.lower()[:8]}"
        path.write_bytes(data)
        storage_path = str(path)
        text = document_text(path, content_type)

    pieces = split_sections(text or "")
    if not pieces:
        raise WorkflowError(
            "No text found in this document. A scanned PDF needs a text version for now.", 422
        )

    doc = KnowledgeDocument(
        title=title,
        kind=kind,
        customer_id=customer_id,
        product_id=product_id,
        original_filename=filename or None,
        content_type=content_type or None,
        storage_path=storage_path,
        uploaded_by_id=actor.id if actor else None,
        passages=[
            KnowledgePassage(
                position=i,
                section=heading[:255] if heading else None,
                text=body,
                customer_id=customer_id,
                product_id=product_id,
            )
            for i, (heading, body) in enumerate(pieces)
        ],
    )
    db.add(doc)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="knowledge_document_added",
        entity_type="knowledge",
        entity_id=doc.id,
        title=title,
        passages=len(pieces),
    )
    return doc


def case_text(case: QCCase) -> str:
    """Return a case's searchable text."""
    who = ", ".join(
        x
        for x in [
            case.product.name if case.product else None,
            f"made by {case.factory_name}" if case.factory_name else None,
            f"for {case.customer.name}" if case.customer else None,
        ]
        if x
    )
    return (
        f"Batch {case.batch_number} ({who}).\n"
        f"Problem: {case.problem}\n"
        f"What was done: {case.actions}\n"
        f"Outcome: {case.outcome.value} on {case.closed_on.isoformat()}."
    )


def save_case(db: Session, case: QCCase) -> QCCase:
    """Store a case and its passage."""
    db.add(case)
    db.flush()
    db.refresh(case)
    case.passages = [
        KnowledgePassage(
            position=0,
            section=f"Case {case.batch_number}",
            text=case_text(case),
            customer_id=case.customer_id,
            product_id=case.product_id,
        )
    ]
    db.flush()
    return case


def record_case(db: Session, batch: Batch) -> QCCase | None:
    """Remember a batch a person resolved, once released or rejected."""
    from app.services.batches import _ts, latest_verdict  # avoids a circular import

    outcome = {
        BatchStatus.RELEASED: CaseOutcome.RELEASED,
        BatchStatus.REJECTED: CaseOutcome.REJECTED,
    }
    if batch.status not in outcome:
        return None
    if db.scalar(select(QCCase.id).where(QCCase.batch_id == batch.id)):
        return None
    # Only batches a person resolved become cases.
    decisions = (BatchActionType.PROPOSE_RELEASE, BatchActionType.HOLD, BatchActionType.REJECT)
    human = [a for a in batch.actions if a.action in decisions and a.note]
    if batch.status == BatchStatus.RELEASED and not human:
        return None

    # Newest first; the relationship's list order depends on how it was loaded.
    flagged = sorted(
        (v for v in batch.verdicts if v.decision != Decision.RELEASE),
        key=lambda v: (_ts(v.created_at), v.id or 0),
        reverse=True,
    )
    worst = next((v for v in flagged if v.decision == Decision.HOLD), None) or (
        flagged[0] if flagged else latest_verdict(batch)
    )
    findings = (
        [
            f["message"]
            for f in (worst.details or {}).get("findings", [])
            if f.get("severity") in ("hold", "review")
        ]
        if worst
        else []
    )
    problem = "; ".join(findings[:4]) or (worst.summary if worst else "Released by a person.")
    actions = (
        " ".join(
            f"{a.actor.full_name if a.actor else 'Someone'} "
            f"({a.action.value.replace('_', ' ')}): {a.note}"
            for a in human
        )
        or "No notes were written."
    )
    return save_case(
        db,
        QCCase(
            batch_id=batch.id,
            batch_number=batch.batch_number,
            customer_id=batch.line.order.customer_id if batch.line else None,
            product_id=batch.product_id,
            factory_name=batch.factory.name if batch.factory else None,
            problem=problem,
            actions=actions,
            outcome=outcome[batch.status],
            closed_on=datetime.now(UTC).date(),
            source="batchgate",
        ),
    )


_STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "must",
    "no",
    "not",
    "of",
    "on",
    "or",
    "our",
    "shall",
    "should",
    "so",
    "such",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "under",
    "was",
    "we",
    "were",
    "what",
    "when",
    "which",
    "who",
    "will",
    "with",
    "would",
    "you",
    "your",
    "batch",
    "batches",
}


def tokens(text: str) -> list[str]:
    """Return lowercase, singular search tokens without stop words."""
    out = []
    for w in re.findall(r"[a-z0-9]+(?:[.][0-9]+)?", text.lower()):
        if w in _STOP or len(w) == 1 and not w.isdigit():
            continue
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def synonym_groups(db: Session, product_id: int | None = None) -> list[set[str]]:
    """Return groups of names the specs and products know for one thing."""
    groups: list[set[str]] = []
    q = select(SpecParameter)
    if product_id is not None:
        from app.models import Spec

        q = q.join(Spec).where(Spec.product_id == product_id)
    for p in db.scalars(q):
        names = {p.name.lower(), *(a.lower() for a in (p.aliases or []))}
        groups.append({n for n in names if n})
    for prod in db.scalars(select(Product)):
        groups.append({prod.name.lower(), *(s.lower() for s in (prod.synonyms or []))})
    return groups


def expand(query: str, groups: list[set[str]]) -> dict[str, float]:
    """Return query tokens weighted 1.0, with known synonyms at 0.5."""
    weights: dict[str, float] = dict.fromkeys(tokens(query), 1.0)
    padded = f" {' '.join(tokens(query))} "
    for group in groups:
        if any(f" {' '.join(tokens(name))} " in padded for name in group if tokens(name)):
            for name in group:
                for t in tokens(name):
                    weights.setdefault(t, 0.5)
    return weights


@dataclass
class Hit:
    """A search result."""

    passage: KnowledgePassage
    score: float
    matched: list[str] = field(default_factory=list)

    @property
    def ref(self) -> str:
        """Return the citation ref, e.g. K12 for passage 12."""
        return f"K{self.passage.id}"

    @property
    def source(self) -> str:
        """Return a readable source label."""
        p = self.passage
        if p.document is not None:
            return f"{p.document.title}" + (f", {p.section}" if p.section else "")
        if p.case is not None:
            return f"Past case {p.case.batch_number} ({p.case.outcome.value})"
        return "Knowledge base"

    @property
    def link(self) -> str:
        """Return the in-app link to the passage."""
        p = self.passage
        if p.document_id:
            return f"/knowledge/documents/{p.document_id}#p{p.id}"
        return f"/knowledge?tab=cases#case-{p.case_id}"


def search(
    db: Session,
    query: str,
    *,
    customer_id: int | None = None,
    product_id: int | None = None,
    kinds: set[str] | None = None,
    limit: int = 5,
    expand_synonyms: bool = True,
) -> list[Hit]:
    """Rank passages for this customer and product (or everyone) with BM25."""
    q = (
        select(KnowledgePassage)
        .outerjoin(KnowledgeDocument)
        .where(or_(KnowledgePassage.document_id.is_(None), KnowledgeDocument.archived.is_(False)))
    )
    if customer_id is not None:
        q = q.where(
            or_(
                KnowledgePassage.customer_id.is_(None), KnowledgePassage.customer_id == customer_id
            )
        )
    if product_id is not None:
        q = q.where(
            or_(KnowledgePassage.product_id.is_(None), KnowledgePassage.product_id == product_id)
        )
    if kinds == {"document"}:
        q = q.where(KnowledgePassage.document_id.is_not(None))
    elif kinds == {"case"}:
        q = q.where(KnowledgePassage.case_id.is_not(None))
    passages = list(db.scalars(q))
    if not passages:
        return []

    weights = (
        expand(query, synonym_groups(db, product_id))
        if expand_synonyms
        else dict.fromkeys(tokens(query), 1.0)
    )
    if not weights:
        return []
    docs = []
    for p in passages:
        title = p.document.title if p.document else ""
        # heading words count double
        docs.append(Counter(tokens(f"{title} {p.section or ''} {p.section or ''} {p.text}")))
    n = len(docs)
    avg = sum(sum(d.values()) for d in docs) / n
    df = Counter(t for d in docs for t in set(d))
    k1, b = 1.5, 0.75

    hits = []
    for p, d in zip(passages, docs, strict=True):
        length = sum(d.values())
        score, matched = 0.0, []
        for t, w in weights.items():
            f = d.get(t, 0)
            if not f:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += w * idf * f * (k1 + 1) / (f + k1 * (1 - b + b * length / avg))
            matched.append(t)
        # on a tie, a passage for this customer or product wins
        if score and customer_id is not None and p.customer_id == customer_id:
            score *= 1.15
        if score:
            hits.append(Hit(p, round(score, 3), matched))
    hits.sort(key=lambda h: (-h.score, h.passage.id))
    return hits[:limit]
