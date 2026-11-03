"""Customer specs, versioned and never edited in place."""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, Order, OrderLine, Product, Spec, SpecParameter, User
from app.models.enums import OrderStatus, RuleType, SpecStatus
from app.services import audit
from app.services.batches import WorkflowError
from app.services.rules.matching import normalize_name


@dataclass
class ParameterInput:
    """One requested spec parameter."""

    name: str
    rule_type: RuleType
    low: float | None = None
    high: float | None = None
    unit: str | None = None
    expected_text: str | None = None
    aliases: list[str] = field(default_factory=list)
    method: str | None = None
    critical: bool = True
    tolerance_pct: float | None = None
    tolerance_abs: float | None = None


def _clean(text: str | None) -> str | None:
    """Strip a text value, returning None when empty."""
    text = (text or "").strip()
    return text or None


def _limits(p: ParameterInput, label: str) -> tuple[float | None, float | None, str | None]:
    """Validate the limits a rule needs and drop the ones it ignores."""
    low, high, expected = p.low, p.high, _clean(p.expected_text)
    match p.rule_type:
        case RuleType.MIN:
            if low is None:
                raise WorkflowError(f"{label}: enter the minimum.", 422)
            return low, None, None
        case RuleType.MAX:
            if high is None:
                raise WorkflowError(f"{label}: enter the maximum.", 422)
            return None, high, None
        case RuleType.RANGE:
            if low is None or high is None:
                raise WorkflowError(f"{label}: enter both the lower and upper limit.", 422)
            if low > high:
                raise WorkflowError(f"{label}: the lower limit is above the upper limit.", 422)
            return low, high, None
        case RuleType.TEXT_MATCH:
            if not expected:
                raise WorkflowError(f"{label}: describe what the result should say.", 422)
            return None, None, expected
        case RuleType.COMPLIES:
            return None, None, None
    return low, high, expected


def _aliases(aliases: list[str], key: str) -> list[str]:
    """Return cleaned, unique aliases that differ from the test name."""
    out: list[str] = []
    for a in aliases:
        a = _clean(a)
        if a and normalize_name(a) != key and a not in out:
            out.append(a)
    return out


def validate_parameters(params: list[ParameterInput]) -> list[ParameterInput]:
    """Validate parameters for their rules and return cleaned copies."""
    if not params:
        raise WorkflowError("A spec needs at least one test.", 422)

    seen: dict[str, str] = {}
    cleaned: list[ParameterInput] = []
    for i, p in enumerate(params, start=1):
        name = _clean(p.name)
        label = f"Test {i}" if not name else f"“{name}”"
        if not name:
            raise WorkflowError(f"{label} has no name.", 422)

        key = normalize_name(name)
        if key in seen:
            raise WorkflowError(f"{label} appears twice in this spec.", 422)
        seen[key] = name

        low, high, expected = _limits(p, label)
        for tol, what in ((p.tolerance_pct, "percentage"), (p.tolerance_abs, "absolute")):
            if tol is not None and tol < 0:
                raise WorkflowError(f"{label}: the {what} tolerance can't be negative.", 422)

        aliases = _aliases(p.aliases, key)
        numeric = p.rule_type in (RuleType.MIN, RuleType.MAX, RuleType.RANGE)
        cleaned.append(
            ParameterInput(
                name=name,
                rule_type=p.rule_type,
                low=low,
                high=high,
                unit=_clean(p.unit) if numeric else None,
                expected_text=expected,
                aliases=aliases,
                method=_clean(p.method),
                critical=p.critical,
                tolerance_pct=p.tolerance_pct if numeric else None,
                tolerance_abs=p.tolerance_abs if numeric else None,
            )
        )
    return cleaned


def _parameters(params: list[ParameterInput]) -> list[SpecParameter]:
    """Build spec parameter rows."""
    return [
        SpecParameter(
            position=i,
            name=p.name,
            rule_type=p.rule_type,
            low=p.low,
            high=p.high,
            unit=p.unit,
            expected_text=p.expected_text,
            aliases=p.aliases,
            method=p.method,
            critical=p.critical,
            tolerance_pct=p.tolerance_pct,
            tolerance_abs=p.tolerance_abs,
        )
        for i, p in enumerate(params)
    ]


