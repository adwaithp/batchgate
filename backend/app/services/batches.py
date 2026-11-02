"""Batch workflow: COAs in, checks run, people decide.

Every way a COA can arrive (upload today; email, ERP or MCP later) goes through ingest_coa().
Every way a check can be triggered goes through run_check(). Nothing else writes verdicts.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import Permission, permissions_for
from app.models import (
    Batch,
    BatchAction,
    COADocument,
    COAResult,
    Order,
    OrderLine,
    Spec,
    Supplier,
    User,
    Verdict,
)
from app.models.enums import (
    BatchActionType,
    BatchStatus,
    CoaSource,
    Decision,
    ExtractionStatus,
    OrderStatus,
    SupplierKind,
)
from app.services import audit
from app.services.rules.engine import ENGINE_VERSION, check_batch
from app.services.rules.matching import match_results
from app.services.rules.types import (
    BatchInput,
    CoaInput,
    EngineConfig,
    EngineResult,
    ParamSpec,
    ResultInput,
    SpecInput,
)


class WorkflowError(Exception):
    """A request that breaks a business rule. Routes turn it into a 4xx with this message."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


TERMINAL = {BatchStatus.RELEASED, BatchStatus.REJECTED}

DECISION_TO_STATUS = {
    # A clean result skips the analyst, but a QC manager still approves.
    Decision.RELEASE: BatchStatus.PENDING_APPROVAL,
    Decision.REVIEW: BatchStatus.PENDING_REVIEW,
    Decision.HOLD: BatchStatus.ON_HOLD,
}


# ---- ORM -> engine inputs ----------------------------------------------------------------


def engine_config() -> EngineConfig:
    s = get_settings()
    return EngineConfig(
        require_lab_coa=s.require_lab_coa,
        default_tolerance_pct=s.default_tolerance_pct,
        low_confidence=s.low_confidence_threshold,
    )


def spec_input(spec: Spec) -> SpecInput:
    return SpecInput(
        product_name=spec.product.name,
        cas_number=spec.product.cas_number,
        product_synonyms=list(spec.product.synonyms or []),
        parameters=[
            ParamSpec(
                id=p.id,
                name=p.name,
                rule_type=p.rule_type,
                low=p.low,
                high=p.high,
                unit=p.unit,
                expected_text=p.expected_text,
                aliases=list(p.aliases or []),
                critical=p.critical,
                tolerance_pct=p.tolerance_pct,
                tolerance_abs=p.tolerance_abs,
            )
            for p in spec.parameters
        ],
    )


def active_coas(batch: Batch) -> list[COADocument]:
    """The latest COA per source whose values are in. Older or empty ones don't count."""
    return [
        c for c in batch.coas if not c.superseded and c.extraction_status == ExtractionStatus.DONE
    ]


def batch_input(batch: Batch) -> BatchInput:
    return BatchInput(
        batch_number=batch.batch_number,
        coas=[
            CoaInput(
                id=c.id,
                source=c.source,
                issuer_name=c.issuer.name if c.issuer else c.issuer_name,
                product_name=c.product_name,
                cas_number=c.cas_number,
                batch_number=c.batch_number,
                mfg_date=c.mfg_date,
                test_date=c.test_date,
                expiry_date=c.expiry_date,
                results=[
                    ResultInput(
                        name_as_written=r.name_as_written,
                        raw_value=r.raw_value,
                        unit=r.unit,
                        confidence=r.confidence,
                        parameter_id=r.matched_parameter_id,
                    )
                    for r in c.results
                ],
            )
            for c in active_coas(batch)
        ],
    )


# ---- Checks ------------------------------------------------------------------------------


def _ts(dt: datetime) -> datetime:
    """SQLite drops time zones on read; compare everything as naive UTC."""
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def latest_verdict(batch: Batch) -> Verdict | None:
    return max(batch.verdicts, key=lambda v: (_ts(v.created_at), v.id or 0), default=None)


