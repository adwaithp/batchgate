"""Order schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import BatchStatus, Decision, OrderStatus
from app.schemas.common import CustomerRef


class OrderLineBatch(BaseModel):
    """A batch on an order line."""

    id: int
    batch_number: str
    factory: str | None
    quantity: float | None
    unit: str
    status: BatchStatus
    decision: Decision | None


class OrderLineDetail(BaseModel):
    """An order line with its spec and batches."""

    id: int
    line_no: int
    product: str
    spec_id: int
    grade: str
    spec_version: int
    spec_current: bool  # false when a newer spec version exists
    quantity: float
    unit: str
    released_quantity: float
    ready: bool
    batches: list[OrderLineBatch]


class OrderListItem(BaseModel):
    """An order row in lists."""

    id: int
    po_number: str
    customer: CustomerRef
    order_date: date
    status: OrderStatus
    lines: int
    quantity: float
    released_quantity: float
    batches_in_qc: int
    on_hold: int


class OrderDetail(BaseModel):
    """An order in full."""

    id: int
    po_number: str
    customer: CustomerRef
    order_date: date
    status: OrderStatus
    created_at: datetime
    lines: list[OrderLineDetail]


class OrderLineIn(BaseModel):
    """Request line: a spec and a quantity."""

    spec_id: int
    quantity: float = Field(gt=0)
    unit: str = Field(default="t", max_length=16)


class OrderCreate(BaseModel):
    """Request to create an order."""

    po_number: str = Field(min_length=1, max_length=64)
    customer_id: int
    order_date: date
    lines: list[OrderLineIn] = Field(min_length=1, max_length=50)
