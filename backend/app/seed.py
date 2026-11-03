"""Demo data: users for each role, fictional companies, illustrative specs, orders and batches.

uv run python -m app.seed          apply migrations, add demo data if missing
uv run python -m app.seed --reset  drop everything and start fresh
"""

import argparse
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import migrations
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import Customer, Order, OrderLine, Product, Spec, SpecParameter, Supplier, User
from app.models.enums import Role, RuleType, SupplierKind

DEMO_USERS = [
    {
        "email": "meera@batchgate.dev",
        "full_name": "Meera Nair",
        "role": Role.QC_MANAGER,
        "description": "Approves releases, edits specs, sees the audit log.",
    },
    {
        "email": "arjun@batchgate.dev",
        "full_name": "Arjun Rao",
        "role": Role.QC_ANALYST,
        "description": "Uploads COAs, runs checks, resolves review items.",
    },
    {
        "email": "sara@batchgate.dev",
        "full_name": "Sara Thomas",
        "role": Role.SALES,
        "description": "Enters and follows her customers' orders. Can't change specs.",
        "customers": ["Ridgeway Industrial Supply"],
    },
    {
        "email": "admin@batchgate.dev",
        "full_name": "Platform Admin",
        "role": Role.ADMIN,
        "description": "Manages users. Sees everything.",
    },
]

CUSTOMERS = [
    {"name": "Ridgeway Industrial Supply", "country": "US", "industry": "Water & Oilfield"},
    {"name": "Lumora Personal Care", "country": "US", "industry": "Home & Personal Care"},
]

PRODUCTS = [
    {
        "name": "Ferric Chloride",
        "cas_number": "7705-08-0",
        "industry": "Water Treatment",
        "synonyms": ["Iron(III) chloride", "FeCl3", "Ferric chloride solution"],
    },
    {
        "name": "MEA Triazine",
        "cas_number": "4719-04-4",
        "industry": "Oilfield & Gas",
        "synonyms": ["Hexahydro-1,3,5-tris(hydroxyethyl)-s-triazine", "H2S scavenger"],
    },
    {
        "name": "Piroctone Olamine",
        "cas_number": "68890-66-4",
        "industry": "Home & Personal Care",
        "synonyms": ["Octopirox"],
    },
]

SUPPLIERS = [
    {
        "name": "Kutch Coastal Chemicals",
        "kind": SupplierKind.FACTORY,
        "country": "IN",
        "city": "Bhuj",
    },
    {
        "name": "Dahej Specialty Organics",
        "kind": SupplierKind.FACTORY,
        "country": "IN",
        "city": "Bharuch",
    },
    {
        "name": "Ruwais Process Chemicals",
        "kind": SupplierKind.FACTORY,
        "country": "AE",
        "city": "Ruwais",
    },
    {
        "name": "Northbridge Analytical Labs",
        "kind": SupplierKind.LAB,
        "country": "IN",
        "city": "Hyderabad",
    },
]


def _p(
    name,
    rule,
    *,
    low=None,
    high=None,
    unit=None,
    text=None,
    aliases=(),
    method=None,
    critical=True,
):
    """Build one spec parameter definition."""
    return {
        "name": name,
        "rule_type": rule,
        "low": low,
        "high": high,
        "unit": unit,
        "expected_text": text,
        "aliases": list(aliases),
        "method": method,
        "critical": critical,
    }


