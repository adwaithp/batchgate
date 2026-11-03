"""PDF text check: each value Claude read must be on its test's row."""

from pathlib import Path

import pytest

from app.schemas.extraction import CoaExtraction, ExtractedRow
from app.services.extraction.verify import UNVERIFIED_CONFIDENCE, pdf_text, verify_reading

EVALS = Path(__file__).resolve().parents[2] / "evals" / "coas"

LAB_TEXT = """Sample Ferric Chloride Solution 40% (CAS 7705-08-0) Lot No. FC-2611-12
Parameter Test method Units Result Limits
Assay as FeCl3 NAL-WI-112 % w/w 40.6 ≥ 40.0
Fe NAL-WI-112 % w/w 13.95 ≥ 13.8
Fe(II) NAL-WI-121 % w/w 0.11 ≤ 0.25
Water insolubles NAL-WI-130 % w/w 0.16 ≤ 0.10
SG Density meter — 1.432 1.40 – 1.45
Appearance Visual — Complies Dark brown liquid
"""


def reading(*rows) -> CoaExtraction:
    """Build a reading with the given rows."""
    return CoaExtraction(
        is_coa=True,
        issuer_name=None,
        issuer_confidence=1.0,
        product_name=None,
        cas_number=None,
        batch_number=None,
        po_reference=None,
        mfg_date=None,
        test_date=None,
        expiry_date=None,
        mfg_date_as_printed=None,
        test_date_as_printed=None,
        expiry_date_as_printed=None,
        results=[
            ExtractedRow(
                name_as_written=name,
                raw_value=value,
                unit=None,
                method=None,
                limit_as_printed=limit,
                confidence=confidence,
                parameter_id=None,
            )
            for name, value, limit, confidence in rows
        ],
        warnings=[],
    )


def confidences(r: CoaExtraction) -> list[float]:
    """Return the row confidences."""
    return [row.confidence for row in r.results]


def test_correct_values_pass_untouched():
    r = reading(
        ("Assay as FeCl3", "40.6", "≥ 40.0", 1.0),
        ("Fe", "13.95", "≥ 13.8", 1.0),  # "Fe" must not match inside "Ferric"
        ("Fe(II)", "0.11", "≤ 0.25", 1.0),
        ("SG", "1.432", "1.40 – 1.45", 1.0),
        ("Appearance", "Complies", "Dark brown liquid", 1.0),
    )
    checked, flagged = verify_reading(r, LAB_TEXT)
    assert flagged == []
    assert checked is r


def test_a_value_copied_from_the_other_coa_is_flagged():
    # The lab's 0.16 misread as the factory's 0.04.
    checked, flagged = verify_reading(
        reading(("Water insolubles", "0.04", "≤ 0.10", 1.0)), LAB_TEXT
    )
    assert confidences(checked) == [UNVERIFIED_CONFIDENCE]
    assert "Water insolubles" in flagged[0]
    assert checked.warnings == flagged


def test_a_result_misread_as_its_own_limit_is_flagged():
    # "0.10" is on the row only as the limit.
    checked, _ = verify_reading(reading(("Water insolubles", "0.10", "≤ 0.10", 1.0)), LAB_TEXT)
    assert confidences(checked) == [UNVERIFIED_CONFIDENCE]


def test_a_result_equal_to_its_limit_still_passes():
    text = "Insoluble matter max 0.10 0.10 % Gravimetric"
    checked, flagged = verify_reading(reading(("Insoluble matter", "0.10", "max 0.10", 1.0)), text)
    assert flagged == []


def test_value_on_the_line_below_the_name():
    text = "Analysis\nFerric chloride\n99.600 %\nInsolubles\n0.100 %"
    r = reading(("Ferric chloride", "99.600", None, 1.0), ("Insolubles", "0.1", None, 1.0))
    assert verify_reading(r, text)[1] == []
    wrong = reading(("Insolubles", "0.010", None, 1.0))
    assert verify_reading(wrong, text)[1]


def test_a_wrong_text_result_is_flagged():
    checked, _ = verify_reading(reading(("Appearance", "Black powder", None, 1.0)), LAB_TEXT)
    assert confidences(checked) == [UNVERIFIED_CONFIDENCE]


def test_rows_already_unsure_are_left_alone():
    r = reading(("Water insolubles", "0.04", "≤ 0.10", 0.4))
    checked, flagged = verify_reading(r, LAB_TEXT)
    assert flagged == [] and confidences(checked) == [0.4]


def test_no_text_layer_means_nothing_to_check():
    r = reading(("Water insolubles", "0.04", "≤ 0.10", 1.0))
    assert verify_reading(r, None) == (r, [])


@pytest.mark.skipif(not EVALS.exists(), reason="eval documents not generated")
def test_pdf_text_reads_text_pdfs_and_skips_scans_and_images():
    assert "Insoluble matter" in pdf_text(EVALS / "01_factory_clean.pdf", "application/pdf")
    assert pdf_text(EVALS / "04_factory_scanned.pdf", "application/pdf") is None
    assert pdf_text(EVALS / "09_factory_phone_photo.jpg", "image/jpeg") is None


def test_broken_pdf_is_not_an_error(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 not really")
    assert pdf_text(bad, "application/pdf") is None
