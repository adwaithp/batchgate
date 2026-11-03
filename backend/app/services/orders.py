"""Customer orders and customers. Each order line is checked against one spec."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import Permission, permissions_for
from app.models import Customer, Order, OrderLine, Spec, User
from app.models.enums import OrderStatus, SpecStatus
from app.services import audit
from app.services.batches import WorkflowError


def visible_customer_ids(user: User) -> set[int] | None:
    """Return the customer ids `user` may see, or None for all."""
    if Permission.VIEW_ALL_CUSTOMERS in permissions_for(user.role):
        return None
    return {c.id for c in user.customers}


def can_see_customer(user: User, customer_id: int) -> bool:
    """Return True when `user` may see the customer."""
    ids = visible_customer_ids(user)
    return ids is None or customer_id in ids


def create_customer(
    db: Session, *, name: str, country: str, industry: str | None, actor: User
) -> Customer:
    """Add a customer; users limited to their own customers get assigned."""
    name = " ".join((name or "").split())
    country = " ".join((country or "").split())
    if not name:
        raise WorkflowError("Enter the customer's name.", 422)
    if not country:
        raise WorkflowError("Enter the customer's country.", 422)
    existing = db.scalar(select(Customer).where(func.lower(Customer.name) == name.lower()))
    if existing is not None:
        if can_see_customer(actor, existing.id):
            raise WorkflowError(f"{existing.name} is already a customer.", 409)
        raise WorkflowError(
            f"{existing.name} is already a customer, managed by someone else. "
            "Ask an admin to add you to it.",
            409,
        )
    customer = Customer(name=name, country=country, industry=(industry or "").strip() or None)
    db.add(customer)
    if visible_customer_ids(actor) is not None:
        actor.customers.append(customer)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="customer_added",
        entity_type="customer",
        entity_id=customer.id,
        name=customer.name,
        country=customer.country,
    )
    return customer


@dataclass
class LineInput:
    """One requested order line."""

    spec_id: int
    quantity: float
    unit: str = "t"


def create_order(
    db: Session,
    *,
    po_number: str,
    customer_id: int,
    order_date: date,
    lines: list[LineInput],
    actor: User,
) -> Order:
    """Create an order whose lines use the customer's current specs."""
    po_number = (po_number or "").strip().upper()
    if not po_number:
        raise WorkflowError("Enter the customer's PO number.", 422)
    if db.scalar(select(Order.id).where(Order.po_number == po_number)):
        raise WorkflowError(f"{po_number} already exists.", 409)

    customer = db.get(Customer, customer_id)
    if customer is None or not can_see_customer(actor, customer_id):
        raise WorkflowError("Choose one of your customers.", 422)
    if not lines:
        raise WorkflowError("Add at least one line.", 422)

    order_lines: list[OrderLine] = []
    for i, line in enumerate(lines, start=1):
        spec = db.get(Spec, line.spec_id)
        if spec is None or spec.customer_id != customer_id:
            raise WorkflowError(f"Line {i}: choose one of {customer.name}'s specs.", 422)
        if spec.status != SpecStatus.ACTIVE:
            raise WorkflowError(
                f"Line {i}: {spec.product.name} “{spec.grade}” v{spec.version} has been "
                "replaced. Choose the current version.",
                422,
            )
        if line.quantity is None or line.quantity <= 0:
            raise WorkflowError(f"Line {i}: enter a quantity above zero.", 422)
        order_lines.append(
            OrderLine(
                line_no=i,
                product_id=spec.product_id,
                spec=spec,
                quantity=line.quantity,
                unit=(line.unit or "t").strip() or "t",
            )
        )

    order = Order(
        po_number=po_number,
        customer=customer,
        order_date=order_date,
        status=OrderStatus.OPEN,
        lines=order_lines,
    )
    db.add(order)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="order_created",
        entity_type="order",
        entity_id=order.id,
        po_number=po_number,
        customer=customer.name,
        lines=len(order_lines),
    )
    return order
