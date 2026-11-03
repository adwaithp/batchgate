"""Enumerations stored as strings."""

from enum import StrEnum


class Role(StrEnum):
    """A user's role, which maps to a set of permissions."""

    ADMIN = "admin"
    QC_MANAGER = "qc_manager"
    QC_ANALYST = "qc_analyst"
    SALES = "sales"


class SupplierKind(StrEnum):
    """Whether a supplier makes batches or tests them."""

    FACTORY = "factory"
    LAB = "lab"


class SpecStatus(StrEnum):
    """Whether a spec version is current."""

    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class RuleType(StrEnum):
    """How a spec parameter is checked."""

    MIN = "min"  # value >= low      ("NLT", "min")
    MAX = "max"  # value <= high     ("NMT", "max")
    RANGE = "range"  # low <= value <= high
    TEXT_MATCH = "text_match"  # e.g. appearance "dark brown liquid"
    COMPLIES = "complies"  # pass/fail statement from the lab ("Complies")


class OrderStatus(StrEnum):
    """Fulfilment state of an order."""

    OPEN = "open"
    PARTIALLY_READY = "partially_ready"
    READY = "ready"
    SHIPPED = "shipped"


class CoaSource(StrEnum):
    """Who issued a COA."""

    FACTORY = "factory"
    LAB = "lab"


class ExtractionStatus(StrEnum):
    """Progress of reading values from a COA."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class Decision(StrEnum):
    """The rules engine's recommendation."""

    RELEASE = "release"
    HOLD = "hold"
    REVIEW = "review"


class BatchStatus(StrEnum):
    """Where a batch is in the workflow."""

    AWAITING_COA = "awaiting_coa"
    PENDING_REVIEW = "pending_review"  # engine said review; an analyst must look
    ON_HOLD = "on_hold"
    PENDING_APPROVAL = "pending_approval"  # awaiting a QC manager's approval
    RELEASED = "released"
    REJECTED = "rejected"
    CANCELLED = "cancelled"  # entered by mistake; not a QC decision


class BatchActionType(StrEnum):
    """A decision a person can take on a batch."""

    PROPOSE_RELEASE = "propose_release"
    APPROVE_RELEASE = "approve_release"
    HOLD = "hold"
    REJECT = "reject"
    ASSIGN_LINE = "assign_line"
    RERUN_CHECK = "rerun_check"
    CANCEL = "cancel"


class DocumentKind(StrEnum):
    """Type of knowledge base document."""

    QUALITY_AGREEMENT = "quality_agreement"
    SOP = "sop"
    METHOD = "method"
    OTHER = "other"


class CaseOutcome(StrEnum):
    """How a past case ended."""

    RELEASED = "released"  # released after a person looked
    REJECTED = "rejected"
