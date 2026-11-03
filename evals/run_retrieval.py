"""Retrieval eval: does knowledge search find the passage that answers a QC question?

  cd backend && uv run python ../evals/run_retrieval.py

Runs on the demo knowledge in a throwaway schema and writes evals/results/retrieval.md.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
os.environ.setdefault("BATCHGATE_BCRYPT_ROUNDS", "4")
os.environ.setdefault("BATCHGATE_CHECK_SCHEMA_ON_START", "false")

from collections.abc import Iterator  # noqa: E402
from contextlib import contextmanager  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402, F401
from app.core import migrations  # noqa: E402
from app.core.database import scratch_schema  # noqa: E402
from app.models import Customer, Product  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services import knowledge  # noqa: E402

QUESTIONS = ROOT / "retrieval" / "questions.json"
RESULTS = ROOT / "results" / "retrieval.md"


@contextmanager
def demo_db(schema: str = "batchgate_eval") -> Iterator[Session]:
    """Yield a session on the demo data in its own schema, dropped afterwards."""
    with scratch_schema(schema) as engine:
        migrations.upgrade(engine)
        with Session(engine, expire_on_commit=False) as db:
            seed(db)
            yield db


def label(hit: knowledge.Hit) -> str:
    """Return a hit's label as used in the questions file."""
    p = hit.passage
    if p.case is not None:
        return f"case:{p.case.batch_number}"
    return f"{p.document.title}|{p.section}"


def rank_of(hits: list[knowledge.Hit], answers: list[str]) -> int | None:
    """Return the rank of the first accepted answer, or None."""
    for i, h in enumerate(hits, start=1):
        if label(h) in answers:
            return i
    return None


def run(db: Session, questions: list[dict], *, expand: bool) -> list[dict]:
    """Search every question and record the rank of its answer."""
    customers = {c.name: c.id for c in db.scalars(select(Customer))}
    products = {p.name: p.id for p in db.scalars(select(Product))}
    rows = []
    for q in questions:
        hits = knowledge.search(
            db,
            q["q"],
            customer_id=customers.get(q.get("customer")),
            product_id=products.get(q.get("product")),
            limit=5,
            expand_synonyms=expand,
        )
        rows.append(
            {
                "q": q["q"],
                "rank": rank_of(hits, q["answers"]),
                "top": label(hits[0]) if hits else None,
            }
        )
    return rows


def metrics(rows: list[dict]) -> dict[str, float]:
    """Return hit@1, hit@3, hit@5 and mean reciprocal rank."""
    n = len(rows)
    ranks = [r["rank"] for r in rows]
    return {
        "hit@1": sum(1 for r in ranks if r == 1) / n,
        "hit@3": sum(1 for r in ranks if r and r <= 3) / n,
        "hit@5": sum(1 for r in ranks if r and r <= 5) / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
    }


def report(with_x: list[dict], without_x: list[dict]) -> str:
    """Render the results as Markdown."""
    a, b = metrics(with_x), metrics(without_x)
    pct = lambda v: f"{100 * v:.0f}%"  # noqa: E731
    lines = [
        "# Knowledge search: retrieval eval",
        "",
        f"{len(with_x)} QC questions against the demo knowledge base (4 documents, 4 past cases), "
        "scoped to each question's customer and product like the copilot's search.",
        "",
        "| | With spec-alias expansion | Without |",
        "|---|---|---|",
        f"| Right passage first (hit@1) | **{pct(a['hit@1'])}** | {pct(b['hit@1'])} |",
        f"| In the top 3 | **{pct(a['hit@3'])}** | {pct(b['hit@3'])} |",
        f"| In the top 5 (what the copilot sees) | **{pct(a['hit@5'])}** | {pct(b['hit@5'])} |",
        f"| Mean reciprocal rank | **{a['mrr']:.2f}** | {b['mrr']:.2f} |",
        "",
        "| Question | Rank of first right passage | Top result |",
        "|---|---|---|",
    ]
    for r in with_x:
        rank = r["rank"] if r["rank"] else "not in top 5"
        lines.append(f"| {r['q']} | {rank} | {str(r['top']).replace('|', ' › ')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Run the eval and write the report."""
    questions = json.loads(QUESTIONS.read_text())
    with demo_db() as db:
        with_x, without_x = run(db, questions, expand=True), run(db, questions, expand=False)
    text = report(with_x, without_x)
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
