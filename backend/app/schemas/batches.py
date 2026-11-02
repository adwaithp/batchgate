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


class Ref(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class SupplierRef(Ref):
    country: str
    city: str | None = None


class ProductRef(Ref):
    cas_number: str | None = None


class SpecParameterOut(BaseModel):
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
    id: int
    grade: str
    version: int
    customer: str
    product: str
    parameters: list[SpecParameterOut]


class LineOut(BaseModel):
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
    spec: SpecOut


class CoaResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_as_written: str
    raw_value: str
    unit: str | None
    method: str | None
    confidence: float
    needs_check: bool  # read with low confidence; a person should compare it with the document
    matched_parameter_id: int | None


class CoaOut(BaseModel):
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
    product_name: str | None
    cas_number: str | None
    batch_number: str | None
    po_reference: str | None
    mfg_date: date | None
    test_date: date | None
    expiry_date: date | None
    results: list[CoaResultOut]


class VerdictOut(BaseModel):
    id: int
    decision: Decision
    summary: str
    details: dict
    engine_version: str
    created_at: datetime


class VerdictBrief(BaseModel):
    id: int
    decision: Decision
    summary: str
    created_at: datetime


class ActionOut(BaseModel):
    id: int
    action: BatchActionType
    actor: str
    actor_role: str
    note: str | None
    created_at: datetime


class SuggestionOut(BaseModel):
    line: LineOut
    decision: Decision
    summary: str
    failing: list[str]


class BatchLineBrief(BaseModel):
    id: int
    po_number: str
    line_no: int
    grade: str
    customer: str


class BatchSummary(BaseModel):
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
    line_detail: LineWithSpec | None
    coas: list[CoaOut]
    verdict: VerdictOut | None
    history: list[VerdictBrief]
    actions: list[ActionOut]
    allowed_actions: list[BatchActionType]
    suggestions: list[SuggestionOut]


# ---- Requests ----------------------------------------------------------------------------


class BatchCreate(BaseModel):
    batch_number: str = Field(min_length=1, max_length=64)
    product_id: int
    factory_id: int
    line_id: int | None = None
    quantity: float | None = Field(default=None, gt=0)


class BatchActionIn(BaseModel):
    action: BatchActionType
    note: str | None = Field(default=None, max_length=2000)
    line_id: int | None = None


class CoaRowIn(BaseModel):
    name_as_written: str = Field(min_length=1, max_length=255)
    raw_value: str = Field(max_length=255)
    unit: str | None = Field(default=None, max_length=32)
    method: str | None = Field(default=None, max_length=128)
    # Rows a person typed, edited or ticked as checked are 1.0; untouched model rows keep theirs.
    confidence: float = Field(default=1.0, ge=0, le=1)
    parameter_id: int | None = None


class CoaDataIn(BaseModel):
    product_name: str | None = None
    cas_number: str | None = None
    batch_number: str | None = None
    po_reference: str | None = None
    mfg_date: date | None = None
    test_date: date | None = None
    expiry_date: date | None = None
    results: list[CoaRowIn]


# ---- Form options ------------------------------------------------------------------------


class LineOption(BaseModel):
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
    products: list[ProductRef]
    factories: list[SupplierRef]
    labs: list[SupplierRef]
    open_lines: list[LineOption]
