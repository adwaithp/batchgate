# ruff: noqa: E501  (report lines read better unwrapped)
"""Copilot eval: does the brief cite the expected sources, and are its citations faithful?

cd backend && uv run python ../evals/run_copilot.py   # needs ANTHROPIC_API_KEY
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
os.environ.setdefault("BATCHGATE_CHECK_SCHEMA_ON_START", "false")
os.environ.setdefault("BATCHGATE_BCRYPT_ROUNDS", "4")

import anthropic  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models import Batch, KnowledgePassage  # noqa: E402
from app.schemas.copilot import Brief  # noqa: E402
from app.services import copilot  # noqa: E402

sys.path.insert(0, str(ROOT))
from run_retrieval import demo_db  # noqa: E402

RESULTS = ROOT / "results" / "copilot.md"

# Sources a QC expert would expect the brief to use.
EXPECTED = {
    "FC-2611-07": {
        "Ridgeway Industrial Supply: quality agreement|4.2 Retests",
        "Ridgeway Industrial Supply: quality agreement|4.3 Concessions",
        "Ridgeway Industrial Supply: quality agreement|5 Factory and laboratory results that disagree",
        "case:FC-2608-15",
        "case:FC-2606-02",
        "Method note: insoluble matter in ferric chloride solution|2 Common causes of high results",
        "Method note: insoluble matter in ferric chloride solution|4 Agreement between laboratories",
    },
    "PO-2611-A": {
        "Lumora Personal Care: quality agreement|4 Factory and laboratory results that disagree",
        "Lumora Personal Care: quality agreement|2.1 (Certificates of analysis)",
        "case:PO-2607-B",
        "SOP QC-07: handling out-of-specification and doubtful results|2 Phase 1: check the data (same day)",
    },
}


class Judgement(BaseModel):
    """A judge's verdict on one citation."""

    ref: str
    supported: bool
    reason: str


class Judgements(BaseModel):
    """All verdicts for one brief."""

    items: list[Judgement]


class Recorder:
    """Wraps the client and keeps every request."""

    def __init__(self, client):
        """Wrap the client."""
        self._client, self.requests = client, []
        self.messages = self

    def create(self, **kwargs):
        """Record the request and forward it."""
        self.requests.append(kwargs["messages"])
        return self._client.messages.create(**kwargs)


def label(p: KnowledgePassage) -> str:
    """Return a passage's label as used in the expectations."""
    return f"case:{p.case.batch_number}" if p.case else f"{p.document.title}|{p.section}"


def judge(client, brief: Brief, texts: dict[str, str]) -> list[Judgement]:
    """Ask a separate Claude call whether each cited passage supports its claim."""
    if not brief.sources:
        return []
    claims = "\n\n".join(
        f"[{c.ref}] claimed support: {c.supports}\nPassage: {texts[c.ref]}" for c in brief.sources
    )
    response = client.beta.messages.parse(
        model=get_settings().copilot_model,
        max_tokens=2000,
        system="You check citations. For each one, say whether the passage, read on its own, "
        "actually supports the claim. Be strict: partial or implied support is not support.",
        messages=[{"role": "user", "content": claims}],
        output_format=Judgements,
    )
    return response.parsed_output.items if response.parsed_output else []


def guardrail_sendbacks(requests: list) -> int:
    """Count briefs sent back by the citation check."""
    count = 0
    for messages in requests:
        last = messages[-1]
        if last["role"] == "user" and isinstance(last["content"], list):
            count += sum(
                1
                for r in last["content"]
                if isinstance(r, dict)
                and r.get("is_error")
                and "not returned by any search" in r["content"]
            )
    return count


def main() -> int:
    """Run the eval and write evals/results/copilot.md."""
    if not get_settings().anthropic_api_key:
        print("Set ANTHROPIC_API_KEY to run the copilot eval.")
        return 2
    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key, timeout=180)
    with demo_db() as db:
        rows = []
        for number, expected in EXPECTED.items():
            batch = db.scalar(select(Batch).where(Batch.batch_number == number))
            rec = Recorder(client)
            result = copilot.review_batch(db, batch, client=rec)
            passages = {
                f"K{p.id}": p
                for p in db.scalars(
                    select(KnowledgePassage).where(
                        KnowledgePassage.id.in_([int(s.ref[1:]) for s in result.brief.sources])
                    )
                )
            }
            cited = {label(passages[s.ref]) for s in result.brief.sources}
            verdicts = judge(client, result.brief, {r: p.text for r, p in passages.items()})
            rows.append(
                {
                    "batch": number,
                    "searches": result.looked_at.count("search_knowledge"),
                    "tools": len(result.looked_at),
                    "cited": sorted(cited),
                    "relevant": bool(cited & expected),
                    "supported": sum(v.supported for v in verdicts),
                    "judged": len(verdicts),
                    "unsupported": [f"{v.ref}: {v.reason}" for v in verdicts if not v.supported],
                    "sendbacks": guardrail_sendbacks(rec.requests),
                    "next_steps": result.brief.next_steps,
                }
            )
            print(json.dumps(rows[-1], indent=1))

    total_cites = sum(r["judged"] for r in rows)
    lines = [
        "# Review copilot eval",
        "",
        f"Model `{get_settings().copilot_model}` on the seeded batches that need a person, with the "
        "demo knowledge base. Citations are judged by a separate Claude call.",
        "",
        "| | Result |",
        "|---|---|",
        f"| Briefs that cited a source a QC expert would expect | {sum(r['relevant'] for r in rows)} / {len(rows)} |",
        f"| Citations the judge found supported | {sum(r['supported'] for r in rows)} / {total_cites} |",
        f"| Knowledge searches per brief | {', '.join(str(r['searches']) for r in rows)} |",
        f"| Briefs sent back for citing an unretrieved passage | {sum(r['sendbacks'] for r in rows)} |",
        "",
    ]
    for r in rows:
        lines += [
            f"## {r['batch']}",
            "",
            "Cited: " + "; ".join(c.replace("|", ", ") for c in r["cited"]),
            "",
        ]
        lines += [f"- {s}" for s in r["next_steps"]]
        if r["unsupported"]:
            lines += ["", "Judge flagged: " + "; ".join(r["unsupported"])]
        lines.append("")
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