SPECS = [
    {
        "customer": "Ridgeway Industrial Supply",
        "product": "Ferric Chloride",
        "grade": "40% solution",
        "parameters": [
            _p(
                "Ferric chloride (FeCl3)",
                RuleType.MIN,
                low=40.0,
                unit="%",
                aliases=["FeCl3 content", "Assay as FeCl3"],
            ),
            _p(
                "Iron (as Fe)",
                RuleType.MIN,
                low=13.8,
                unit="%",
                aliases=["Fe", "Fe content", "Total iron"],
            ),
            _p(
                "Free acid (as HCl)",
                RuleType.MAX,
                high=0.5,
                unit="%",
                aliases=["Free HCl", "Free acidity"],
            ),
            _p(
                "Ferrous iron (Fe2+)",
                RuleType.MAX,
                high=0.25,
                unit="%",
                aliases=["Fe(II)", "Ferrous as Fe"],
            ),
            _p(
                "Insoluble matter",
                RuleType.MAX,
                high=0.1,
                unit="%",
                aliases=["Insolubles", "Water insolubles"],
            ),
            _p(
                "Specific gravity @ 25 °C",
                RuleType.RANGE,
                low=1.40,
                high=1.45,
                aliases=["SG", "Density ratio"],
            ),
            _p("Appearance", RuleType.TEXT_MATCH, text="Dark brown liquid", critical=False),
        ],
    },
    {
        "customer": "Ridgeway Industrial Supply",
        "product": "MEA Triazine",
        "grade": "78% active",
        "parameters": [
            _p(
                "Active content",
                RuleType.MIN,
                low=78.0,
                unit="%",
                aliases=["Triazine content", "Assay", "Active matter"],
            ),
            _p(
                "Free MEA",
                RuleType.MAX,
                high=2.0,
                unit="%",
                aliases=["Free monoethanolamine", "Residual MEA"],
            ),
            _p("pH (neat)", RuleType.RANGE, low=9.5, high=11.0, aliases=["pH"]),
            _p("Specific gravity @ 25 °C", RuleType.RANGE, low=1.14, high=1.17, aliases=["SG"]),
            _p(
                "Appearance", RuleType.TEXT_MATCH, text="Clear, pale yellow liquid", critical=False
            ),
        ],
    },
    {
        "customer": "Ridgeway Industrial Supply",
        "product": "MEA Triazine",
        "grade": "40% active",
        "parameters": [
            _p(
                "Active content",
                RuleType.RANGE,
                low=40.0,
                high=44.0,
                unit="%",
                aliases=["Triazine content", "Assay", "Active matter"],
            ),
            _p(
                "Free MEA",
                RuleType.MAX,
                high=1.0,
                unit="%",
                aliases=["Free monoethanolamine", "Residual MEA"],
            ),
            _p("pH (neat)", RuleType.RANGE, low=9.0, high=11.0, aliases=["pH"]),
            _p("Specific gravity @ 25 °C", RuleType.RANGE, low=1.07, high=1.10, aliases=["SG"]),
            _p(
                "Appearance", RuleType.TEXT_MATCH, text="Clear, pale yellow liquid", critical=False
            ),
        ],
    },
    {
        "customer": "Lumora Personal Care",
        "product": "Piroctone Olamine",
        "grade": "Cosmetic grade",
        "parameters": [
            _p(
                "Assay (HPLC)",
                RuleType.RANGE,
                low=98.0,
                high=101.0,
                unit="%",
                aliases=["Purity", "Assay"],
                method="HPLC",
            ),
            _p("Loss on drying", RuleType.MAX, high=0.5, unit="%", aliases=["LOD", "Moisture"]),
            _p(
                "Heavy metals (as Pb)", RuleType.MAX, high=10, unit="ppm", aliases=["Heavy metals"]
            ),
            _p(
                "Sulphated ash",
                RuleType.MAX,
                high=0.2,
                unit="%",
                aliases=["Sulfated ash", "Residue on ignition"],
            ),
            _p(
                "Melting range",
                RuleType.RANGE,
                low=130,
                high=135,
                unit="°C",
                aliases=["Melting point"],
                critical=False,
            ),
            _p("Identification (IR)", RuleType.COMPLIES, aliases=["IR", "Identity"]),
            _p(
                "Appearance",
                RuleType.TEXT_MATCH,
                text="White to off-white crystalline powder",
                critical=False,
            ),
        ],
    },
]

# Allowed factory-vs-lab difference; unlisted tests use the engine default.
TOLERANCES = {
    "Free acid (as HCl)": {"tolerance_abs": 0.05},
    "Ferrous iron (Fe2+)": {"tolerance_abs": 0.03},
    "Insoluble matter": {"tolerance_abs": 0.02},
    "Specific gravity @ 25 °C": {"tolerance_abs": 0.005},
    "Free MEA": {"tolerance_abs": 0.2},
    "pH (neat)": {"tolerance_abs": 0.2},
    "Assay (HPLC)": {"tolerance_pct": 1.0},  # purity assays need a tighter match
    "Loss on drying": {"tolerance_abs": 0.1},
    "Heavy metals (as Pb)": {"tolerance_abs": 2},
    "Sulphated ash": {"tolerance_abs": 0.03},
    "Melting range": {"tolerance_abs": 1.0},
}

ORDERS = [
    {
        # The same product on two lines at two grades.
        "po_number": "PO-1042",
        "customer": "Ridgeway Industrial Supply",
        "order_date": date(2026, 10, 20),
        "lines": [
            ("Ferric Chloride", "40% solution", 20),
            ("MEA Triazine", "78% active", 10),
            ("MEA Triazine", "40% active", 10),
        ],
    },
    {
        "po_number": "PO-2001",
        "customer": "Lumora Personal Care",
        "order_date": date(2026, 10, 27),
        "lines": [("Piroctone Olamine", "Cosmetic grade", 0.5)],
    },
]


def _get_or_create(db: Session, model, lookup: dict, **values):
    """Return the row matching `lookup`, creating it with `values` if missing."""
    obj = db.scalar(select(model).filter_by(**lookup))
    if obj is None:
        obj = model(**lookup, **values)
        db.add(obj)
        db.flush()
    return obj