def run_check(db: Session, batch: Batch, *, actor: User | None = None) -> Verdict | None:
    """Re-evaluate a batch and move it to the status the verdict implies.

    No verdict is written when there is nothing to check against (no line, so no spec) or
    nothing to check (no COA values yet).
    """
    if batch.status in TERMINAL:
        raise WorkflowError(f"Batch {batch.batch_number} is {batch.status.value}; it is closed.")

    previous = batch.status
    if not active_coas(batch):
        batch.status = BatchStatus.AWAITING_COA
        verdict = None
    elif batch.line is None:
        batch.status = BatchStatus.PENDING_REVIEW  # a person must assign the line first
        verdict = None
    else:
        spec = spec_input(batch.line.spec)
        _record_matches(batch, spec)
        result = check_batch(spec, batch_input(batch), config=engine_config())
        details = json.loads(json.dumps(result.to_dict(), default=str))
        previous_verdict = latest_verdict(batch)
        if (
            previous_verdict is not None
            and previous_verdict.spec_id == batch.line.spec_id
            and previous_verdict.engine_version == ENGINE_VERSION
            and previous_verdict.details == details
        ):
            verdict = previous_verdict  # nothing changed: keep the history readable
        else:
            verdict = Verdict(
                batch=batch,
                spec_id=batch.line.spec_id,
                decision=result.decision,
                summary=result.summary,
                details=details,
                engine_version=ENGINE_VERSION,
            )
            db.add(verdict)
        batch.status = DECISION_TO_STATUS[result.decision]

    db.flush()
    audit.record(
        db,
        actor=actor,
        action="check_run",
        entity_type="batch",
        entity_id=batch.id,
        decision=verdict.decision.value if verdict else None,
        status_from=previous.value,
        status_to=batch.status.value,
    )
    if batch.line:
        recompute_order_status(batch.line.order)
    return verdict


def _record_matches(batch: Batch, spec: SpecInput) -> None:
    """Remember which spec parameter each COA row is evidence for (shown in the entry form)."""
    valid = {p.id for p in spec.parameters}
    for coa in active_coas(batch):
        for row in coa.results:
            if row.matched_parameter_id not in valid:
                row.matched_parameter_id = None
        inputs = [
            ResultInput(
                r.name_as_written, r.raw_value, r.unit, r.confidence, r.matched_parameter_id
            )
            for r in coa.results
        ]
        matched, _ = match_results(spec.parameters, inputs)
        for pid, ri in matched.items():
            idx = next(i for i, x in enumerate(inputs) if x is ri)
            coa.results[idx].matched_parameter_id = pid


@dataclass
class LineSuggestion:
    line: OrderLine
    decision: Decision
    summary: str
    failing: list[str]


def suggest_lines(db: Session, batch: Batch) -> list[LineSuggestion]:
    """For a batch with no order line: which open lines could it be, and does it fit their spec?

    Suggestions only. A person confirms, because shipping the wrong grade is worse than waiting.
    """
    coas = active_coas(batch)
    if not coas:
        return []

    q = (
        select(OrderLine)
        .join(Order)
        .where(OrderLine.product_id == batch.product_id, Order.status != OrderStatus.SHIPPED)
    )
    lines = list(db.scalars(q))

    po_refs = {c.po_reference.strip().upper() for c in coas if c.po_reference}
    if po_refs:
        referenced = [ln for ln in lines if ln.order.po_number.upper() in po_refs]
        lines = referenced or lines

    data = batch_input(batch)
    rank = {Decision.RELEASE: 0, Decision.REVIEW: 1, Decision.HOLD: 2}
    out: list[LineSuggestion] = []
    for line in lines:
        result: EngineResult = check_batch(spec_input(line.spec), data, config=engine_config())
        failing = [p.name for p in result.parameters if p.status.value == "fail"]
        out.append(LineSuggestion(line, result.decision, result.summary, failing))
    return sorted(out, key=lambda s: (rank[s.decision], len(s.failing), s.line.id))


