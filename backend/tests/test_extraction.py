"""Reading COAs with Claude; a fake replaces the API call."""

from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app import worker
from app.core.config import get_settings
from app.models import COADocument
from app.schemas.extraction import CoaExtraction, ExtractedRow
from app.services import batches as svc
from app.services.extraction.reader import ExtractionError, read_coa
from tests.test_batches import ANALYST, PDF, detail, find, sse

MODEL = get_settings().extraction_model


@pytest.fixture(autouse=True)
def tmp_uploads(tmp_path, monkeypatch):
    """Store uploads in a temporary folder."""
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))


def row(name, value, unit=None, confidence=1.0, parameter_id=None):
    """Build an extracted result row."""
    return ExtractedRow(
        name_as_written=name,
        raw_value=value,
        unit=unit,
        method=None,
        limit_as_printed=None,
        confidence=confidence,
        parameter_id=parameter_id,
    )


def mt78(*rows: ExtractedRow, **header) -> CoaExtraction:
    """Return a clean factory COA reading for MT-2610-31."""
    defaults = {
        "is_coa": True,
        "issuer_name": "Dahej Specialty Organics",
        "issuer_confidence": 1.0,
        "product_name": "MEA Triazine 78%",
        "cas_number": "4719-04-4",
        "batch_number": "MT-2610-31",
        "po_reference": None,
        "mfg_date": "2026-10-18",
        "test_date": "2026-10-20",
        "expiry_date": "2028-10-17",
        "mfg_date_as_printed": "2026-10-18",
        "test_date_as_printed": "2026-10-20",
        "expiry_date_as_printed": "2028-10-17",
        "results": list(rows)
        or [
            row("Active content", "78.9", "%"),
            row("Free MEA", "1.1", "%"),
            row("pH", "10.4"),
            row("SG", "1.155"),
            row("Appearance", "Clear, pale yellow liquid"),
        ],
        "warnings": [],
    }
    return CoaExtraction(**{**defaults, **header})


def reads(extraction: CoaExtraction):
    """Return a reader that always returns `extraction`."""
    return lambda path, content_type, params: extraction


def fails(message: str):
    """Return a reader that always fails with `message`."""

    def read(path, content_type, params):
        """Raise ExtractionError."""
        raise ExtractionError(message)

    return read


