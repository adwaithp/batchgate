"""Review copilot: Claude explains a batch that needs a person and drafts a follow-up.

A tool-use loop over read-only lookups and knowledge base search. Citations are checked in code,
and nothing is written.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Batch, Product, Supplier, Verdict
from app.schemas.copilot import Brief
from app.services.batches import active_coas, latest_verdict

MAX_TURNS = 10

SYSTEM_PROMPT = """You help a QC analyst at a specialty chemicals company deal with a batch that \
BatchGate did not release. BatchGate's rules engine already made the decision (release, review or \
hold) by comparing the COAs with the customer's spec. You do not decide and you never suggest the \
batch is fine to ship: you explain what the engine found and what a person should do next.

Use the tools to look things up. Only state facts that came from a tool; if something isn't \
there, say it isn't known. Use the exact test names, values and limits from the tools.

Before advising what to do, search the knowledge base: what this customer's quality agreement \
allows (retests, concessions, notice to the customer), what the SOPs say, what can go wrong with \
the test method, and how similar past cases ended. Search with a few specific words ("retest \
policy", "concession insoluble matter", "notification hold") and search more than once for \
different questions. Cite what you rely on with its ref in square brackets, e.g. "[K12]", and \
list each cited ref in sources with what it supports. Only cite refs a search returned.

When you have enough, call submit_brief once:
- explanation: 2-4 plain sentences on why this batch needs a person. Lead with what blocks \
release.
- next_steps: 1-4 short, concrete actions for the analyst, each citing its source where one \
applies.
- history_note: only if the factory's past batches show a pattern worth knowing (a recurring \
failure, a drifting value). Otherwise null.
- email: a short, polite email the analyst can send to whoever must act (usually the factory; \
the lab if its COA is missing or unclear), asking for exactly what is missing or wrong. Plain \
text, no placeholders other than the recipient's name. Null if no email would help.

Write for a busy QC analyst: plain words, no jargon, no filler."""


TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_verdict",
        "description": "The rules engine's latest decision for this batch: every finding, the "
        "parameter-by-parameter results for the factory and lab COAs, and identity checks.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_spec",
        "description": "The customer spec this batch is checked against: each test with its "
        "limit, unit, whether it is critical, and the allowed factory-vs-lab difference.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_coa_readings",
        "description": "What was read from each COA for this batch: issuer, product, dates, every "
        "result row as printed with Claude's confidence, and any reading warnings.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_order_line",
        "description": "The customer order line this batch is for: customer, PO, grade, "
        "quantity, and the other batches on the line.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_factory_history",
        "description": "This factory's recent batches of the same product (other orders too): "
        "decision, status and the values reported, newest first. Use it to spot patterns.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
        },
    },
    {
        "name": "search_knowledge",
        "description": "Search the QC knowledge base for this batch's customer and product: "
        "quality agreements (what the customer allows: retests, concessions, notice), internal "
        "SOPs, test method notes, and past cases (what went wrong before and how it ended). "
        "Returns passages with a ref like K12 to cite.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A few specific words"},
                "look_in": {
                    "type": "string",
                    "enum": ["everything", "documents", "past_cases"],
                    "default": "everything",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "submit_brief",
        "description": "Hand back the finished brief. Call exactly once, at the end.",
        "input_schema": Brief.model_json_schema(),
    },
]


class CopilotError(Exception):
    """The brief could not be produced; the message is shown to the user."""


@dataclass
class Source:
    """A passage the copilot cited, resolved for display."""

    ref: str
    title: str
    link: str
    supports: str


@dataclass
class CopilotResult:
    """The brief plus the tools used and the cited sources."""

    brief: Brief
    looked_at: list[str] = field(default_factory=list)
    model: str = ""
    sources: list[Source] = field(default_factory=list)


def _verdict(batch: Batch) -> dict:
    """Tool: the latest verdict with findings and per-parameter results."""
    v = latest_verdict(batch)
    if v is None:
        return {"verdict": None, "note": "No check has run yet (COA values not in)."}
    d = v.details or {}
    return {
        "decision": v.decision.value,
        "summary": v.summary,
        "checked_at": v.created_at.isoformat(),
        "findings": d.get("findings", []),
        "parameters": d.get("parameters", []),
        "identity": d.get("identity", []),
        "unmatched_rows": d.get("unmatched", []),
    }


def _spec(batch: Batch) -> dict:
    """Tool: the spec the batch is checked against."""
    if batch.line is None:
        return {"spec": None, "note": "The batch isn't on an order line yet, so there's no spec."}
    s = batch.line.spec
    return {
        "customer": s.customer.name,
        "product": s.product.name,
        "grade": s.grade,
        "version": s.version,
        "tests": [
            {
                "name": p.name,
                "rule": p.rule_type.value,
                "low": p.low,
                "high": p.high,
                "unit": p.unit,
                "expected_text": p.expected_text,
                "critical": p.critical,
                "tolerance_abs": p.tolerance_abs,
                "tolerance_pct": p.tolerance_pct,
            }
            for p in s.parameters
        ],
    }


def _readings(batch: Batch) -> dict:
    """Tool: what was read from each active COA."""
    coas = []
    for c in active_coas(batch):
        warnings = (c.raw_extraction or {}).get("warnings", []) if c.raw_extraction else []
        coas.append(
            {
                "source": c.source.value,
                "issuer_printed": c.issuer_name,
                "issuer_expected": (
                    batch.factory.name
                    if c.source.value == "factory" and batch.factory
                    else (c.issuer.name if c.issuer else None)
                ),
                "product_printed": c.product_name,
                "batch_printed": c.batch_number,
                "mfg_date": c.mfg_date_as_printed or (c.mfg_date and c.mfg_date.isoformat()),
                "expiry": c.expiry_date_as_printed
                or (c.expiry_date and c.expiry_date.isoformat()),
                "read_by": c.extraction_model or "typed in by a person",
                "status": c.extraction_status.value,
                "rows": [
                    {
                        "name": r.name_as_written,
                        "value": r.raw_value,
                        "unit": r.unit,
                        "confidence": r.confidence,
                    }
                    for r in c.results
                ],  # fmt: skip
                "warnings": warnings,
            }
        )
    missing = {"factory", "lab"} - {c["source"] for c in coas}
    return {"coas": coas, "not_received": sorted(missing)}


def _order_line(batch: Batch) -> dict:
    """Tool: the batch's order line and its other batches."""
    line = batch.line
    if line is None:
        return {"line": None, "note": "Not assigned to an order line yet."}
    return {
        "customer": line.order.customer.name,
        "po_number": line.order.po_number,
        "line_no": line.line_no,
        "grade": line.spec.grade,
        "quantity": f"{line.quantity:g} {line.unit}",
        "other_batches": [
            {"batch": b.batch_number, "status": b.status.value}
            for b in line.batches
            if b.id != batch.id
        ],
    }


