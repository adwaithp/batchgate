"""Orders, batches, COA documents, verdicts and the human decisions taken on them.

Customer ─< Order ─< OrderLine (product + spec) ─< Batch ─< COADocument ─< COAResult
                                                        └─< Verdict (engine)
                                                        └─< BatchAction (humans)
"""

from datetime import date, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.catalog import Customer, Product, Spec, SpecParameter, Supplier
from app.models.enums import (
    BatchActionType,
    BatchStatus,
    CoaSource,
    Decision,
    ExtractionStatus,
    OrderStatus,
)
from app.models.mixins import TimestampMixin, str_enum, utcnow


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_date: Mapped[date]
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus), default=OrderStatus.OPEN)

    customer: Mapped[Customer] = relationship(lazy="joined")
    lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderLine.line_no",
        lazy="selectin",
    )


class OrderLine(Base):
    """One product on a PO. The same product can appear on several lines (e.g. two grades)."""

    __tablename__ = "order_lines"
    __table_args__ = (UniqueConstraint("order_id", "line_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int]
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id"))
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16), default="t")

    order: Mapped[Order] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(lazy="joined")
    spec: Mapped[Spec] = relationship(lazy="joined")
    batches: Mapped[list["Batch"]] = relationship(back_populates="line", lazy="selectin")


class Batch(TimestampMixin, Base):
    __tablename__ = "batches"
    __table_args__ = (UniqueConstraint("factory_id", "batch_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_number: Mapped[str] = mapped_column(String(64), index=True)
    # Nullable: a COA can arrive before anyone knows which order line it belongs to.
    line_id: Mapped[int | None] = mapped_column(ForeignKey("order_lines.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    factory_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16), default="t")
    status: Mapped[BatchStatus] = mapped_column(
        str_enum(BatchStatus), default=BatchStatus.AWAITING_COA
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    line: Mapped[OrderLine | None] = relationship(back_populates="batches")
    product: Mapped[Product] = relationship(lazy="joined")
    factory: Mapped[Supplier | None] = relationship(lazy="joined")
    coas: Mapped[list["COADocument"]] = relationship(
        back_populates="batch", order_by="COADocument.id", lazy="selectin"
    )
    verdicts: Mapped[list["Verdict"]] = relationship(
        back_populates="batch", order_by="Verdict.created_at.desc()", lazy="selectin"
    )
    actions: Mapped[list["BatchAction"]] = relationship(
        back_populates="batch", order_by="BatchAction.id", lazy="selectin"
    )


class COADocument(Base):
    """An uploaded certificate of analysis, from the factory or the independent lab."""

    __tablename__ = "coa_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), index=True)
    source: Mapped[CoaSource] = mapped_column(str_enum(CoaSource))
    issuer_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))

    # How it arrived: "upload", "manual" (typed in, no file), later "email" or "api".
    origin: Mapped[str] = mapped_column(String(16), default="upload")
    # A newer COA of the same source replaces this one; old ones are kept for the record.
    superseded: Mapped[bool] = mapped_column(default=False)

    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(64))
    storage_path: Mapped[str | None] = mapped_column(String(512))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Header fields as printed on the document (read by the model, or typed in by a person).
    # PENDING = file uploaded, values not in yet; DONE = values available for the check.
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        str_enum(ExtractionStatus), default=ExtractionStatus.PENDING
    )
    extraction_error: Mapped[str | None] = mapped_column(Text)
    extraction_model: Mapped[str | None] = mapped_column(String(64))
    issuer_name: Mapped[str | None] = mapped_column(String(255))
    product_name: Mapped[str | None] = mapped_column(String(255))
    cas_number: Mapped[str | None] = mapped_column(String(32))
    batch_number: Mapped[str | None] = mapped_column(String(64))
    po_reference: Mapped[str | None] = mapped_column(String(64))
    mfg_date: Mapped[date | None]
    test_date: Mapped[date | None]
    expiry_date: Mapped[date | None]
    raw_extraction: Mapped[dict | None] = mapped_column(JSON)

    batch: Mapped[Batch | None] = relationship(back_populates="coas")
    issuer: Mapped[Supplier | None] = relationship(lazy="joined")
    results: Mapped[list["COAResult"]] = relationship(
        back_populates="coa", cascade="all, delete-orphan", lazy="selectin"
    )


class COAResult(Base):
    """One test result row as printed on a COA."""

    __tablename__ = "coa_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    coa_id: Mapped[int] = mapped_column(
        ForeignKey("coa_documents.id", ondelete="CASCADE"), index=True
    )
    name_as_written: Mapped[str] = mapped_column(String(255))
    raw_value: Mapped[str] = mapped_column(String(255))  # exactly as printed: "41.2 %", "Complies"
    value: Mapped[float | None] = mapped_column(Float)  # parsed number, if any
    unit: Mapped[str | None] = mapped_column(String(32))
    method: Mapped[str | None] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    # Filled by the matcher: which spec parameter this row is evidence for.
    matched_parameter_id: Mapped[int | None] = mapped_column(ForeignKey("spec_parameters.id"))

    coa: Mapped[COADocument] = relationship(back_populates="results")
    matched_parameter: Mapped[SpecParameter | None] = relationship()


class Verdict(TimestampMixin, Base):
    """The engine's recommendation for a batch. Re-running a check adds a new verdict."""

    __tablename__ = "verdicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    spec_id: Mapped[int | None] = mapped_column(ForeignKey("specs.id"))
    decision: Mapped[Decision] = mapped_column(str_enum(Decision))
    summary: Mapped[str] = mapped_column(Text)
    # Full per-parameter breakdown, identity checks and factory-vs-lab discrepancies.
    details: Mapped[dict] = mapped_column(JSON)
    engine_version: Mapped[str] = mapped_column(String(32))

    batch: Mapped[Batch] = relationship(back_populates="verdicts")
    spec: Mapped[Spec | None] = relationship()


class BatchAction(TimestampMixin, Base):
    """A human decision on a batch: propose, approve, hold, reject, assign to a line."""

    __tablename__ = "batch_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    action: Mapped[BatchActionType] = mapped_column(str_enum(BatchActionType))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    verdict_id: Mapped[int | None] = mapped_column(ForeignKey("verdicts.id"))

    batch: Mapped[Batch] = relationship(back_populates="actions")
    actor: Mapped["User"] = relationship(lazy="joined")  # noqa: F821


class AuditLog(TimestampMixin, Base):
    """Append-only record of who did what, for every change that matters."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int | None]
    data: Mapped[dict] = mapped_column(JSON, default=dict)
