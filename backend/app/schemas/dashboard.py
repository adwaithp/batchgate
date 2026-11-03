"""Dashboard schemas."""

from pydantic import BaseModel

from app.models.enums import OrderStatus


class OrderLineSummary(BaseModel):
    """An order line with release progress."""

    line_no: int
    product: str
    grade: str
    quantity: float
    unit: str
    batches: int
    released: int
    released_quantity: float
    ready: bool


class OrderSummary(BaseModel):
    """A recent order with its lines."""

    id: int
    po_number: str
    customer: str
    order_date: str
    status: OrderStatus
    lines: list[OrderLineSummary]


class DashboardOut(BaseModel):
    """Counts and recent orders for the signed-in user's customers."""

    scope: str  # all customers, or the customers a sales user manages
    open_orders: int
    order_lines: int
    active_specs: int
    batches_by_status: dict[str, int]
    recent_orders: list[OrderSummary]
