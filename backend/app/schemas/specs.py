"""Spec schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import RuleType, SpecStatus
from app.schemas.common import CustomerRef, ProductRef


class SpecParameterFull(BaseModel):
    """A spec parameter with its tolerances and text."""

    id: int
    name: str
    rule_type: RuleType
    low: float | None
    high: float | None
    unit: str | None
    expected_text: str | None
    aliases: list[str]
    method: str | None
    critical: bool
    tolerance_pct: float | None
    tolerance_abs: float | None
    spec_text: str


class SpecSummary(BaseModel):
    """A spec row in lists."""

    id: int
    customer: CustomerRef
    product: ProductRef
    grade: str
    version: int
    status: SpecStatus
    effective_from: date | None
    tests: int
    critical_tests: int
    open_lines: int
    created_at: datetime


class SpecVersionBrief(BaseModel):
    """One version in a spec's history."""

    id: int
    version: int
    status: SpecStatus
    effective_from: date | None
    created_by: str | None
    created_at: datetime
    notes: str | None


class SpecLineUse(BaseModel):
    """An open order line using a spec."""

    line_id: int
    order_id: int
    po_number: str
    line_no: int
    quantity: float
    unit: str
    spec_version: int


class SpecDetail(SpecSummary):
    """A spec version in full."""

    notes: str | None
    created_by: str | None
    parameters: list[SpecParameterFull]
    versions: list[SpecVersionBrief]
    current_version_id: int | None  # set once a newer version replaces this one
    used_by: list[SpecLineUse]
    can_edit: bool


class SpecParameterIn(BaseModel):
    """A spec parameter in a create or update request."""

    name: str = Field(max_length=128)
    rule_type: RuleType
    low: float | None = None
    high: float | None = None
    unit: str | None = Field(default=None, max_length=32)
    expected_text: str | None = Field(default=None, max_length=255)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    method: str | None = Field(default=None, max_length=128)
    critical: bool = True
    tolerance_pct: float | None = None
    tolerance_abs: float | None = None


class SpecCreate(BaseModel):
    """Request to create a spec."""

    customer_id: int
    product_id: int
    grade: str = Field(max_length=64)
    notes: str | None = Field(default=None, max_length=2000)
    parameters: list[SpecParameterIn] = Field(max_length=60)


class SpecNewVersion(BaseModel):
    """Request to create the next version of a spec."""

    notes: str | None = Field(default=None, max_length=2000)
    parameters: list[SpecParameterIn] = Field(max_length=60)


class SpecOption(BaseModel):
    """A current spec offered on the order form."""

    id: int
    product_id: int
    product: str
    grade: str
    version: int


class CustomerSpecs(BaseModel):
    """A customer's current specs."""

    customer_id: int
    specs: list[SpecOption]