def seed(db: Session, *, demo_batches: bool = True) -> None:
    """Add the demo users, catalog, specs, orders, batches and knowledge."""
    settings = get_settings()

    customers = {
        c["name"]: _get_or_create(
            db, Customer, {"name": c["name"]}, country=c["country"], industry=c["industry"]
        )
        for c in CUSTOMERS
    }
    products = {
        p["name"]: _get_or_create(
            db,
            Product,
            {"name": p["name"]},
            cas_number=p["cas_number"],
            industry=p["industry"],
            synonyms=p["synonyms"],
        )
        for p in PRODUCTS
    }
    for s in SUPPLIERS:
        _get_or_create(
            db, Supplier, {"name": s["name"]}, kind=s["kind"], country=s["country"], city=s["city"]
        )

    for u in DEMO_USERS:
        user = _get_or_create(
            db,
            User,
            {"email": u["email"]},
            full_name=u["full_name"],
            role=u["role"],
            hashed_password=hash_password(settings.demo_password),
        )
        user.customers = [customers[name] for name in u.get("customers", [])]

    specs: dict[tuple[str, str, str], Spec] = {}
    for s in SPECS:
        key = (s["customer"], s["product"], s["grade"])
        spec = db.scalar(
            select(Spec).filter_by(
                customer_id=customers[s["customer"]].id,
                product_id=products[s["product"]].id,
                grade=s["grade"],
                version=1,
            )
        )
        if spec is None:
            spec = Spec(
                customer=customers[s["customer"]],
                product=products[s["product"]],
                grade=s["grade"],
                version=1,
                effective_from=date(2026, 1, 1),
                notes="Illustrative spec for the demo.",
                parameters=[
                    SpecParameter(position=i, **p, **TOLERANCES.get(p["name"], {}))
                    for i, p in enumerate(s["parameters"])
                ],
            )
            db.add(spec)
            db.flush()
        specs[key] = spec

    for o in ORDERS:
        if db.scalar(select(Order).filter_by(po_number=o["po_number"])):
            continue
        db.add(
            Order(
                po_number=o["po_number"],
                customer=customers[o["customer"]],
                order_date=o["order_date"],
                lines=[
                    OrderLine(
                        line_no=i,
                        product=products[product],
                        spec=specs[(o["customer"], product, grade)],
                        quantity=qty,
                        unit="t",
                    )
                    for i, (product, grade, qty) in enumerate(o["lines"], start=1)
                ],
            )
        )

    db.commit()
    if demo_batches:
        seed_batches(db)
        from app.seed_knowledge import seed_knowledge

        seed_knowledge(db)


# Created through the real workflow so the engine decides each one.

_FC_HEADER = {
    "product_name": "Ferric Chloride Solution 40%",
    "cas_number": "7705-08-0",
    "mfg_date": date(2026, 10, 24),
    "test_date": date(2026, 10, 26),
    "expiry_date": date(2028, 10, 23),
}
_FC_ROWS = [
    ("FeCl3 content", "40.6", "%"),
    ("Total iron (as Fe)", "13.9", "%"),
    ("Free acid (as HCl)", "0.31", "%"),
    ("Ferrous iron (Fe2+)", "0.12", "%"),
    ("Insoluble matter", "0.05", "%"),
    ("Specific gravity @ 25 °C", "1.42", None),
    ("Appearance", "Dark brown liquid", None),
]

_MT78_HEADER = {
    "product_name": "MEA Triazine 78%",
    "cas_number": "4719-04-4",
    "mfg_date": date(2026, 10, 18),
    "test_date": date(2026, 10, 20),
    "expiry_date": date(2028, 10, 17),
}
_MT78_ROWS = [
    ("Active content", "78.9", "%"),
    ("Free MEA", "1.1", "%"),
    ("pH", "10.4", None),
    ("SG", "1.155", None),
    ("Appearance", "Clear, pale yellow liquid", None),
]

_MT40_HEADER = {
    "product_name": "Triazine H2S scavenger (40% active)",
    "cas_number": "4719-04-4",
    "mfg_date": date(2026, 10, 28),
    "test_date": date(2026, 10, 30),
    "expiry_date": date(2028, 10, 27),
}
_MT40_ROWS = [
    ("Triazine content", "41.8", "%"),
    ("Free MEA", "0.6", "%"),
    ("pH (neat)", "10.1", None),
    ("Specific gravity", "1.085", None),
    ("Appearance", "Clear pale yellow liquid", None),
]

