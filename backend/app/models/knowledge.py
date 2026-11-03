"""Knowledge base models: documents, past cases and their searchable passages."""

from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.catalog import Customer, Product
from app.models.enums import CaseOutcome, DocumentKind
from app.models.mixins import TimestampMixin, str_enum


class KnowledgeDocument(TimestampMixin, Base):
    """A quality agreement, SOP or method note; no customer = all."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[DocumentKind] = mapped_column(str_enum(DocumentKind))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100))
    storage_path: Mapped[str | None] = mapped_column(String(500))
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    archived: Mapped[bool] = mapped_column(default=False)

    customer: Mapped[Customer | None] = relationship(lazy="joined")
    product: Mapped[Product | None] = relationship(lazy="joined")
    passages: Mapped[list["KnowledgePassage"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgePassage.position",
    )


class QCCase(TimestampMixin, Base):
    """A batch that needed a person, and how it ended."""

    __tablename__ = "qc_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), unique=True)
    batch_number: Mapped[str] = mapped_column(String(64))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    factory_name: Mapped[str | None] = mapped_column(String(255))
    problem: Mapped[str] = mapped_column(Text)
    actions: Mapped[str] = mapped_column(Text)
    outcome: Mapped[CaseOutcome] = mapped_column(str_enum(CaseOutcome))
    closed_on: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(32), default="batchgate")  # or imported

    customer: Mapped[Customer | None] = relationship(lazy="joined")
    product: Mapped[Product | None] = relationship(lazy="joined")
    passages: Mapped[list["KnowledgePassage"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class KnowledgePassage(Base):
    """A searchable section of a document, or a whole case."""

    __tablename__ = "knowledge_passages"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("qc_cases.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(default=0)
    section: Mapped[str | None] = mapped_column(String(255))  # e.g. "4.2 Retests"
    text: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)

    document: Mapped[KnowledgeDocument | None] = relationship(back_populates="passages")
    case: Mapped[QCCase | None] = relationship(back_populates="passages")