def current_spec(db: Session, customer_id: int, product_id: int, grade: str) -> Spec | None:
    """Return the active spec for a customer, product and grade."""
    return db.scalar(
        select(Spec).where(
            Spec.customer_id == customer_id,
            Spec.product_id == product_id,
            func.lower(Spec.grade) == grade.strip().lower(),
            Spec.status == SpecStatus.ACTIVE,
        )
    )


def create_spec(
    db: Session,
    *,
    customer_id: int,
    product_id: int,
    grade: str,
    parameters: list[ParameterInput],
    notes: str | None,
    actor: User,
    effective_from: date | None = None,
) -> Spec:
    """Create the first version of a spec."""
    grade = (grade or "").strip()
    if not grade:
        raise WorkflowError("Name the grade, for example “40% solution” or “Cosmetic grade”.", 422)
    customer = db.get(Customer, customer_id)
    product = db.get(Product, product_id)
    if customer is None or product is None:
        raise WorkflowError("Choose a customer and a product.", 422)
    if existing := current_spec(db, customer_id, product_id, grade):
        raise WorkflowError(
            f"{customer.name} already has a {product.name} spec for “{existing.grade}”. "
            "Edit it to create a new version.",
            409,
        )

    spec = Spec(
        customer=customer,
        product=product,
        grade=grade,
        version=1,
        status=SpecStatus.ACTIVE,
        effective_from=effective_from or date.today(),
        notes=_clean(notes),
        created_by_id=actor.id,
        parameters=_parameters(validate_parameters(parameters)),
    )
    db.add(spec)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="spec_created",
        entity_type="spec",
        entity_id=spec.id,
        customer=customer.name,
        product=product.name,
        grade=grade,
        tests=len(spec.parameters),
    )
    return spec


def new_version(
    db: Session,
    spec: Spec,
    *,
    parameters: list[ParameterInput],
    notes: str | None,
    actor: User,
) -> Spec:
    """Create the next version of a spec and retire the current one."""
    if spec.status != SpecStatus.ACTIVE:
        raise WorkflowError("Only the current version of a spec can be changed.", 409)

    latest = (
        db.scalar(
            select(func.max(Spec.version)).where(
                Spec.customer_id == spec.customer_id,
                Spec.product_id == spec.product_id,
                Spec.grade == spec.grade,
            )
        )
        or spec.version
    )
    spec.status = SpecStatus.SUPERSEDED
    db.flush()  # free the active slot before adding the new version
    successor = Spec(
        customer_id=spec.customer_id,
        product_id=spec.product_id,
        grade=spec.grade,
        version=latest + 1,
        status=SpecStatus.ACTIVE,
        effective_from=date.today(),
        notes=_clean(notes),
        created_by_id=actor.id,
        parameters=_parameters(validate_parameters(parameters)),
    )
    db.add(successor)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="spec_new_version",
        entity_type="spec",
        entity_id=successor.id,
        previous_spec_id=spec.id,
        version=successor.version,
        tests=len(successor.parameters),
    )
    return successor


def versions_of(db: Session, spec: Spec) -> list[Spec]:
    """Return every version of a spec, newest first."""
    return list(
        db.scalars(
            select(Spec)
            .where(
                Spec.customer_id == spec.customer_id,
                Spec.product_id == spec.product_id,
                Spec.grade == spec.grade,
            )
            .order_by(Spec.version.desc())
        )
    )


def open_lines_using(db: Session, spec_ids: list[int]) -> list[OrderLine]:
    """Return open order lines using any version of a spec."""
    if not spec_ids:
        return []
    return list(
        db.scalars(
            select(OrderLine)
            .join(Order)
            .where(OrderLine.spec_id.in_(spec_ids), Order.status != OrderStatus.SHIPPED)
            .order_by(Order.order_date.desc(), OrderLine.line_no)
        )
    )
