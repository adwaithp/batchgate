"""Dashboard API: order and batch counts for the signed-in user's customers."""

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import DbSession, require
from app.core.permissions import Permission, permissions_for
from app.models import Batch, Order, OrderLine, Spec, User
from app.models.enums import BatchStatus, OrderStatus, SpecStatus
from app.schemas.dashboard import DashboardOut, OrderLineSummary, OrderSummary
from app.services.batches import line_is_ready, released_quantity

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(
    db: DbSession, user: Annotated[User, Depends(require(Permission.VIEW_DASHBOARD))]
) -> DashboardOut:
    """Summarise open orders, active specs and batches by status."""
    sees_all = Permission.VIEW_ALL_CUSTOMERS in permissions_for(user.role)
    customer_ids = None if sees_all else [c.id for c in user.customers]

    order_q = select(Order)
    if customer_ids is not None:
        order_q = order_q.where(Order.customer_id.in_(customer_ids))
    orders = list(db.scalars(order_q.order_by(Order.order_date.desc())))

    open_orders = sum(o.status != OrderStatus.SHIPPED for o in orders)
    order_lines = sum(len(o.lines) for o in orders)

    spec_q = select(func.count(Spec.id)).where(Spec.status == SpecStatus.ACTIVE)
    if customer_ids is not None:
        spec_q = spec_q.where(Spec.customer_id.in_(customer_ids))
    active_specs = db.scalar(spec_q) or 0

    batch_q = select(Batch.status)
    if customer_ids is not None:
        batch_q = (
            batch_q.join(OrderLine, Batch.line_id == OrderLine.id)
            .join(Order, OrderLine.order_id == Order.id)
            .where(Order.customer_id.in_(customer_ids))
        )
    counts = Counter(db.scalars(batch_q))
    batches_by_status = {s.value: counts.get(s, 0) for s in BatchStatus}

    recent = [
        OrderSummary(
            id=o.id,
            po_number=o.po_number,
            customer=o.customer.name,
            order_date=o.order_date.isoformat(),
            status=o.status,
            lines=[
                OrderLineSummary(
                    line_no=line.line_no,
                    product=line.product.name,
                    grade=line.spec.grade,
                    quantity=line.quantity,
                    unit=line.unit,
                    batches=sum(b.status != BatchStatus.CANCELLED for b in line.batches),
                    released=sum(b.status == BatchStatus.RELEASED for b in line.batches),
                    released_quantity=released_quantity(line),
                    ready=line_is_ready(line),
                )
                for line in o.lines
            ],
        )
        for o in orders[:5]
    ]

    scope = "All customers" if sees_all else ", ".join(c.name for c in user.customers) or "None"
    return DashboardOut(
        scope=scope,
        open_orders=open_orders,
        order_lines=order_lines,
        active_specs=active_specs,
        batches_by_status=batches_by_status,
        recent_orders=recent,
    )
