"""Knowledge base and case memory: splitting, search, scope, uploads and cases."""

from sqlalchemy import select

from app.models import Customer, KnowledgeDocument, KnowledgePassage, Product, QCCase
from app.models.enums import CaseOutcome
from app.services import knowledge as kb

ANALYST = "arjun@batchgate.dev"
MANAGER = "meera@batchgate.dev"
SALES = "sara@batchgate.dev"


def ids(db):
    """Return the demo customer and product ids."""
    rid = db.scalar(select(Customer.id).where(Customer.name == "Ridgeway Industrial Supply"))
    lum = db.scalar(select(Customer.id).where(Customer.name == "Lumora Personal Care"))
    fe = db.scalar(select(Product.id).where(Product.name == "Ferric Chloride"))
    po = db.scalar(select(Product.id).where(Product.name == "Piroctone Olamine"))
    return rid, lum, fe, po


def test_sections_keep_their_headings_and_clauses_cite_cleanly():
    text = """1 Scope
Covers ferric chloride.

4 Out-of-specification results
4.1 No out-of-specification material is released without a written concession.
4.2 Retests. One retest by the independent laboratory on the retained sample is permitted.
GENERAL TERMS
Payment in 30 days."""
    pieces = kb.split_sections(text)
    assert [s for s, _ in pieces] == [
        "1 Scope",
        "4.1 (Out-of-specification results)",
        "4.2 Retests",
        "GENERAL TERMS",
    ]
    assert pieces[2][1].startswith("One retest")


def test_long_sections_are_cut_without_losing_the_heading():
    body = " ".join(f"Sentence number {i} explains a rule." for i in range(120))
    pieces = kb.split_sections(f"5 Long rules\n{body}")
    assert len(pieces) > 1
    assert all(s == "5 Long rules" and len(t) <= kb.MAX_PASSAGE_CHARS for s, t in pieces)


def test_tokens_fold_plurals():
    assert kb.tokens("Retests of the batches, insolubles!") == ["retest", "insoluble"]


def test_demo_knowledge_is_seeded(db_session):
    assert db_session.query(KnowledgeDocument).count() == 4
    assert db_session.query(QCCase).count() == 4
    assert db_session.query(KnowledgePassage).count() > 20


def test_search_finds_the_clause_that_answers(db_session):
    rid, _, fe, _ = ids(db_session)
    hits = kb.search(db_session, "retest policy", customer_id=rid, product_id=fe)
    assert hits[0].passage.section == "4.2 Retests"
    assert hits[0].source == "Ridgeway Industrial Supply: quality agreement, 4.2 Retests"
    assert hits[0].link.startswith("/knowledge/documents/") and "#p" in hits[0].link
    assert hits[0].ref == f"K{hits[0].passage.id}"


def test_spec_aliases_widen_the_search(db_session):
    """A spec alias for a test widens the search."""
    rid, _, fe, _ = ids(db_session)
    groups = kb.synonym_groups(db_session, fe)
    weights = kb.expand("water insolubles high", groups)
    assert weights["matter"] == 0.5  # from the spec's other name for the test
    hits = kb.search(db_session, "water insolubles retest", customer_id=rid, product_id=fe)
    assert any(h.passage.case and h.passage.case.batch_number == "FC-2608-15" for h in hits)


def test_search_is_scoped_to_the_customer(db_session):
    rid, lum, fe, po = ids(db_session)
    ridgeway = kb.search(db_session, "quality agreement assay", customer_id=rid, product_id=fe)
    assert all(h.passage.customer_id in (None, rid) for h in ridgeway), (
        "Lumora's agreement must not answer a Ridgeway question"
    )
    lumora = kb.search(db_session, "assay basis dried", customer_id=lum, product_id=po, limit=10)
    assert any("Lumora" in h.source for h in lumora)


def test_archived_documents_drop_out_of_search(db_session):
    rid, _, fe, _ = ids(db_session)
    doc = db_session.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.title.like("Ridgeway%"))
    )
    doc.archived = True
    db_session.commit()
    hits = kb.search(db_session, "retest policy", customer_id=rid, product_id=fe, limit=10)
    assert all(h.passage.document_id != doc.id for h in hits)


def test_nothing_matches_nothing(db_session):
    assert kb.search(db_session, "the of and") == []
    assert kb.search(db_session, "zzzz qqqq") == []


def test_overview_and_document_detail(client, login):
    h = login(ANALYST)
    body = client.get("/api/knowledge", headers=h).json()
    assert len(body["documents"]) == 4 and len(body["cases"]) == 4
    assert body["can_edit"] is False
    doc = next(d for d in body["documents"] if d["title"].startswith("Ridgeway"))
    detail = client.get(f"/api/knowledge/documents/{doc['id']}", headers=h).json()
    assert "4.2 Retests" in [p["section"] for p in detail["passages_list"]]


def test_search_endpoint(client, login, db_session):
    rid, *_ = ids(db_session)
    hits = client.get(
        "/api/knowledge/search",
        params={"q": "notify customer when held", "customer_id": rid},
        headers=login(ANALYST),
    ).json()
    assert hits[0]["source"] == "Ridgeway Industrial Supply: quality agreement, 3 Notification"
    assert hits[0]["kind"] == "document"