# ---- Ingest ------------------------------------------------------------------------------


@dataclass
class IncomingFile:
    filename: str
    content_type: str
    data: bytes


ALLOWED_TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}


def _store(file: IncomingFile) -> tuple[str, str]:
    settings = get_settings()
    if file.content_type not in ALLOWED_TYPES:
        raise WorkflowError("Upload a PDF, PNG or JPEG file.", 415)
    if len(file.data) > settings.max_upload_mb * 1024 * 1024:
        raise WorkflowError(f"File is larger than {settings.max_upload_mb} MB.", 413)
    if not file.data:
        raise WorkflowError("The file is empty.", 400)

    digest = hashlib.sha256(file.data).hexdigest()
    folder = Path(settings.upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest}{ALLOWED_TYPES[file.content_type]}"
    if not path.exists():
        path.write_bytes(file.data)
    return str(path), digest


def get_or_create_batch(
    db: Session,
    *,
    batch_number: str,
    product_id: int,
    factory_id: int,
    line_id: int | None = None,
    quantity: float | None = None,
    actor: User | None = None,
) -> Batch:
    batch_number = batch_number.strip()
    if not batch_number:
        raise WorkflowError("Batch number is required.", 422)

    factory = db.get(Supplier, factory_id)
    if factory is None or factory.kind != SupplierKind.FACTORY:
        raise WorkflowError("Choose the partner factory that made this batch.", 422)

    batch = db.scalar(
        select(Batch).where(Batch.factory_id == factory_id, Batch.batch_number == batch_number)
    )
    if batch is not None:
        if batch.product_id != product_id:
            raise WorkflowError(
                f"{factory.name} batch {batch_number} is already registered as "
                f"{batch.product.name}.",
                409,
            )
        return batch

    line = None
    if line_id is not None:
        line = db.get(OrderLine, line_id)
        if line is None or line.product_id != product_id:
            raise WorkflowError("That order line is for a different product.", 422)

    batch = Batch(
        batch_number=batch_number,
        product_id=product_id,
        factory_id=factory_id,
        line=line,
        quantity=quantity,
        status=BatchStatus.AWAITING_COA,
    )
    db.add(batch)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="batch_created",
        entity_type="batch",
        entity_id=batch.id,
        batch_number=batch_number,
        line_id=line_id,
    )
    return batch


def ingest_coa(
    db: Session,
    *,
    batch: Batch,
    source: CoaSource,
    issuer_id: int | None,
    file: IncomingFile | None,
    actor: User | None,
    origin: str = "upload",
) -> COADocument:
    """The single way a COA enters BatchGate. Later: the model reads it here, then run_check()."""
    if batch.status in TERMINAL:
        raise WorkflowError(f"Batch {batch.batch_number} is {batch.status.value}; it is closed.")

    if issuer_id is not None:
        issuer = db.get(Supplier, issuer_id)
        expected = SupplierKind.LAB if source == CoaSource.LAB else SupplierKind.FACTORY
        if issuer is None or issuer.kind != expected:
            raise WorkflowError(
                "A lab COA must come from a lab, and a factory COA from a factory.", 422
            )
    elif source == CoaSource.FACTORY:
        issuer_id = batch.factory_id

    storage_path = digest = None
    if file is not None:
        storage_path, digest = _store(file)
        if any(c.sha256 == digest for c in batch.coas):
            raise WorkflowError("This file is already attached to this batch.", 409)

    for old in batch.coas:
        if old.source == source and not old.superseded:
            old.superseded = True

    coa = COADocument(
        batch=batch,
        source=source,
        issuer_id=issuer_id,
        origin=origin if file is not None else "manual",
        original_filename=file.filename if file else None,
        content_type=file.content_type if file else None,
        storage_path=storage_path,
        sha256=digest,
        uploaded_by_id=actor.id if actor else None,
        extraction_status=ExtractionStatus.PENDING,
    )
    db.add(coa)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="coa_received",
        entity_type="coa",
        entity_id=coa.id,
        batch_id=batch.id,
        source=source.value,
        origin=coa.origin,
        filename=coa.original_filename,
    )
    # The COA has no values yet, so the batch waits for them (or for the extractor).
    run_check(db, batch, actor=actor)
    return coa


