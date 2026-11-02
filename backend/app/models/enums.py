from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    QC_MANAGER = "qc_manager"
    QC_ANALYST = "qc_analyst"
    SALES = "sales"


class SupplierKind(StrEnum):
    FACTORY = "factory"  # partner manufacturing site
    LAB = "lab"  # independent testing laboratory


class SpecStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class RuleType(StrEnum):
    MIN = "min"  # value >= low      ("NLT", "min")
    MAX = "max"  # value <= high     ("NMT", "max")
    RANGE = "range"  # low <= value <= high
    TEXT_MATCH = "text_match"  # e.g. appearance "dark brown liquid"
    COMPLIES = "complies"  # pass/fail statement from the lab ("Complies")


class OrderStatus(StrEnum):
    OPEN = "open"
    PARTIALLY_READY = "partially_ready"
    READY = "ready"
    SHIPPED = "shipped"


class CoaSource(StrEnum):
    FACTORY = "factory"
    LAB = "lab"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class Decision(StrEnum):
    """What the engine recommends for a batch."""

    RELEASE = "release"
    HOLD = "hold"
    REVIEW = "review"


class BatchStatus(StrEnum):
    """Where a batch is in the human workflow."""

    AWAITING_COA = "awaiting_coa"
    PENDING_REVIEW = "pending_review"  # engine said REVIEW, a QC analyst must look
    ON_HOLD = "on_hold"  # engine or human said HOLD
    PENDING_APPROVAL = "pending_approval"  # proposed for release, needs a QC manager
    RELEASED = "released"
    REJECTED = "rejected"


class BatchActionType(StrEnum):
    PROPOSE_RELEASE = "propose_release"  # analyst: "I've reviewed it, release it"
    APPROVE_RELEASE = "approve_release"  # manager: second pair of eyes
    HOLD = "hold"
    REJECT = "reject"
    ASSIGN_LINE = "assign_line"  # confirm which order line a batch belongs to
    RERUN_CHECK = "rerun_check"