@pytest.fixture
def new_factory_coa(client, login, db_session):
    """Upload a new factory COA for MT-2610-31, awaiting values."""
    h = login(ANALYST)
    b = find(client, h, "MT-2610-31")
    res = client.post(
        f"/api/batches/{b['id']}/coas",
        headers=h,
        data={"source": "factory"},
        files={"file": ("factory.pdf", PDF + b"new", "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return db_session.get(COADocument, sse(res)[0]["coa_id"])


def test_clean_reading_is_saved_and_checked(client, login, db_session, new_factory_coa):
    svc.extract_coa(db_session, new_factory_coa, read=reads(mt78()))

    d = detail(client, login(ANALYST), "MT-2610-31")
    coa = next(c for c in d["coas"] if c["id"] == new_factory_coa.id)
    assert coa["extraction_status"] == "done"
    assert coa["extraction_model"] == MODEL
    assert coa["batch_number"] == "MT-2610-31"
    assert d["status"] == "pending_approval"  # clean: a QC manager still approves


def test_low_confidence_reading_goes_to_review(client, login, db_session, new_factory_coa):
    extraction = mt78(
        row("Active content", "78.9", "%", confidence=0.6),
        row("Free MEA", "1.1", "%"),
        row("pH", "10.4"),
        row("SG", "1.155"),
        row("Appearance", "Clear, pale yellow liquid"),
    )
    svc.extract_coa(db_session, new_factory_coa, read=reads(extraction))

    d = detail(client, login(ANALYST), "MT-2610-31")
    assert d["status"] == "pending_review"
    assert "low confidence" in d["verdict"]["summary"].lower()
    coa = next(c for c in d["coas"] if c["id"] == new_factory_coa.id)
    assert [r["needs_check"] for r in coa["results"]] == [True, False, False, False, False]


def test_person_checking_the_values_clears_the_review(client, login, db_session, new_factory_coa):
    extraction = mt78(
        row("Active content", "78.9", "%", confidence=0.6),
        row("Free MEA", "1.1", "%", confidence=0.5),
        row("pH", "10.4"),
        row("SG", "1.155"),
        row("Appearance", "Clear, pale yellow liquid"),
    )
    svc.extract_coa(db_session, new_factory_coa, read=reads(extraction))
    h = login(ANALYST)

    def save(confidences):
        """Save the COA with the given row confidences."""
        coa = next(
            c for c in detail(client, h, "MT-2610-31")["coas"] if c["id"] == new_factory_coa.id
        )
        results = [
            {
                "name_as_written": r["name_as_written"],
                "raw_value": r["raw_value"],
                "unit": r["unit"],
                "confidence": conf,
            }
            for r, conf in zip(coa["results"], confidences, strict=True)
        ]
        res = client.put(
            f"/api/coas/{new_factory_coa.id}/data",
            headers=h,
            json={
                **{k: coa[k] for k in ("product_name", "cas_number", "batch_number")},
                "results": results,
            },
        )
        assert res.status_code == 200, res.text
        return res.json()

    # One doubtful row checked, the other untouched: still needs a look.
    body = save([1.0, 0.5, 1.0, 1.0, 1.0])
    assert body["status"] == "pending_review"
    body = save([1.0, 1.0, 1.0, 1.0, 1.0])
    assert body["status"] == "pending_approval"

    coa = next(c for c in body["coas"] if c["id"] == new_factory_coa.id)
    assert coa["extraction_model"] == MODEL  # still credited to the model's reading
    assert coa["checked_by"] == "Arjun Rao"


def test_failed_reading_falls_back_to_manual_entry(client, login, db_session, new_factory_coa):
    svc.extract_coa(db_session, new_factory_coa, read=fails("Claude couldn't open this file."))

    d = detail(client, login(ANALYST), "MT-2610-31")
    coa = next(c for c in d["coas"] if c["id"] == new_factory_coa.id)
    assert coa["extraction_status"] == "failed"
    assert coa["extraction_error"] == "Claude couldn't open this file."
    assert d["status"] == "pending_review"
    assert d["verdict"]["summary"] == "Needs review: Factory COA not received yet."


@pytest.mark.parametrize(
    ("extraction", "error"),
    [
        (mt78(is_coa=False), "This file doesn't look like a certificate of analysis."),
        (mt78(results=[]), "No test results were found on this COA."),
    ],
)
def test_unusable_readings_fail(db_session, new_factory_coa, extraction, error):
    svc.extract_coa(db_session, new_factory_coa, read=reads(extraction))
    assert new_factory_coa.extraction_status == "failed"
    assert new_factory_coa.extraction_error == error
    assert new_factory_coa.raw_extraction["is_coa"] == extraction.is_coa


def test_values_typed_in_meanwhile_are_not_overwritten(db_session, new_factory_coa):
    def person_types_while_claude_reads(path, content_type, params):
        """Save typed values while the reading is in progress."""
        svc.save_coa_data(
            db_session,
            new_factory_coa,
            svc.CoaHeader(batch_number="MT-2610-31"),
            [svc.CoaRow("Active content", "79.0", "%")],
            actor=None,
        )
        return mt78()

    svc.extract_coa(db_session, new_factory_coa, read=person_types_while_claude_reads)
    assert new_factory_coa.extraction_model == "manual"
    assert [r.raw_value for r in new_factory_coa.results] == ["79.0"]


def test_parameter_hints_only_fill_gaps_left_by_name_matching(db_session, new_factory_coa):
    spec = svc.spec_input(new_factory_coa.batch.line.spec)
    ids = {p.name: p.id for p in spec.parameters}
    active, free_mea = ids["Active content"], ids["Free MEA"]

    rows = svc._rows_with_hints(
        spec,
        [
            # The name matches; a wrong hint must not override it.
            row("Active content", "78.9", "%", parameter_id=free_mea),
            # An unmatched name: the hint fills the gap.
            row("Unreacted monoethanolamine", "1.1", "%", parameter_id=free_mea),
            # A hint for an already matched parameter is dropped.
            row("Triazine (assay)", "78.8", "%", parameter_id=active),
            row("Odour", "Amine-like", parameter_id=9999),
        ],
    )
    assert [r.parameter_id for r in rows] == [None, free_mea, None, None]


@pytest.fixture
def reader_on(monkeypatch):
    """Pretend an API key is configured."""
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")


def test_upload_streams_the_reading_to_the_end(client, login, db_session, reader_on, monkeypatch):
    async def read_now(coa_id):
        """Stand in for the worker and finish the reading immediately."""
        svc.extract_coa(db_session, db_session.get(COADocument, coa_id), read=reads(mt78()))
        db_session.commit()

    monkeypatch.setattr(worker, "enqueue_extraction", read_now)

    class NoLiveEvents:
        """A subscription with no events."""

        async def last(self):
            """Return no event."""
            return

        async def close(self):
            """Do nothing."""

    async def subscribe(coa_id):
        """Return an empty subscription."""
        return NoLiveEvents()

    monkeypatch.setattr("app.services.extraction.events.subscribe", subscribe)

    h = login(ANALYST)
    b = find(client, h, "MT-2610-31")
    res = client.post(
        f"/api/batches/{b['id']}/coas",
        headers=h,
        data={"source": "factory"},
        files={"file": ("factory.pdf", PDF + b"streamed", "application/pdf")},
    )
    assert res.status_code == 201
    assert res.headers["content-type"].startswith("text/event-stream")
    events = sse(res)
    assert [e["stage"] for e in events] == ["received", "done"]
    assert events[-1]["message"] == "Claude read 5 results. The check has run."

    again = client.get(f"/api/coas/{events[0]['coa_id']}/events", headers=h)
    assert [e["stage"] for e in sse(again)] == ["done"]


def test_stale_final_event_does_not_end_a_live_reading(client, login, reader_on, monkeypatch):
    async def queued(coa_id):
        """Accept the job."""

    monkeypatch.setattr(worker, "enqueue_extraction", queued)

    class LeftoverFromAnEarlierDatabase:
        """A subscription replaying events from an earlier database."""

        async def last(self):
            """Return a stale final event."""
            return {"stage": "done", "message": "Claude read 7 results. The check has run."}

        async def next(self, timeout):
            """Return another stale final event."""
            return {"stage": "failed", "message": "Claude couldn't open this file."}

        async def close(self):
            """Do nothing."""

    async def subscribe(coa_id):
        """Return the stale subscription."""
        return LeftoverFromAnEarlierDatabase()

    monkeypatch.setattr("app.services.extraction.events.subscribe", subscribe)
    h = login(ANALYST)
    b = find(client, h, "MT-2610-31")
    res = client.post(
        f"/api/batches/{b['id']}/coas",
        headers=h,
        data={"source": "factory"},
        files={"file": ("factory.pdf", PDF + b"stale", "application/pdf")},
    )
    assert [e["stage"] for e in sse(res)] == ["received", "queued", "failed"]


def test_queue_mode_without_redis_falls_back_to_manual_entry(
    client, login, reader_on, monkeypatch
):
    async def no_redis(coa_id):
        """Fail as Redis would."""
        raise RedisConnectionError("connection refused")

    monkeypatch.setattr(worker, "enqueue_extraction", no_redis)
    monkeypatch.setattr(get_settings(), "extraction_mode", "queue")
    h = login(ANALYST)
    b = find(client, h, "MT-2610-31")
    res = client.post(
        f"/api/batches/{b['id']}/coas",
        headers=h,
        data={"source": "factory"},
        files={"file": ("factory.pdf", PDF + b"no-redis", "application/pdf")},
    )
    last = sse(res)[-1]
    assert last == {
        "stage": "failed",
        "message": "The COA reader isn't running. Enter the values by hand.",
    }


@pytest.mark.parametrize("mode", ["auto", "inline"])
def test_without_redis_the_api_reads_the_coa_itself(
    client, login, db_session, reader_on, monkeypatch, mode
):
    """Without Redis, Claude reads the COA inside the upload request."""
    queued = []

    async def no_redis(coa_id):
        """Record the attempt and fail as Redis would."""
        queued.append(coa_id)
        raise RedisConnectionError("connection refused")

    def read_here(coa_id):
        """Read the COA in-process."""
        svc.extract_coa(db_session, db_session.get(COADocument, coa_id), read=reads(mt78()))
        db_session.commit()
        return "done"

    monkeypatch.setattr(worker, "enqueue_extraction", no_redis)
    monkeypatch.setattr(worker, "extract_now", read_here)
    monkeypatch.setattr(get_settings(), "extraction_mode", mode)
    h = login(ANALYST)
    b = find(client, h, "MT-2610-31")
    res = client.post(
        f"/api/batches/{b['id']}/coas",
        headers=h,
        data={"source": "factory"},
        files={"file": ("factory.pdf", PDF + mode.encode(), "application/pdf")},
    )
    assert res.status_code == 201
    events = sse(res)
    assert [e["stage"] for e in events] == ["received", "reading", "done"]
    assert events[-1]["message"] == "Claude read 5 results. The check has run."
    assert bool(queued) == (mode == "auto")  # inline mode does not try the queue


def test_batch_page_follows_a_reading_without_redis_until_it_is_done(
    client, login, db_session, reader_on, monkeypatch
):
    """Without Redis, the event stream polls the database until the reading ends."""
    from app.api.routes import batches as routes

    monkeypatch.setattr(get_settings(), "extraction_mode", "inline")
    monkeypatch.setattr(worker, "extract_now", lambda coa_id: "pending")
    h = login(ANALYST)
    b = find(client, h, "MT-2610-31")
    up = client.post(
        f"/api/batches/{b['id']}/coas",
        headers=h,
        data={"source": "factory"},
        files={"file": ("factory.pdf", PDF + b"poll", "application/pdf")},
    )
    coa_id = sse(up)[0]["coa_id"]
    assert db_session.get(COADocument, coa_id).extraction_status.value == "pending"

    real_reading, looks = routes._reading, []

    def reading_finishes_on_the_second_look(coa):
        """Finish the reading on the second poll."""
        looks.append(coa.id)
        if len(looks) == 2:
            svc.extract_coa(db_session, coa, read=reads(mt78()))
            db_session.commit()
        return real_reading(coa)

    monkeypatch.setattr(routes, "_reading", reading_finishes_on_the_second_look)
    monkeypatch.setattr(routes, "POLL_SECONDS", 0.01)
    events = sse(client.get(f"/api/coas/{coa_id}/events", headers=h))
    assert [e["stage"] for e in events] == ["reading", "done"]
    assert events[-1]["message"] == "Claude read 5 results. The check has run."


def test_progress_events_without_redis_are_skipped_quietly(monkeypatch):
    from app.services.extraction import events

    monkeypatch.setattr(get_settings(), "redis_url", "redis://127.0.0.1:1/0")
    events.publish(1, events.READING)  # no exception: reading carries on


class FakeClient:
    """Returns one canned structured-output response."""

    def __init__(self, stop_reason, parsed_output=None):
        """Prepare the canned response."""
        response = SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed_output)
        parse = lambda **kwargs: response  # noqa: E731
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=parse))


