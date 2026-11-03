"""Customers, products, suppliers and versioned specs."""

from datetime import date

from sqlalchemy import JSON, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import RuleType, SpecStatus, SupplierKind
from app.models.mixins import TimestampMixin, str_enum


class Customer(TimestampMixin, Base):
    """A company that orders products."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    country: Mapped[str] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(64))


class Product(TimestampMixin, Base):
    """A chemical product, identified by name and CAS number."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    cas_number: Mapped[str | None] = mapped_column(String(32), index=True)
    industry: Mapped[str | None] = mapped_column(String(64))
    synonyms: Mapped[list[str]] = mapped_column(JSON, default=list)


class Supplier(TimestampMixin, Base):
    """A partner factory that makes batches or an independent lab."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    kind: Mapped[SupplierKind] = mapped_column(str_enum(SupplierKind))
    country: Mapped[str] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(64))


class Spec(TimestampMixin, Base):
    """A customer's requirements for one product grade; versioned, never edited."""

    __tablename__ = "specs"
    __table_args__ = (UniqueConstraint("customer_id", "product_id", "grade", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    grade: Mapped[str] = mapped_column(String(64))  # e.g. "78% active", "40% solution"
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[SpecStatus] = mapped_column(str_enum(SpecStatus), default=SpecStatus.ACTIVE)
    effective_from: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    customer: Mapped[Customer] = relationship(lazy="joined")
    product: Mapped[Product] = relationship(lazy="joined")
    parameters: Mapped[list["SpecParameter"]] = relationship(
        back_populates="spec",
        cascade="all, delete-orphan",
        order_by="SpecParameter.position",
        lazy="selectin",
    )


class SpecParameter(Base):
    """One test on a spec, e.g. free acid (as HCl) max 0.5 %."""

    __tablename__ = "spec_parameters"

    id: Mapped[int] = mapped_column(primary_key=True)
    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    name: Mapped[str] = mapped_column(String(128))
    # Other names suppliers use for the same test.
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    rule_type: Mapped[RuleType] = mapped_column(str_enum(RuleType))
    low: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    expected_text: Mapped[str | None] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(32))
    method: Mapped[str | None] = mapped_column(String(128))
    # A missing critical parameter blocks release.
    critical: Mapped[bool] = mapped_column(default=True)
    # Allowed factory-vs-lab difference; None uses the engine default.
    tolerance_pct: Mapped[float | None] = mapped_column(Float)
    tolerance_abs: Mapped[float | None] = mapped_column(Float)

    spec: Mapped[Spec] = relationship(back_populates="parameters")
