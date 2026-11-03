"""Review copilot: read-only tools, citation checks and the structured brief."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import AuditLog, Batch, Verdict
from app.services import copilot

ANALYST = "arjun@batchgate.dev"
SALES = "sara@batchgate.dev"

BRIEF = {
    "explanation": "The lab COA shows insoluble matter at 0.14 %, above the 0.1 % limit.",
    "next_steps": ["Ask the factory for a retest of insoluble matter.", "Keep the batch on hold."],
    "history_note": None,
    "email": {
        "to": "factory",
        "subject": "FC-2611-07: insoluble matter above spec",
        "body": "Hello,\n\nThe lab measured 0.14 % insoluble matter (limit 0.1 %). Please retest.",
    },
}


def tool_use(name, args=None, id_="t"):
    """Build a fake tool_use content block."""
    return SimpleNamespace(type="tool_use", id=f"{id_}-{name}", name=name, input=args or {})


def text(t):
    """Build a fake text content block."""
    return SimpleNamespace(type="text", text=t)


class FakeClaude:
    """Plays back scripted turns and records every request."""

    def __init__(self, *turns):
        """Queue the scripted turns."""
        self.turns = list(turns)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        """Record the request and return the next scripted turn."""
        self.requests.append(json.loads(json.dumps(kwargs["messages"], default=str)))
        content = self.turns.pop(0)
        stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        return SimpleNamespace(content=content, stop_reason=stop)


def held_batch(db):
    """Return the held demo batch FC-2611-07."""
    return db.scalar(select(Batch).where(Batch.batch_number == "FC-2611-07"))


def tool_results(request):
    """Return the tool results in the last user message, by tool_use id."""
    return {r["tool_use_id"]: json.loads(r["content"]) for r in request[-1]["content"]}


def test_agent_looks_things_up_then_submits_a_brief(db_session):
    fake = FakeClaude(
        [text("Let me look."), tool_use("get_verdict"), tool_use("get_factory_history")],
        [tool_use("get_spec")],
        [tool_use("submit_brief", BRIEF)],
    )
    result = copilot.review_batch(db_session, held_batch(db_session), client=fake)

    assert result.looked_at == ["get_verdict", "get_factory_history", "get_spec"]
    assert result.brief.email.to == "factory"
    first = tool_results(fake.requests[1])
    verdict = first["t-get_verdict"]
    assert verdict["decision"] == "hold"
    assert any("Insoluble matter" in f["message"] for f in verdict["findings"])
    history = first["t-get_factory_history"]
    assert history["factory"] == "Kutch Coastal Chemicals"
    assert all(b["batch"] != "FC-2611-07" for b in history["batches"])  # only the other batches
    spec = tool_results(fake.requests[2])["t-get_spec"]
    assert {t["name"] for t in spec["tests"]} >= {"Insoluble matter", "Iron (as Fe)"}


def test_readings_tool_says_which_coa_is_missing(db_session):
    batch = db_session.scalar(select(Batch).where(Batch.batch_number == "FC-2611-12"))
    assert copilot.run_tool(db_session, batch, "get_coa_readings", {})["not_received"] == [
        "factory",
        "lab",
    ]


def test_an_invalid_brief_is_sent_back_and_corrected(db_session):
    bad = dict(BRIEF, next_steps=[])  # at least one step is required
    fake = FakeClaude([tool_use("submit_brief", bad)], [tool_use("submit_brief", BRIEF)])
    result = copilot.review_batch(db_session, held_batch(db_session), client=fake)
    assert result.brief.next_steps
    error = fake.requests[1][-1]["content"][0]
    assert error["is_error"] is True


def test_prose_instead_of_a_brief_gets_one_nudge(db_session):
    fake = FakeClaude(
        [text("It's held because of insolubles.")], [tool_use("submit_brief", BRIEF)]
    )
    copilot.review_batch(db_session, held_batch(db_session), client=fake)
    assert fake.requests[1][-1]["content"] == "Please call submit_brief now."

    stubborn = FakeClaude([text("Held.")], [text("Still held.")])
    with pytest.raises(copilot.CopilotError):
        copilot.review_batch(db_session, held_batch(db_session), client=stubborn)


def test_the_agent_has_no_tool_that_changes_anything():
    names = {t["name"] for t in copilot.TOOLS}
    assert names == {
        "get_verdict",
        "get_spec",
        "get_coa_readings",
        "get_order_line",
        "get_factory_history",
        "search_knowledge",
        "submit_brief",
    }


def test_endpoint_returns_the_brief_records_it_and_changes_nothing(
    client, login, db_session, monkeypatch
):
    fake = FakeClaude([tool_use("get_verdict")], [tool_use("submit_brief", BRIEF)])
    real = copilot.review_batch
    monkeypatch.setattr(copilot, "review_batch", lambda db, b: real(db, b, client=fake))
    batch = held_batch(db_session)
    verdicts_before = db_session.query(Verdict).filter_by(batch_id=batch.id).count()

    res = client.post(f"/api/batches/{batch.id}/copilot", headers=login(ANALYST))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["email"]["subject"].startswith("FC-2611-07")
    assert body["looked_at"] == ["get_verdict"]

    db_session.refresh(batch)
    assert batch.status.value == "on_hold"
    assert db_session.query(Verdict).filter_by(batch_id=batch.id).count() == verdicts_before
    entry = db_session.scalar(select(AuditLog).where(AuditLog.action == "copilot_brief"))
    assert entry.entity_id == batch.id and entry.data["email_to"] == "factory"


def test_without_an_api_key_the_endpoint_says_so(client, login, db_session):
    res = client.post(f"/api/batches/{held_batch(db_session).id}/copilot", headers=login(ANALYST))
    assert res.status_code == 503
    assert "no API key" in res.json()["detail"]


def test_sales_cannot_use_the_copilot(client, login, db_session):
    res = client.post(f"/api/batches/{held_batch(db_session).id}/copilot", headers=login(SALES))
    assert res.status_code == 403


def test_search_is_scoped_to_the_batchs_customer_and_product(db_session):
    found = {}
    out = copilot.run_tool(
        db_session, held_batch(db_session), "search_knowledge", {"query": "retest policy"}, found
    )
    assert (
        out["results"][0]["source"] == "Ridgeway Industrial Supply: quality agreement, 4.2 Retests"
    )
    assert all("Lumora" not in r["source"] for r in out["results"])
    assert set(found) == {r["ref"] for r in out["results"]}
    cases = copilot.run_tool(
        db_session,
        held_batch(db_session),
        "search_knowledge",
        {"query": "insoluble matter retest", "look_in": "past_cases"},
        {},
    )
    assert cases["results"] and all(r["source"].startswith("Past case") for r in cases["results"])


def _retest_ref(db_session):
    """Return the ref of the retest clause found by a real search."""
    out = copilot.run_tool(
        db_session, held_batch(db_session), "search_knowledge", {"query": "retest policy"}, {}
    )
    return out["results"][0]["ref"]


def test_cited_sources_come_back_with_titles_and_links(db_session):
    ref = _retest_ref(db_session)
    brief = dict(
        BRIEF,
        next_steps=[f"Ask the lab for one retest of the retained sample [{ref}]."],
        sources=[{"ref": ref, "supports": "One retest is allowed when sampling is suspected."}],
    )
    fake = FakeClaude(
        [tool_use("search_knowledge", {"query": "retest policy"})],
        [tool_use("submit_brief", brief)],
    )
    result = copilot.review_batch(db_session, held_batch(db_session), client=fake)
    (src,) = result.sources
    assert src.ref == ref and src.title.endswith("4.2 Retests")
    assert src.link.startswith("/knowledge/documents/")


def test_refs_cited_only_in_the_text_still_appear_as_sources(db_session):
    ref = _retest_ref(db_session)
    brief = dict(BRIEF, history_note=f"A similar batch was retested [{ref}].", sources=[])
    fake = FakeClaude(
        [tool_use("search_knowledge", {"query": "retest policy"})],
        [tool_use("submit_brief", brief)],
    )
    result = copilot.review_batch(db_session, held_batch(db_session), client=fake)
    assert [s.ref for s in result.sources] == [ref]


def test_a_citation_that_no_search_returned_is_sent_back(db_session):
    ref = _retest_ref(db_session)
    invented = dict(BRIEF, next_steps=["Retest it [K9999]."], sources=[])
    honest = dict(BRIEF, sources=[{"ref": ref, "supports": "Retest rule."}])
    fake = FakeClaude(
        [tool_use("search_knowledge", {"query": "retest policy"})],
        [tool_use("submit_brief", invented)],
        [tool_use("submit_brief", honest)],
    )
    result = copilot.review_batch(db_session, held_batch(db_session), client=fake)
    error = fake.requests[2][-1]["content"][0]
    assert error["is_error"] and "K9999" in error["content"]
    assert [s.ref for s in result.sources] == [ref]
