"""Audit log schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEntry(BaseModel):
    """One audit log entry with a readable label and link."""

    id: int
    at: datetime
    actor: str | None  # None means BatchGate itself
    action: str
    entity_type: str
    entity_id: int | None
    entity_label: str | None
    link: str | None
    data: dict[str, Any]


class AuditPage(BaseModel):
    """A page of audit entries."""

    entries: list[AuditEntry]
    next_before: int | None  # pass as ?before= to load older entries