def factory_history(
    db: Session, factory: Supplier, product: Product, *, exclude_id: int | None = None, limit=10
) -> dict:
    """Return the factory's recent batches of a product, newest first."""
    q = (
        select(Batch)
        .where(Batch.factory_id == factory.id, Batch.product_id == product.id)
        .order_by(Batch.created_at.desc())
        .limit(min(max(int(limit), 1), 20))
    )
    if exclude_id is not None:
        q = q.where(Batch.id != exclude_id)
    rows = []
    for b in db.scalars(q):
        v: Verdict | None = latest_verdict(b)
        values = {}
        for p in (v.details or {}).get("parameters", []) if v else []:
            reads = [f"{r['source']} {r['raw_value']}" for r in p.get("readings", [])]
            if reads:
                values[p["name"]] = ", ".join(reads)
        rows.append(
            {
                "batch": b.batch_number,
                "registered": b.created_at.date().isoformat(),
                "status": b.status.value,
                "decision": v.decision.value if v else None,
                "summary": v.summary if v else None,
                "values": values,
            }
        )
    return {"factory": factory.name, "product": product.name, "batches": rows}


def _history(db: Session, batch: Batch, limit: int = 10) -> dict:
    """Tool: this batch's factory history."""
    if batch.factory is None:
        return {"batches": [], "note": "No factory recorded for this batch."}
    return factory_history(db, batch.factory, batch.product, exclude_id=batch.id, limit=limit)


def _search(db: Session, batch: Batch, args: dict, found: dict[str, dict]) -> dict:
    """Tool: search the knowledge base scoped to the batch's customer and product."""
    from app.services import knowledge  # avoids a circular import

    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "Give a few words to search for."}
    kinds = {"documents": {"document"}, "past_cases": {"case"}}.get(args.get("look_in") or "")
    hits = knowledge.search(
        db,
        query,
        customer_id=batch.line.order.customer_id if batch.line else None,
        product_id=batch.product_id,
        kinds=kinds,
        limit=5,
    )
    results = []
    for h in hits:
        found[h.ref] = {"title": h.source, "link": h.link}
        results.append({"ref": h.ref, "source": h.source, "text": h.passage.text})
    return (
        {"query": query, "results": results}
        if results
        else {
            "query": query,
            "results": [],
            "note": "Nothing found. Try other words.",
        }
    )


def run_tool(
    db: Session, batch: Batch, name: str, args: dict, found: dict[str, dict] | None = None
) -> dict:
    """Run one tool call and return its JSON-serialisable result."""
    match name:
        case "get_verdict":
            return _verdict(batch)
        case "get_spec":
            return _spec(batch)
        case "get_coa_readings":
            return _readings(batch)
        case "get_order_line":
            return _order_line(batch)
        case "get_factory_history":
            return _history(db, batch, int(args.get("limit") or 10))
        case "search_knowledge":
            return _search(db, batch, args, found if found is not None else {})
    return {"error": f"Unknown tool {name}"}


