"""Plain dataclasses in and out of the rules engine."""

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum

from app.models.enums import CoaSource, Decision, RuleType


class Severity(StrEnum):
    """How much a finding matters."""

    HOLD = "hold"
    REVIEW = "review"
    INFO = "info"  # shown only


class ParamStatus(StrEnum):
    """Result of checking one parameter."""

    PASS = "pass"
    FAIL = "fail"
    UNCLEAR = "unclear"
    MISSING = "missing"


class CheckStatus(StrEnum):
    """Result of an identity check."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    MISSING = "missing"


@dataclass
class ParamSpec:
    """One spec parameter."""

    id: int
    name: str
    rule_type: RuleType
    low: float | None = None
    high: float | None = None
    unit: str | None = None
    expected_text: str | None = None
    aliases: list[str] = field(default_factory=list)
    critical: bool = True
    tolerance_pct: float | None = None  # factory vs lab, relative
    tolerance_abs: float | None = None  # factory vs lab, in the parameter's unit


@dataclass
class SpecInput:
    """The spec a batch is checked against."""

    product_name: str
    parameters: list[ParamSpec]
    cas_number: str | None = None
    product_synonyms: list[str] = field(default_factory=list)
    grade: str | None = None  # e.g. "40% solution"


@dataclass
class ResultInput:
    """One result row from a COA."""

    name_as_written: str
    raw_value: str
    unit: str | None = None
    confidence: float = 1.0
    parameter_id: int | None = None  # set when already matched


@dataclass
class CoaInput:
    """One COA's header and results."""

    source: CoaSource
    results: list[ResultInput]
    id: int | None = None
    issuer_name: str | None = None
    issuer_confidence: float = 1.0
    expected_issuer: str | None = None  # the batch's factory, or the lab chosen for this COA
    product_name: str | None = None
    cas_number: str | None = None
    batch_number: str | None = None
    mfg_date: date | None = None
    test_date: date | None = None
    expiry_date: date | None = None  # only full dates
    # Dates as printed when not a full date.
    mfg_date_as_printed: str | None = None
    test_date_as_printed: str | None = None
    expiry_date_as_printed: str | None = None


@dataclass
class BatchInput:
    """A batch and its COAs."""

    batch_number: str
    coas: list[CoaInput]


@dataclass
class EngineConfig:
    """Release policy settings."""

    require_lab_coa: bool = True
    default_tolerance_pct: float = 2.0
    low_confidence: float = 0.8
    expiry_warning_days: int = 30


@dataclass
class SourceReading:
    """One COA's reading of a parameter."""

    source: CoaSource
    coa_id: int | None
    raw_value: str
    unit: str | None
    value: float | None  # in the spec's unit, when convertible
    status: ParamStatus
    note: str | None = None
    confidence: float = 1.0


@dataclass
class ParameterCheck:
    """A parameter's readings and combined status."""

    parameter_id: int
    name: str
    spec_text: str
    critical: bool
    status: ParamStatus
    readings: list[SourceReading]
    discrepancy: str | None = None
    note: str | None = None


@dataclass
class IdentityCheck:
    """A product, grade, issuer, batch or date check."""

    code: str
    label: str
    status: CheckStatus
    message: str
    source: CoaSource | None = None


@dataclass
class Finding:
    """A reason behind the decision."""

    severity: Severity
    code: str
    message: str
    parameter_id: int | None = None


@dataclass
class UnmatchedResult:
    """A COA row that matched no parameter."""

    source: CoaSource
    name_as_written: str
    raw_value: str
    unit: str | None


@dataclass
class EngineResult:
    """The engine's decision with all its evidence."""

    decision: Decision
    summary: str
    parameters: list[ParameterCheck]
    identity: list[IdentityCheck]
    findings: list[Finding]
    unmatched: list[UnmatchedResult]

    def to_dict(self) -> dict:
        """Return the result as a plain dict for storage."""
        return asdict(self)