_PO_HEADER = {
    "product_name": "Piroctone Olamine",
    "cas_number": "68890-66-4",
    "mfg_date": date(2026, 10, 21),
    "test_date": date(2026, 10, 23),
    "expiry_date": date(2028, 10, 20),
}
_PO_ROWS = [
    ("Assay (HPLC)", "99.6", "%"),
    ("Loss on drying", "0.21", "%"),
    ("Heavy metals", "< 10", "ppm"),
    ("Sulfated ash", "0.06", "%"),
    ("Melting range", "131.0 – 133.5", "°C"),
    ("Identification (IR)", "Complies", None),
    ("Appearance", "White crystalline powder", None),
]


def _swap(rows, name, value):
    """Return result rows with one test's value replaced."""
    return [(n, value if n == name else v, u) for n, v, u in rows]


def seed_batches(db: Session) -> None:
    """Create the demo batches through the real workflow."""
    from app.models import Batch
    from app.models.enums import CoaSource
    from app.services import batches as svc

    if db.scalar(select(Batch.id).limit(1)):
        return

    analyst = db.scalar(select(User).where(User.email == "arjun@batchgate.dev"))
    supplier = {s.name: s for s in db.scalars(select(Supplier))}
    product = {p.name: p for p in db.scalars(select(Product))}
    lines = {(ln.order.po_number, ln.line_no): ln for ln in db.scalars(select(OrderLine))}
    lab = supplier["Northbridge Analytical Labs"]

    def make(batch_number, product_name, factory, line, qty, coas):
        """Register a batch and save its COAs, letting the engine decide."""
        batch = svc.get_or_create_batch(
            db,
            batch_number=batch_number,
            product_id=product[product_name].id,
            factory_id=supplier[factory].id,
            line_id=lines[line].id if line else None,
            quantity=qty,
            actor=analyst,
        )
        for source, header, rows in coas:
            coa = svc.ingest_coa(
                db,
                batch=batch,
                source=source,
                issuer_id=lab.id if source == CoaSource.LAB else None,
                file=None,
                actor=analyst,
            )
            svc.save_coa_data(
                db,
                coa,
                svc.CoaHeader(
                    batch_number=batch_number,
                    issuer_name=factory if source == CoaSource.FACTORY else lab.name,
                    **header,
                ),
                [svc.CoaRow(name, value, unit) for name, value, unit in rows],
                actor=analyst,
            )
        return batch

    from_factory, from_lab = CoaSource.FACTORY, CoaSource.LAB

    # Hold: the lab finds insoluble matter above the limit.
    make(
        "FC-2611-07",
        "Ferric Chloride",
        "Kutch Coastal Chemicals",
        ("PO-1042", 1),
        10,
        [
            (from_factory, _FC_HEADER, _FC_ROWS),
            (
                from_lab,
                {**_FC_HEADER, "product_name": "Ferric chloride solution"},
                _swap(_FC_ROWS, "Insoluble matter", "0.14"),
            ),
        ],
    )
    # Registered, awaiting its COAs.
    make("FC-2611-12", "Ferric Chloride", "Kutch Coastal Chemicals", ("PO-1042", 1), 10, [])
    # Clean on both COAs: awaiting a QC manager's approval.
    make(
        "MT-2610-31",
        "MEA Triazine",
        "Dahej Specialty Organics",
        ("PO-1042", 2),
        10,
        [
            (from_factory, _MT78_HEADER, _MT78_ROWS),
            (from_lab, _MT78_HEADER, _swap(_MT78_ROWS, "Active content", "78.6")),
        ],
    )
    # No order line: fits the 40 % grade (line 3), fails the 78 % grade (line 2).
    make(
        "MT-2611-04",
        "MEA Triazine",
        "Ruwais Process Chemicals",
        None,
        10,
        [
            (from_factory, _MT40_HEADER, _MT40_ROWS),
            (from_lab, _MT40_HEADER, _swap(_MT40_ROWS, "Triazine content", "41.5")),
        ],
    )
    # Review: factory and lab assay differ by more than 1 %.
    make(
        "PO-2611-A",
        "Piroctone Olamine",
        "Dahej Specialty Organics",
        ("PO-2001", 1),
        0.5,
        [
            (from_factory, _PO_HEADER, _PO_ROWS),
            (from_lab, _PO_HEADER, _swap(_PO_ROWS, "Assay (HPLC)", "98.3")),
        ],
    )
    db.commit()


def main() -> None:
    """Apply migrations and seed; with --reset, drop everything first."""
    parser = argparse.ArgumentParser(description="Seed BatchGate demo data")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    args = parser.parse_args()

    import app.models  # noqa: F401  (register tables)

    if args.reset:
        Base.metadata.drop_all(engine)
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    migrations.upgrade(engine)
    with SessionLocal() as db:
        seed(db)
    print("Seeded demo data. Demo password:", get_settings().demo_password)


if __name__ == "__main__":
    main()
