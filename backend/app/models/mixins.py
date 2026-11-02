from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def str_enum(enum_cls):
    """Store enums by value as plain strings (readable in the DB, easy to migrate)."""
    return Enum(
        enum_cls,
        native_enum=False,
        values_callable=lambda e: [m.value for m in e],
        length=32,
        validate_strings=True,
    )
