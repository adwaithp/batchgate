"""Orders API: list, view and create customer purchase orders."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.permissions import Permission
from app.models import Order, User
from app.models.enums import BatchStatus, SpecStatus
from app.schemas.common import CustomerRef
from app.schemas.orders import (
    OrderCreate,
    OrderDetail,
    OrderLineBatch,
    OrderLineDetail,
    OrderListItem,
)
from app.services import orders as svc
from app.services.batches import latest_verdict, line_is_ready, released_quantity

router = APIRouter(prefix="/orders", tags=["orders"])

OrderViewer = Annotated[User, Depends(require(Permission.VIEW_ORDERS))]
OrderEditor = Annotated[User, Depends(require(Permission.EDIT_ORDERS))]

IN_QC = {BatchStatus.AWAITING_COA, BatchStatus.PENDING_REVIEW, BatchStatus.PENDING_APPROVAL}


def _list_item(order: Order) -> OrderListItem:
    """Map an order to its list-row view with release progress."""
    batches = [b for line in order.lines for b in line.batches]
    return OrderListItem(
        id=order.id,
        po_number=order.po_number,
        customer=CustomerRef.model_validate(order.customer),
        order_date=order.order_date,
        status=order.status,
        lines=len(order.lines),
        quantity=sum(line.quantity for line in order.lines),
        released_quantity=sum(released_quantity(line) for line in order.lines),
        batches_in_qc=sum(b.status in IN_QC for b in batches),
        on_hold=sum(b.status == BatchStatus.ON_HOLD for b in batches),
    )


def _detail(order: Order) -> OrderDetail:
    """Map an order to its detail view with each line's batches."""
    return OrderDetail(
        id=order.id,
        po_number=order.po_number,
        customer=CustomerRef.model_validate(order.customer),
        order_date=order.order_date,
        status=order.status,
        created_at=order.created_at,
        lines=[
            OrderLineDetail(
                id=line.id,
                line_no=line.line_no,
                product=line.product.name,
                spec_id=line.spec_id,
                grade=line.spec.grade,
                spec_version=line.spec.version,
                spec_current=line.spec.status == SpecStatus.ACTIVE,
                quantity=line.quantity,
                unit=line.unit,
                released_quantity=released_quantity(line),
                ready=line_is_ready(line),
                batches=[
                    OrderLineBatch(
                        id=b.id,
                        batch_number=b.batch_number,
                        factory=b.factory.name if b.factory else None,
                        quantity=b.quantity,
                        unit=b.unit,
                        status=b.status,
                        decision=(v.decision if (v := latest_verdict(b)) else None),
                    )
                    for b in sorted(line.batches, key=lambda b: b.id)
                ],
            )
            for line in order.lines
        ],
    )


@router.get("", response_model=list[OrderListItem])
def list_orders(db: DbSession, user: OrderViewer) -> list[OrderListItem]:
    """List the orders the signed-in user may see, newest first."""
    q = select(Order).order_by(Order.order_date.desc(), Order.id.desc())
    ids = svc.visible_customer_ids(user)
    if ids is not None:
        q = q.where(Order.customer_id.in_(ids))
    return [_list_item(o) for o in db.scalars(q)]


@router.get("/{order_id}", response_model=OrderDetail)
def get_order(db: DbSession, user: OrderViewer, order_id: int) -> OrderDetail:
    """Return one order, or 404 if it is out of the user's scope."""
    order = db.get(Order, order_id)
    if order is None or not svc.can_see_customer(user, order.customer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return _detail(order)


@router.post("", response_model=OrderDetail, status_code=status.HTTP_201_CREATED)
def create_order(db: DbSession, user: OrderEditor, body: OrderCreate) -> OrderDetail:
    """Create an order against the customer's current specs."""
    order = svc.create_order(
        db,
        po_number=body.po_number,
        customer_id=body.customer_id,
        order_date=body.order_date,
        lines=[svc.LineInput(**line.model_dump()) for line in body.lines],
        actor=user,
    )
    db.commit()
    return _detail(order)