_CITED = re.compile(r"\[(K\d+)\]")


def _brief_text(brief: Brief) -> str:
    """Return all of a brief's text, for finding citation markers."""
    return " ".join(
        [brief.explanation, *brief.next_steps, brief.history_note or ""]
        + ([brief.email.body] if brief.email else [])
    )


def check_citations(brief: Brief, found: dict[str, dict]) -> list[str]:
    """Return refs the brief cites that no search returned."""
    cited = {c.ref for c in brief.sources} | set(_CITED.findall(_brief_text(brief)))
    return sorted(cited - set(found))


def _intro(batch: Batch) -> str:
    """Return the opening user message describing the batch."""
    v = latest_verdict(batch)
    return (
        f"Batch {batch.batch_number} ({batch.product.name}, made by "
        f"{batch.factory.name if batch.factory else 'an unknown factory'}) is "
        f"{batch.status.value.replace('_', ' ')}. "
        + (f"BatchGate's decision: {v.decision.value}. " if v else "No check has run yet. ")
        + "Look up what you need, then submit the brief."
    )


def _call_claude(client: anthropic.Anthropic, model: str, messages: list[dict]):
    """Send one turn to Claude, turning API failures into CopilotError."""
    try:
        response = client.messages.create(
            model=model, max_tokens=4000, system=SYSTEM_PROMPT, tools=TOOLS, messages=messages
        )
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        raise CopilotError("Couldn't reach Claude. Try again later.") from e
    except anthropic.RateLimitError as e:
        raise CopilotError("Claude is busy right now. Try again in a minute.") from e
    except anthropic.APIStatusError as e:
        raise CopilotError(f"Claude returned an error ({e.status_code}).") from e
    if response.stop_reason == "refusal":
        raise CopilotError("Claude declined to write this brief.")
    return response


def _accept_brief(block, found: dict[str, dict]) -> tuple[Brief | None, dict | None]:
    """Validate a submitted brief; return it, or the error to send back to Claude."""
    try:
        brief = Brief.model_validate(block.input)
    except ValidationError as e:
        return None, _tool_result(block.id, {"error": str(e)}, error=True)
    if unknown := check_citations(brief, found):
        error = (
            f"These refs were not returned by any search: {', '.join(unknown)}. "
            "Cite only refs from search results, or search again."
        )
        return None, _tool_result(block.id, {"error": error}, error=True)
    return brief, None


def _resolve_sources(brief: Brief, found: dict[str, dict]) -> list[Source]:
    """Resolve the brief's citations, adding refs cited in the text but not listed."""
    sources = [
        Source(c.ref, found[c.ref]["title"], found[c.ref]["link"], c.supports)
        for c in brief.sources
    ]
    listed = {c.ref for c in brief.sources}
    for ref in dict.fromkeys(_CITED.findall(_brief_text(brief))):
        if ref not in listed:
            sources.append(
                Source(ref, found[ref]["title"], found[ref]["link"], "Cited in the brief.")
            )
    return sources


def review_batch(
    db: Session, batch: Batch, *, client: anthropic.Anthropic | None = None
) -> CopilotResult:
    """Run the copilot loop for a batch and return the checked brief."""
    settings = get_settings()
    if client is None:
        if not settings.anthropic_api_key:
            raise CopilotError("Claude isn't set up on this server (no API key).")
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=120)

    messages: list[dict] = [{"role": "user", "content": _intro(batch)}]
    looked_at: list[str] = []
    found: dict[str, dict] = {}  # passages returned by any search, by ref
    nudged = False
    for _ in range(MAX_TURNS):
        response = _call_claude(client, settings.copilot_model, messages)
        messages.append({"role": "assistant", "content": response.content})

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "submit_brief":
                brief, error = _accept_brief(block, found)
                if brief is None:
                    results.append(error)
                    continue
                sources = _resolve_sources(brief, found)
                return CopilotResult(brief, looked_at, settings.copilot_model, sources)
            looked_at.append(block.name)
            results.append(
                _tool_result(block.id, run_tool(db, batch, block.name, block.input, found))
            )

        if results:
            messages.append({"role": "user", "content": results})
        elif not nudged:  # answered in prose instead of submitting: ask once more
            nudged = True
            messages.append({"role": "user", "content": "Please call submit_brief now."})
        else:
            break
    raise CopilotError("Claude couldn't finish the brief. Try again.")


def _tool_result(tool_use_id: str, data: dict, *, error: bool = False) -> dict:
    """Build a tool_result content block."""
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(data, default=str),
        "is_error": error,
    }
