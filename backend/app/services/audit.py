"""Audit log writer."""

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    **data,
) -> AuditLog:
    """Append an audit entry; the caller commits it with its own change."""
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        data=data,
    )
    db.add(entry)
    return entry
