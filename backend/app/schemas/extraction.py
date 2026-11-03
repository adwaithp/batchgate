"""Structured output Claude returns when reading a COA."""

from datetime import date

from pydantic import BaseModel


class ExtractedRow(BaseModel):
    """One result row as printed."""

    name_as_written: str
    raw_value: str
    unit: str | None
    method: str | None
    limit_as_printed: str | None  # helps keep the result and limit columns apart
    confidence: float
    parameter_id: int | None


class CoaExtraction(BaseModel):
    """Everything read from one COA."""

    is_coa: bool
    issuer_name: str | None
    issuer_confidence: float
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
    results: list[ExtractedRow]
    warnings: list[str]
