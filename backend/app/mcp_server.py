"""MCP server exposing BatchGate lookups to Claude Desktop and Claude Code.

Run with `uv run python -m app.mcp_server` (stdio). It acts as the user named by BATCHGATE_MCP_USER
with that user's permissions and has no release, hold or reject tools.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.permissions import Permission, permissions_for
from app.models import Batch, Product, Spec, Supplier, User
from app.models.enums import BatchActionType, BatchStatus, SpecStatus
from app.services import batches as svc
from app.services import copilot
from app.services.orders import visible_customer_ids

server = MCPServer(
    "BatchGate",
    instructions=(
        "BatchGate checks every batch's certificates of analysis (COAs) against the customer's "
        "spec before it ships. The rules engine decides release, review or hold; you can look "
        "things up, explain them and re-run a check. Releasing or holding a batch is done in the "
        "BatchGate web app."
    ),
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
ATTENTION = [BatchStatus.PENDING_REVIEW, BatchStatus.ON_HOLD, BatchStatus.PENDING_APPROVAL]


class NotAllowedError(Exception):
    """The configured user may not perform this request."""


@contextmanager
def session() -> Iterator[tuple[Session, User]]:
    """Yield a database session and the user this server acts as."""
    email = get_settings().mcp_user.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        if user is None:
            raise NotAllowedError(f"No active BatchGate user {email!r}. Set BATCHGATE_MCP_USER.")
        yield db, user


def _require(user: User, permission: Permission) -> None:
    """Raise NotAllowedError unless `user` holds `permission`."""
    if permission not in permissions_for(user.role):
        raise NotAllowedError(f"{user.full_name} ({user.role.value}) can't do this.")


def _find(db: Session, batch_number: str) -> list[Batch]:
    """Return the batches with this number, or raise NotAllowedError."""
    key = batch_number.strip().upper()
    found = list(db.scalars(select(Batch).where(func.upper(Batch.batch_number) == key)))
    if not found:
        raise NotAllowedError(f"No batch {batch_number!r}.")
    return found


def _brief(b: Batch) -> dict[str, Any]:
    """Summarise a batch for list results."""
    v = svc.latest_verdict(b)
    return {
        "batch": b.batch_number,
        "product": b.product.name,
        "factory": b.factory.name if b.factory else None,
        "status": b.status.value,
        "order_line": f"{b.line.order.po_number} line {b.line.line_no} ({b.line.spec.grade})"
        if b.line
        else None,
        "decision": v.decision.value if v else None,
        "summary": v.summary if v else None,
    }


@server.tool(annotations=READ_ONLY)
def batches_needing_attention() -> dict[str, list[dict]]:
    """Batches awaiting review, on hold, or awaiting approval."""
    with session() as (db, user):
        _require(user, Permission.VIEW_BATCHES)
        rows = db.scalars(
            select(Batch).where(Batch.status.in_(ATTENTION)).order_by(Batch.updated_at.desc())
        )
        out: dict[str, list[dict]] = {s.value: [] for s in ATTENTION}
        for b in rows:
            out[b.status.value].append(_brief(b))
        return out


@server.tool(annotations=READ_ONLY)
def get_batch(batch_number: str) -> list[dict]:
    """One batch in full: status, findings, results and COA readings."""
    with session() as (db, user):
        _require(user, Permission.VIEW_BATCHES)
        return [
            _brief(b)
            | {
                "check": copilot.run_tool(db, b, "get_verdict", {}),
                "coas": copilot.run_tool(db, b, "get_coa_readings", {}),
            }  # fmt: skip
            for b in _find(db, batch_number)
        ]


@server.tool(annotations=READ_ONLY)
def get_spec(product: str, grade: str | None = None, customer: str | None = None) -> list[dict]:
    """Current specs for a product, optionally one grade or customer."""
    with session() as (db, user):
        _require(user, Permission.VIEW_SPECS)
        q = (
            select(Spec)
            .join(Product)
            .where(Spec.status == SpecStatus.ACTIVE, func.lower(Product.name) == product.lower())
        )
        if (ids := visible_customer_ids(user)) is not None:
            q = q.where(Spec.customer_id.in_(ids))
        specs = [
            s
            for s in db.scalars(q)
            if (grade is None or s.grade.lower() == grade.lower())
            and (customer is None or customer.lower() in s.customer.name.lower())
        ]
        return [
            {
                "customer": s.customer.name,
                "product": s.product.name,
                "grade": s.grade,
                "version": s.version,
                "tests": [
                    {
                        "name": p.name,
                        "rule": p.rule_type.value,
                        "low": p.low,
                        "high": p.high,
                        "unit": p.unit,
                        "expected_text": p.expected_text,
                        "if_it_fails": "hold" if p.critical else "review",
                    }
                    for p in s.parameters
                ],  # fmt: skip
            }
            for s in specs
        ]


@server.tool(annotations=READ_ONLY)
def factory_history(factory: str, product: str, limit: int = 10) -> dict:
    """A factory's recent batches of one product, newest first."""
    with session() as (db, user):
        _require(user, Permission.VIEW_BATCHES)
        f = db.scalar(select(Supplier).where(func.lower(Supplier.name).contains(factory.lower())))
        p = db.scalar(select(Product).where(func.lower(Product.name) == product.lower()))
        if f is None or p is None:
            raise NotAllowedError(f"No factory matching {factory!r} or product {product!r}.")
        return copilot.factory_history(db, f, p, limit=limit)


@server.tool(annotations=READ_ONLY)
def search_knowledge(
    query: str, customer: str | None = None, product: str | None = None, limit: int = 5
) -> list[dict]:
    """Search quality agreements, SOPs, method notes and past cases."""
    from app.models import Customer
    from app.services import knowledge

    with session() as (db, user):
        _require(user, Permission.VIEW_KNOWLEDGE)
        c = (
            db.scalar(select(Customer).where(func.lower(Customer.name).contains(customer.lower())))
            if customer
            else None
        )
        p = (
            db.scalar(select(Product).where(func.lower(Product.name) == product.lower()))
            if product
            else None
        )
        if c is not None and (ids := visible_customer_ids(user)) is not None and c.id not in ids:
            raise NotAllowedError(f"{user.full_name} can't see {c.name}.")
        hits = knowledge.search(
            db,
            query,
            customer_id=c.id if c else None,
            product_id=p.id if p else None,
            limit=max(1, min(limit, 10)),
        )
        return [{"ref": h.ref, "source": h.source, "text": h.passage.text} for h in hits]


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
def rerun_check(batch_number: str) -> list[dict]:
    """Re-run the rules engine on a batch's current COAs."""
    with session() as (db, user):
        _require(user, Permission.RUN_CHECK)
        out = []
        for b in _find(db, batch_number):
            if b.status in svc.TERMINAL:
                out.append(_brief(b) | {"note": "Closed batches aren't checked again."})
                continue
            svc.apply_action(db, b, BatchActionType.RERUN_CHECK, actor=user)
            out.append(_brief(b))
        db.commit()
        return out


def main() -> None:
    """Run the server over stdio."""
    server.run("stdio")


if __name__ == "__main__":
    main()
