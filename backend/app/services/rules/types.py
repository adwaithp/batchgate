"""Plain data in and out of the rules engine. No database, no AI: easy to test and to evaluate."""

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum

from app.models.enums import CoaSource, Decision, RuleType


class Severity(StrEnum):
    HOLD = "hold"  # blocks release outright
    REVIEW = "review"  # a person must look before release
    INFO = "info"  # shown, does not change the decision


class ParamStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNCLEAR = "unclear"
    MISSING = "missing"


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    MISSING = "missing"


# ---- Inputs ------------------------------------------------------------------------------


@dataclass
class ParamSpec:
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
    product_name: str
    parameters: list[ParamSpec]
    cas_number: str | None = None
    product_synonyms: list[str] = field(default_factory=list)


@dataclass
class ResultInput:
    name_as_written: str
    raw_value: str
    unit: str | None = None
    confidence: float = 1.0
    parameter_id: int | None = None  # set when a person (or the extractor) already matched it


@dataclass
class CoaInput:
    source: CoaSource
    results: list[ResultInput]
    id: int | None = None
    issuer_name: str | None = None
    product_name: str | None = None
    cas_number: str | None = None
    batch_number: str | None = None
    mfg_date: date | None = None
    test_date: date | None = None
    expiry_date: date | None = None


@dataclass
class BatchInput:
    batch_number: str
    coas: list[CoaInput]


@dataclass
class EngineConfig:
    require_lab_coa: bool = True
    default_tolerance_pct: float = 2.0
    low_confidence: float = 0.8
    expiry_warning_days: int = 30


# ---- Outputs -----------------------------------------------------------------------------


@dataclass
class SourceReading:
    source: CoaSource
    coa_id: int | None
    raw_value: str
    unit: str | None
    value: float | None  # converted to the spec's unit, when numeric and convertible
    status: ParamStatus
    note: str | None = None
    confidence: float = 1.0


@dataclass
class ParameterCheck:
    parameter_id: int
    name: str
    spec_text: str
    critical: bool
    status: ParamStatus
    readings: list[SourceReading]
    discrepancy: str | None = None  # factory vs lab disagreement, explained
    note: str | None = None


@dataclass
class IdentityCheck:
    code: str
    label: str
    status: CheckStatus
    message: str
    source: CoaSource | None = None


@dataclass
class Finding:
    severity: Severity
    code: str
    message: str
    parameter_id: int | None = None


@dataclass
class UnmatchedResult:
    source: CoaSource
    name_as_written: str
    raw_value: str
    unit: str | None


@dataclass
class EngineResult:
    decision: Decision
    summary: str
    parameters: list[ParameterCheck]
    identity: list[IdentityCheck]
    findings: list[Finding]
    unmatched: list[UnmatchedResult]

    def to_dict(self) -> dict:
        return asdict(self)