@dataclass
class CoaHeader:
    product_name: str | None = None
    cas_number: str | None = None
    batch_number: str | None = None
    po_reference: str | None = None
    mfg_date: date | None = None
    test_date: date | None = None
    expiry_date: date | None = None


@dataclass
class CoaRow:
    name_as_written: str
    raw_value: str
    unit: str | None = None
    method: str | None = None
    confidence: float = 1.0
    parameter_id: int | None = None


def save_coa_data(
    db: Session,
    coa: COADocument,
    header: CoaHeader,
    rows: list[CoaRow],
    *,
    actor: User | None,
    model: str | None = None,
) -> Verdict | None:
    """Store the values read off a COA (typed by a person now, by the model later) and re-check."""
    batch = coa.batch
    if batch.status in TERMINAL:
        raise WorkflowError(f"Batch {batch.batch_number} is {batch.status.value}; it is closed.")
    if coa.superseded:
        raise WorkflowError("A newer COA from this source has replaced this one.")

    for field_name, value in vars(header).items():
        setattr(coa, field_name, value.strip() if isinstance(value, str) else value)

    coa.results = [
        COAResult(
            name_as_written=r.name_as_written.strip(),
            raw_value=r.raw_value.strip(),
            unit=(r.unit or "").strip() or None,
            method=r.method,
            confidence=r.confidence,
            matched_parameter_id=r.parameter_id,
        )
        for r in rows
        if r.raw_value and r.raw_value.strip()
    ]
    coa.extraction_status = ExtractionStatus.DONE
    coa.extraction_model = model or "manual"
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="coa_data_saved",
        entity_type="coa",
        entity_id=coa.id,
        rows=len(coa.results),
        by=coa.extraction_model,
    )
    return run_check(db, batch, actor=actor)


# ---- Human decisions ---------------------------------------------------------------------


@dataclass(frozen=True)
class ActionRule:
    permission: Permission
    from_statuses: frozenset[BatchStatus]
    to_status: BatchStatus | None  # None: decided by a re-check
    note_required: bool


ACTION_RULES: dict[BatchActionType, ActionRule] = {
    BatchActionType.PROPOSE_RELEASE: ActionRule(
        Permission.PROPOSE_RELEASE,
        frozenset({BatchStatus.PENDING_REVIEW, BatchStatus.ON_HOLD}),
        BatchStatus.PENDING_APPROVAL,
        note_required=True,  # always overrides the engine, so say why
    ),
    BatchActionType.APPROVE_RELEASE: ActionRule(
        Permission.APPROVE_RELEASE,
        frozenset({BatchStatus.PENDING_APPROVAL}),
        BatchStatus.RELEASED,
        note_required=False,
    ),
    BatchActionType.HOLD: ActionRule(
        Permission.HOLD_BATCH,
        frozenset(
            {BatchStatus.AWAITING_COA, BatchStatus.PENDING_REVIEW, BatchStatus.PENDING_APPROVAL}
        ),
        BatchStatus.ON_HOLD,
        note_required=True,
    ),
    BatchActionType.REJECT: ActionRule(
        Permission.REJECT_BATCH,
        frozenset({BatchStatus.PENDING_REVIEW, BatchStatus.ON_HOLD, BatchStatus.PENDING_APPROVAL}),
        BatchStatus.REJECTED,
        note_required=True,
    ),
    BatchActionType.ASSIGN_LINE: ActionRule(
        Permission.RUN_CHECK,
        frozenset(set(BatchStatus) - TERMINAL),
        None,
        note_required=False,
    ),
    BatchActionType.RERUN_CHECK: ActionRule(
        Permission.RUN_CHECK,
        frozenset(set(BatchStatus) - TERMINAL),
        None,
        note_required=False,
    ),
}


