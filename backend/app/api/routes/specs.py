"""Specs API: customer specs, their versions, customers and form reference data."""

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.permissions import Permission, permissions_for
from app.models import Customer, Product, Spec, User
from app.models.enums import SpecStatus
from app.schemas.common import CustomerRef, ProductRef
from app.schemas.customers import CustomerCreate, ReferenceData
from app.schemas.specs import (
    CustomerSpecs,
    SpecCreate,
    SpecDetail,
    SpecLineUse,
    SpecNewVersion,
    SpecOption,
    SpecParameterFull,
    SpecSummary,
    SpecVersionBrief,
)
from app.services import specs as svc
from app.services.orders import can_see_customer, create_customer, visible_customer_ids
from app.services.rules.engine import spec_text
from app.services.rules.types import ParamSpec

router = APIRouter(tags=["specs"])

SpecViewer = Annotated[User, Depends(require(Permission.VIEW_SPECS))]
SpecEditor = Annotated[User, Depends(require(Permission.EDIT_SPECS))]
CustomerAdder = Annotated[User, Depends(require(Permission.ADD_CUSTOMERS))]
OrderEditor = Annotated[User, Depends(require(Permission.EDIT_ORDERS))]


def _summary(spec: Spec, open_lines: int) -> SpecSummary:
    """Map a spec to its list-row view."""
    return SpecSummary(
        id=spec.id,
        customer=CustomerRef.model_validate(spec.customer),
        product=ProductRef.model_validate(spec.product),
        grade=spec.grade,
        version=spec.version,
        status=spec.status,
        effective_from=spec.effective_from,
        tests=len(spec.parameters),
        critical_tests=sum(p.critical for p in spec.parameters),
        open_lines=open_lines,
        created_at=spec.created_at,
    )


def _user_name(db: DbSession, user_id: int | None) -> str | None:
    """Return a user's full name, or None."""
    user = db.get(User, user_id) if user_id else None
    return user.full_name if user else None


def _detail(db: DbSession, spec: Spec, viewer: User) -> SpecDetail:
    """Build a spec's detail view with versions and the lines using it."""
    versions = svc.versions_of(db, spec)
    current = next((v for v in versions if v.status == SpecStatus.ACTIVE), None)
    lines = svc.open_lines_using(db, [v.id for v in versions])
    version_of = {v.id: v.version for v in versions}
    return SpecDetail(
        **_summary(spec, sum(ln.spec_id == spec.id for ln in lines)).model_dump(),
        notes=spec.notes,
        created_by=_user_name(db, spec.created_by_id),
        parameters=[
            SpecParameterFull(
                id=p.id,
                name=p.name,
                rule_type=p.rule_type,
                low=p.low,
                high=p.high,
                unit=p.unit,
                expected_text=p.expected_text,
                aliases=list(p.aliases or []),
                method=p.method,
                critical=p.critical,
                tolerance_pct=p.tolerance_pct,
                tolerance_abs=p.tolerance_abs,
                spec_text=spec_text(
                    ParamSpec(p.id, p.name, p.rule_type, p.low, p.high, p.unit, p.expected_text)
                ),
            )
            for p in spec.parameters
        ],
        versions=[
            SpecVersionBrief(
                id=v.id,
                version=v.version,
                status=v.status,
                effective_from=v.effective_from,
                created_by=_user_name(db, v.created_by_id),
                created_at=v.created_at,
                notes=v.notes,
            )
            for v in versions
        ],
        current_version_id=current.id if current and current.id != spec.id else None,
        used_by=[
            SpecLineUse(
                line_id=ln.id,
                order_id=ln.order_id,
                po_number=ln.order.po_number,
                line_no=ln.line_no,
                quantity=ln.quantity,
                unit=ln.unit,
                spec_version=version_of[ln.spec_id],
            )
            for ln in lines
        ],
        can_edit=Permission.EDIT_SPECS in permissions_for(viewer.role)
        and spec.status == SpecStatus.ACTIVE,
    )


