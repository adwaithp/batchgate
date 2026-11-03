"""Batch, COA and verdict schemas."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    BatchActionType,
    BatchStatus,
    CoaSource,
    Decision,
    ExtractionStatus,
    RuleType,
)
from app.schemas.common import ProductRef, SupplierRef


class SpecParameterOut(BaseModel):
    """A spec parameter as shown on a batch."""

    id: int
    name: str
    rule_type: RuleType
    low: float | None
    high: float | None
    unit: str | None
    expected_text: str | None
    critical: bool
    spec_text: str
    aliases: list[str]


class SpecOut(BaseModel):
    """The spec a batch is checked against."""

    id: int
    grade: str
    version: int
    customer: str
    product: str
    parameters: list[SpecParameterOut]


class LineOut(BaseModel):
    """An order line as shown on a batch."""

    id: int
    order_id: int
    po_number: str
    line_no: int
    customer: str
    product: str
    grade: str
    quantity: float
    unit: str
    released_quantity: float


class LineWithSpec(LineOut):
    """An order line with its spec."""

    spec: SpecOut


class CoaResultOut(BaseModel):
    """One result row read from a COA."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name_as_written: str
    raw_value: str
    unit: str | None
    method: str | None
    confidence: float
    needs_check: bool  # read with low confidence; compare with the document
    matched_parameter_id: int | None


class CoaOut(BaseModel):
    """A COA document with its header fields and results."""

    id: int
    source: CoaSource
    issuer: SupplierRef | None
    origin: str
    superseded: bool
    original_filename: str | None
    has_file: bool
    uploaded_at: datetime
    uploaded_by: str | None
    extraction_status: ExtractionStatus
    extraction_model: str | None
    extraction_error: str | None
    warnings: list[str]
    checked_by: str | None
    issuer_name: str | None  # as printed; `issuer` is the supplier chosen in BatchGate
    issuer_confidence: float
    issuer_needs_check: bool
    product_name: str | None
    cas_number: str | None
    batch_number: str | None
    po_reference: str | None
    mfg_date: date | None
    test_date: date | None
    expiry_date: date | None
    mfg_date_as_printed: str | None
    test_date_as_printed: str | None
    expiry_date_as_printed: str | None
    results: list[CoaResultOut]


class VerdictOut(BaseModel):
    """A rules-engine verdict with its full details."""

    id: int
    decision: Decision
    summary: str
    details: dict
    engine_version: str
    created_at: datetime


class VerdictBrief(BaseModel):
    """A verdict in a batch's history."""

    id: int
    decision: Decision
    summary: str
    created_at: datetime


class ActionOut(BaseModel):
    """A decision a person took on a batch."""

    id: int
    action: BatchActionType
    actor: str
    actor_role: str
    note: str | None
    created_at: datetime


class SuggestionOut(BaseModel):
    """An open order line a batch could belong to."""

    line: LineOut
    decision: Decision
    summary: str
    failing: list[str]


class BatchLineBrief(BaseModel):
    """The order line shown in batch lists."""

    id: int
    po_number: str
    line_no: int
    grade: str
    customer: str


class BatchSummary(BaseModel):
    """A batch row in lists."""

    id: int
    batch_number: str
    product: ProductRef
    factory: SupplierRef | None
    status: BatchStatus
    quantity: float | None
    unit: str
    line: BatchLineBrief | None
    decision: Decision | None
    summary: str | None
    coa_sources: list[CoaSource]
    updated_at: datetime


class BatchDetail(BatchSummary):
    """A batch in full, with what the user may do next."""

    line_detail: LineWithSpec | None
    coas: list[CoaOut]
    verdict: VerdictOut | None
    history: list[VerdictBrief]
    actions: list[ActionOut]
    allowed_actions: list[BatchActionType]
    suggestions: list[SuggestionOut]


class BatchCreate(BaseModel):
    """Request to register a batch."""

    batch_number: str = Field(min_length=1, max_length=64)
    product_id: int
    factory_id: int
    line_id: int | None = None
    quantity: float | None = Field(default=None, gt=0)


class BatchActionIn(BaseModel):
    """Request to take a decision on a batch."""

    action: BatchActionType
    note: str | None = Field(default=None, max_length=2000)
    line_id: int | None = None


class CoaRowIn(BaseModel):
    """One result row typed or confirmed by a person."""

    name_as_written: str = Field(min_length=1, max_length=255)
    raw_value: str = Field(max_length=255)
    unit: str | None = Field(default=None, max_length=32)
    method: str | None = Field(default=None, max_length=128)
    # 1.0 for rows a person typed, edited or ticked; others keep the model's.
    confidence: float = Field(default=1.0, ge=0, le=1)
    parameter_id: int | None = None


class CoaDataIn(BaseModel):
    """COA header fields and results typed or confirmed by a person."""

    issuer_name: str | None = Field(default=None, max_length=255)
    issuer_confidence: float = Field(default=1.0, ge=0, le=1)  # as for result rows
    product_name: str | None = None
    cas_number: str | None = None
    batch_number: str | None = None
    po_reference: str | None = None
    mfg_date: date | None = None
    test_date: date | None = None
    expiry_date: date | None = None
    mfg_date_as_printed: str | None = Field(default=None, max_length=64)
    test_date_as_printed: str | None = Field(default=None, max_length=64)
    expiry_date_as_printed: str | None = Field(default=None, max_length=64)
    results: list[CoaRowIn]


class LineOption(BaseModel):
    """An open order line offered in the batch form."""

    id: int
    product_id: int
    label: str
    po_number: str
    line_no: int
    grade: str
    customer: str
    quantity: float
    unit: str


class CatalogOptions(BaseModel):
    """Choices for the register-batch and upload forms."""

    products: list[ProductRef]
    factories: list[SupplierRef]
    labs: list[SupplierRef]
    open_lines: list[LineOption]