def _release_proposer(batch: Batch) -> User | None:
    """Who proposed the pending release, if a person did (not the engine)."""
    verdict = latest_verdict(batch)
    since = verdict.created_at if verdict else None
    for action in reversed(batch.actions):
        if since and _ts(action.created_at) < _ts(since):
            break
        if action.action == BatchActionType.PROPOSE_RELEASE:
            return action.actor
    return None


def blocked_reason(batch: Batch, action: BatchActionType, user: User) -> str | None:
    """Why `user` can't take `action` right now, or None if they can."""
    rule = ACTION_RULES[action]
    if rule.permission not in permissions_for(user.role):
        return "Your role can't do this."
    if batch.status not in rule.from_statuses:
        return f"Not possible while the batch is {batch.status.value.replace('_', ' ')}."
    if action == BatchActionType.PROPOSE_RELEASE and latest_verdict(batch) is None:
        return "Run a check first."
    if action == BatchActionType.APPROVE_RELEASE:
        proposer = _release_proposer(batch)
        if proposer is not None and proposer.id == user.id:
            return "You proposed this release; another QC manager has to approve it."
    return None


def allowed_actions(batch: Batch, user: User) -> list[BatchActionType]:
    return [a for a in ACTION_RULES if blocked_reason(batch, a, user) is None]


def apply_action(
    db: Session,
    batch: Batch,
    action: BatchActionType,
    *,
    actor: User,
    note: str | None = None,
    line_id: int | None = None,
) -> Batch:
    reason = blocked_reason(batch, action, actor)
    if reason:
        raise WorkflowError(reason, 403 if reason == "Your role can't do this." else 409)

    rule = ACTION_RULES[action]
    note = (note or "").strip() or None
    if rule.note_required and not note:
        raise WorkflowError("Add a note explaining this decision.", 422)

    previous = batch.status
    verdict = latest_verdict(batch)

    if action == BatchActionType.ASSIGN_LINE:
        line = db.get(OrderLine, line_id) if line_id is not None else None
        if line is None or line.product_id != batch.product_id:
            raise WorkflowError("Choose an order line for the same product.", 422)
        old_order = batch.line.order if batch.line else None
        batch.line = line
        db.flush()
        if old_order is not None:
            recompute_order_status(old_order)

    db.add(
        BatchAction(
            batch=batch,
            action=action,
            actor_id=actor.id,
            note=note,
            verdict_id=verdict.id if verdict else None,
        )
    )

    if rule.to_status is not None:
        batch.status = rule.to_status
        db.flush()
        if batch.line:
            recompute_order_status(batch.line.order)
    else:
        db.flush()
        run_check(db, batch, actor=actor)

    audit.record(
        db,
        actor=actor,
        action=f"batch_{action.value}",
        entity_type="batch",
        entity_id=batch.id,
        status_from=previous.value,
        status_to=batch.status.value,
        note=note,
        line_id=line_id,
    )
    return batch


# ---- Orders ------------------------------------------------------------------------------


def released_quantity(line: OrderLine) -> float:
    return sum(b.quantity or 0 for b in line.batches if b.status == BatchStatus.RELEASED)


def line_is_ready(line: OrderLine) -> bool:
    return released_quantity(line) >= line.quantity - 1e-9


def recompute_order_status(order: Order) -> None:
    if order.status == OrderStatus.SHIPPED:
        return
    ready = [line_is_ready(line) for line in order.lines]
    if ready and all(ready):
        order.status = OrderStatus.READY
    elif any(ready):
        order.status = OrderStatus.PARTIALLY_READY
    else:
        order.status = OrderStatus.OPEN
