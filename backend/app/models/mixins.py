"""Shared column helpers."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


class TimestampMixin:
    """Adds created and updated timestamps."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def str_enum(enum_cls):
    """Store an enum by its value as a plain string."""
    return Enum(
        enum_cls,
        native_enum=False,
        values_callable=lambda e: [m.value for m in e],
        length=32,
        validate_strings=True,
    )
