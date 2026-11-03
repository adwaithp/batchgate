"""The eval harness: a perfect reader scores 100% and misreads are counted.

Confident misreads that would release a failing batch count as false releases.
"""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

from app.schemas.extraction import CoaExtraction, ExtractedRow
from app.services.extraction.reader import ExtractionError

EVALS = Path(__file__).resolve().parents[2] / "evals"
spec = importlib.util.spec_from_file_location("run_evals", EVALS / "run_evals.py")
run_evals = importlib.util.module_from_spec(spec)
sys.modules["run_evals"] = run_evals
spec.loader.exec_module(run_evals)

TODAY = date(2026, 11, 3)

pytestmark = pytest.mark.skipif(
    not (EVALS / "coas" / "manifest.json").exists(), reason="eval documents not generated"
)


def perfect_reading(case, *, misread: dict | None = None) -> CoaExtraction:
    """Return the reading a perfect reader would produce for a case."""
    t = case.truth
    misread = misread or {}
    return CoaExtraction(
        is_coa=True,
        issuer_name=t.get("issuer_name"),
        issuer_confidence=1.0,
        product_name=t.get("product_name"),
        cas_number=t.get("cas_number"),
        batch_number=t.get("batch_number"),
        po_reference=t.get("po_reference"),
        mfg_date=t.get("mfg_date"),
        test_date=t.get("test_date"),
        expiry_date=t.get("expiry_date"),
        mfg_date_as_printed=t.get("mfg_date_as_printed"),
        test_date_as_printed=t.get("test_date_as_printed"),
        expiry_date_as_printed=t.get("expiry_date_as_printed"),
        results=[
            ExtractedRow(
                name_as_written=r["name_as_written"],
                raw_value=misread.get(r["name_as_written"], (r["raw_value"],))[0],
                unit=r.get("unit"),
                method=None,
                limit_as_printed=None,
                confidence=misread.get(r["name_as_written"], (None, 1.0))[1],
                parameter_id=None,
            )
            for r in t["results"]
        ],
        warnings=[],
    )


def synthetic_cases():
    """Return the cases for the generated COAs."""
    return [c for c in run_evals.load_cases() if c.suite == "coas"]


def test_a_perfect_reader_scores_full_marks_and_every_expected_decision():
    cases = synthetic_cases()
    assert len(cases) >= 9
    for case in cases:
        s = run_evals.score_case(case, perfect_reading(case), "", TODAY)
        assert s.decision_ok, (case.file.name, s.got, s.expected, s.summary)
        assert s.fields_right == s.fields_total, (case.file.name, s.mistakes)
        assert s.values_right == s.values_total, (case.file.name, s.mistakes)


def test_a_confident_misread_that_hides_the_failure_is_reported_as_a_false_release():
    """A confident misread that matches the other COA hides a failure."""
    case = next(c for c in synthetic_cases() if c.file.name == "03_lab_insolubles_out_of_spec.pdf")
    row = next(r for r in case.truth["results"] if "nsoluble" in r["name_as_written"])
    reading = perfect_reading(case, misread={row["name_as_written"]: ("0.04", 1.0)})
    s = run_evals.score_case(case, reading, "", TODAY)
    assert s.wrong_and_confident == 1
    assert s.false_release
    assert "false release" in run_evals.report([s], "test-model")


def test_an_unsure_misread_is_flagged():
    case = next(c for c in synthetic_cases() if c.file.name == "01_factory_clean.pdf")
    row = case.truth["results"][0]
    s = run_evals.score_case(
        case, perfect_reading(case, misread={row["name_as_written"]: ("48.0", 0.5)}), "", TODAY
    )  # noqa: E501
    assert s.wrong_but_flagged == 1
    assert s.got == "review"  # low confidence goes to a person


def test_a_failed_read_is_manual_entry_not_a_release():
    case = synthetic_cases()[0]
    s = run_evals.score_case(case, None, "Claude is busy right now.", TODAY)
    assert s.got is None and not s.false_release


def test_runner_saves_readings_and_rescores_them_without_the_api(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evals, "READINGS", tmp_path / "readings")
    case = synthetic_cases()[0]
    calls = []

    def fake_reader(path, content_type, params):
        """Record the call and return a perfect reading."""
        calls.append(content_type)
        return perfect_reading(case)

    reading, error = run_evals.read_case(case, cached=False, reader=fake_reader)
    assert error == "" and calls == ["application/pdf"]
    again, _ = run_evals.read_case(case, cached=True)
    assert again == reading

    def failing(*_):
        """Fail as the reader would."""
        raise ExtractionError("Claude is busy right now.")

    _, error = run_evals.read_case(case, cached=False, reader=failing)
    assert run_evals.read_case(case, cached=True) == (None, error)


def test_the_pdf_text_check_stops_the_hidden_misread():
    case = next(c for c in synthetic_cases() if c.file.name == "03_lab_insolubles_out_of_spec.pdf")
    row = next(r for r in case.truth["results"] if "nsoluble" in r["name_as_written"])
    reading = perfect_reading(case, misread={row["name_as_written"]: ("0.04", 1.0)})
    reading.results[[r.name_as_written for r in reading.results].index(row["name_as_written"])] = (
        reading.results[0].model_copy(
            update={"name_as_written": row["name_as_written"], "raw_value": "0.04",
                    "limit_as_printed": "≤ 0.10", "confidence": 1.0}
        )
    )  # fmt: skip
    text = run_evals.pdf_text(case.file, "application/pdf")
    s = run_evals.score_case(case, reading, "", TODAY, text)
    assert s.caught_by_text_check == 1
    assert not s.false_release
    assert s.got == "review"


@pytest.mark.skipif(
    not (run_evals.READINGS / "coas").exists(), reason="no saved Claude readings yet"
)
def test_stress_test_on_claudes_saved_readings_finds_no_unseen_misreads_on_text_pdfs():
    table = run_evals.stress(synthetic_cases(), TODAY)
    text_row = next(line for line in table.splitlines() if line.startswith("| PDFs"))
    cells = [c.strip(" *") for c in text_row.split("|")[1:-1]]
    assert int(cells[1]) > 20
    assert cells[3] == "0"
    assert cells[4].replace("*", "").endswith("/ 0")