@pytest.mark.parametrize(
    ("stop_reason", "message"),
    [
        ("refusal", "Claude declined to read this document."),
        ("max_tokens", "The COA is too long to read in one go."),
        ("end_turn", "Claude's answer was not in the expected shape."),
    ],
)
def test_reader_turns_bad_stops_into_failures(tmp_path, stop_reason, message):
    path = tmp_path / "coa.pdf"
    path.write_bytes(PDF)
    with pytest.raises(ExtractionError, match=message):
        read_coa(path, "application/pdf", [], client=FakeClient(stop_reason))


def test_reader_returns_the_parsed_reading(tmp_path):
    path = tmp_path / "coa.png"
    path.write_bytes(b"\x89PNG")
    assert read_coa(path, "image/png", [], client=FakeClient("end_turn", mt78())) == mt78()


def test_reading_keeps_printed_dates_and_checks_the_issuer(
    client, login, db_session, new_factory_coa
):
    # Another company's letterhead and a month-and-year expiry.
    extraction = mt78(
        issuer_name="Meridian Reference Labs Pvt. Ltd.",
        expiry_date=None,
        expiry_date_as_printed="June 2031",
    )
    svc.extract_coa(db_session, new_factory_coa, read=reads(extraction))

    d = detail(client, login(ANALYST), "MT-2610-31")
    coa = next(c for c in d["coas"] if c["id"] == new_factory_coa.id)
    assert coa["issuer_name"] == "Meridian Reference Labs Pvt. Ltd."
    assert coa["expiry_date"] is None
    assert coa["expiry_date_as_printed"] == "June 2031"

    assert d["status"] == "pending_review"
    findings = {f["code"]: f["message"] for f in d["verdict"]["details"]["findings"]}
    assert findings["issuer"].startswith(
        "This COA is issued by Meridian Reference Labs Pvt. Ltd., but the batch is from "
        "Dahej Specialty Organics."
    )
    assert "2031-06-01" in findings["expiry_day_assumed"]