def _get_spec(db: DbSession, spec_id: int, viewer: User) -> Spec:
    """Load a spec visible to `viewer`, or raise 404."""
    spec = db.get(Spec, spec_id)
    if spec is None or not can_see_customer(viewer, spec.customer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Spec not found")
    return spec


def _params(body: SpecCreate | SpecNewVersion) -> list[svc.ParameterInput]:
    """Convert request parameters to service inputs."""
    return [svc.ParameterInput(**p.model_dump()) for p in body.parameters]


@router.get("/reference", response_model=ReferenceData)
def reference_data(db: DbSession, user: SpecViewer) -> ReferenceData:
    """Customers the user may see and all products, for the forms."""
    ids = visible_customer_ids(user)
    q = select(Customer).order_by(Customer.name)
    if ids is not None:
        q = q.where(Customer.id.in_(ids))
    return ReferenceData(
        customers=[CustomerRef.model_validate(c) for c in db.scalars(q)],
        products=[
            ProductRef.model_validate(p)
            for p in db.scalars(select(Product).order_by(Product.name))
        ],
    )


@router.post("/customers", response_model=CustomerRef, status_code=status.HTTP_201_CREATED)
def add_customer(db: DbSession, user: CustomerAdder, body: CustomerCreate) -> CustomerRef:
    """Add a customer; sales users are assigned to the customer they add."""
    customer = create_customer(
        db, name=body.name, country=body.country, industry=body.industry, actor=user
    )
    db.commit()
    return CustomerRef.model_validate(customer)


@router.get("/specs", response_model=list[SpecSummary])
def list_specs(
    db: DbSession,
    user: SpecViewer,
    include_old: Annotated[bool, Query(description="Also list replaced versions")] = False,
) -> list[SpecSummary]:
    """List current specs, optionally including superseded versions."""
    q = select(Spec)
    if not include_old:
        q = q.where(Spec.status == SpecStatus.ACTIVE)
    ids = visible_customer_ids(user)
    if ids is not None:
        q = q.where(Spec.customer_id.in_(ids))
    specs = list(db.scalars(q))
    specs.sort(key=lambda s: (s.customer.name, s.product.name, s.grade, -s.version))
    usage = Counter(ln.spec_id for ln in svc.open_lines_using(db, [s.id for s in specs]))
    return [_summary(s, usage[s.id]) for s in specs]


@router.get("/specs/{spec_id}", response_model=SpecDetail)
def get_spec(db: DbSession, user: SpecViewer, spec_id: int) -> SpecDetail:
    """Return one spec version in full."""
    return _detail(db, _get_spec(db, spec_id, user), user)


@router.post("/specs", response_model=SpecDetail, status_code=status.HTTP_201_CREATED)
def create_spec(db: DbSession, user: SpecEditor, body: SpecCreate) -> SpecDetail:
    """Create the first version of a spec."""
    spec = svc.create_spec(
        db,
        customer_id=body.customer_id,
        product_id=body.product_id,
        grade=body.grade,
        parameters=_params(body),
        notes=body.notes,
        actor=user,
    )
    db.commit()
    return _detail(db, spec, user)


@router.post("/specs/{spec_id}/versions", response_model=SpecDetail, status_code=201)
def create_version(
    db: DbSession, user: SpecEditor, spec_id: int, body: SpecNewVersion
) -> SpecDetail:
    """Create the next version of a spec; the old one is retired."""
    spec = _get_spec(db, spec_id, user)
    successor = svc.new_version(db, spec, parameters=_params(body), notes=body.notes, actor=user)
    db.commit()
    return _detail(db, successor, user)


@router.get("/customers/{customer_id}/specs", response_model=CustomerSpecs)
def customer_specs(db: DbSession, user: OrderEditor, customer_id: int) -> CustomerSpecs:
    """List the current specs an order line for this customer can use."""
    if not can_see_customer(user, customer_id) or db.get(Customer, customer_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    specs = db.scalars(
        select(Spec).where(Spec.customer_id == customer_id, Spec.status == SpecStatus.ACTIVE)
    )
    return CustomerSpecs(
        customer_id=customer_id,
        specs=sorted(
            (
                SpecOption(
                    id=s.id,
                    product_id=s.product_id,
                    product=s.product.name,
                    grade=s.grade,
                    version=s.version,
                )
                for s in specs
            ),
            key=lambda o: (o.product, o.grade),
        ),
    )