def test_manager_uploads_a_text_document_and_it_is_searchable(client, login):
    h = login(MANAGER)
    text = b"1 Sampling\nDraw IBC samples from the middle after 15 minutes of recirculation.\n"
    res = client.post(
        "/api/knowledge/documents",
        headers=h,
        data={"title": "SOP QC-03: sampling IBCs", "kind": "sop"},
        files={"file": ("sop-qc-03.txt", text, "text/plain")},
    )
    assert res.status_code == 201, res.text
    assert res.json()["passages_list"][0]["section"] == "1 Sampling"
    hits = client.get(
        "/api/knowledge/search", params={"q": "recirculation IBC sample"}, headers=h
    ).json()
    assert hits[0]["source"].startswith("SOP QC-03")
    log = client.get("/api/audit?kind=knowledge", headers=h).json()["entries"]
    assert log[0]["action"] == "knowledge_document_added"


def test_a_pdf_without_text_is_refused_clearly(client, login):
    res = client.post(
        "/api/knowledge/documents",
        headers=login(MANAGER),
        data={"title": "Scanned agreement", "kind": "quality_agreement"},
        files={"file": ("scan.pdf", b"%PDF-1.4 no text", "application/pdf")},
    )
    assert res.status_code == 422


def test_who_can_do_what(client, login):
    upload = {
        "data": {"title": "x", "kind": "other"},
        "files": {"file": ("x.txt", b"1 Part\nSome text here.", "text/plain")},
    }
    assert (
        client.post("/api/knowledge/documents", headers=login(ANALYST), **upload).status_code
        == 403
    )
    assert client.get("/api/knowledge", headers=login(SALES)).status_code == 403


def _act(client, h, batch_id, action, **body):
    """Post a decision on a batch."""
    return client.post(
        f"/api/batches/{batch_id}/actions", headers=h, json={"action": action, **body}
    )


def _batch(client, h, number):
    """Return a batch from the list by number."""
    return next(
        b for b in client.get("/api/batches", headers=h).json() if b["batch_number"] == number
    )


def test_a_batch_released_after_review_becomes_a_case(client, login, db_session):
    a, m = login(ANALYST), login(MANAGER)
    b = _batch(client, a, "PO-2611-A")  # needs review: factory vs lab assay gap
    note = (
        "Factory reported as-is, lab dried basis; same basis differs by 0.1 %. Lumora QA agreed."
    )
    assert _act(client, a, b["id"], "propose_release", note=note).status_code == 200
    # Reloaded verdicts come newest first; the case must use the resolved problem.
    db_session.expire_all()
    assert _act(client, m, b["id"], "approve_release").status_code == 200

    case = db_session.scalar(select(QCCase).where(QCCase.batch_id == b["id"]))
    assert case.outcome == CaseOutcome.RELEASED and case.source == "batchgate"
    assert "Assay" in case.problem and "dried basis" in case.actions
    assert case.passages[0].customer_id == db_session.scalar(
        select(Customer.id).where(Customer.name == "Lumora Personal Care")
    )
    hits = kb.search(db_session, "as-is dried basis assay", kinds={"case"}, limit=10)
    assert any(h.passage.case_id == case.id for h in hits)


def test_a_rejected_batch_becomes_a_case(client, login, db_session):
    m = login(MANAGER)
    b = _batch(client, m, "FC-2611-07")
    assert (
        _act(
            client, m, b["id"], "reject", note="Retest confirmed 0.15 %. No concession."
        ).status_code
        == 200
    )
    case = db_session.scalar(select(QCCase).where(QCCase.batch_id == b["id"]))
    assert case.outcome == CaseOutcome.REJECTED
    assert "Insoluble matter" in case.problem


def test_a_clean_release_teaches_nothing_new(client, login, db_session):
    b = _batch(client, login(ANALYST), "MT-2610-31")  # the engine cleared it; awaiting approval
    assert _act(client, login(MANAGER), b["id"], "approve_release").status_code == 200
    assert db_session.scalar(select(QCCase).where(QCCase.batch_id == b["id"])) is None


def test_retrieval_eval_stays_at_its_measured_level():
    """Retrieval stays at its measured level: every answer in the top 5."""
    import importlib.util
    import json
    from pathlib import Path

    evals = Path(__file__).resolve().parents[2] / "evals"
    spec = importlib.util.spec_from_file_location("run_retrieval", evals / "run_retrieval.py")
    rr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rr)

    questions = json.loads((evals / "retrieval" / "questions.json").read_text())
    with rr.demo_db("batchgate_eval_test") as db:
        with_expansion = rr.metrics(rr.run(db, questions, expand=True))
        without = rr.metrics(rr.run(db, questions, expand=False))
    assert with_expansion["hit@5"] == 1.0
    assert with_expansion["hit@1"] >= 0.7
    assert with_expansion["mrr"] >= without["mrr"]  # spec aliases help, never hurt