def test_doubtful_issuer_stays_in_review_until_a_person_vouches_for_it(
    client, login, db_session, new_factory_coa
):
    reading = mt78(issuer_name="Dahej Specialty Organics", issuer_confidence=0.5)
    svc.extract_coa(db_session, new_factory_coa, read=reads(reading))
    h = login(ANALYST)
    d = detail(client, h, "MT-2610-31")
    coa = next(c for c in d["coas"] if c["id"] == new_factory_coa.id)
    assert coa["issuer_needs_check"] and d["status"] == "pending_review"

    def save(issuer_confidence):
        """Save the COA with the given issuer confidence."""
        body = {
            k: coa[k]
            for k in ("issuer_name", "product_name", "cas_number", "batch_number", "expiry_date")
        }
        body["issuer_confidence"] = issuer_confidence
        body["results"] = [
            {
                "name_as_written": r["name_as_written"],
                "raw_value": r["raw_value"],
                "unit": r["unit"],
            }
            for r in coa["results"]
        ]
        res = client.put(f"/api/coas/{new_factory_coa.id}/data", headers=h, json=body)
        assert res.status_code == 200, res.text
        return res.json()["status"]

    assert save(0.5) == "pending_review"
    assert save(1.0) == "pending_approval"  # ticked "Matches the document"
