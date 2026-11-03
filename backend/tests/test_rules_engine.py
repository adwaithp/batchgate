"""Rules engine: units, values, decisions, identity checks and dates."""

from datetime import date

import pytest

from app.models.enums import CoaSource, Decision, RuleType
from app.services.rules.engine import check_batch
from app.services.rules.matching import match_results
from app.services.rules.types import (
    BatchInput,
    CoaInput,
    EngineConfig,
    ParamSpec,
    ParamStatus,
    ResultInput,
    SpecInput,
)
from app.services.rules.units import UnitMismatchError, convert, normalize_unit
from app.services.rules.values import (
    Qualifier,
    month_start,
    parse_measurement,
    text_matches,
    text_verdict,
)

TODAY = date(2026, 11, 2)

FECL3 = SpecInput(
    product_name="Ferric Chloride",
    cas_number="7705-08-0",
    product_synonyms=["Iron(III) chloride", "FeCl3"],
    parameters=[
        ParamSpec(
            1, "Iron (as Fe)", RuleType.MIN, low=13.8, unit="%", aliases=["Fe", "Fe content"]
        ),
        ParamSpec(2, "Free acid (as HCl)", RuleType.MAX, high=0.5, unit="%", tolerance_abs=0.05),
        ParamSpec(3, "Insoluble matter", RuleType.MAX, high=0.1, unit="%", tolerance_abs=0.02),
        ParamSpec(
            4, "Specific gravity @ 25 °C", RuleType.RANGE, low=1.40, high=1.45, aliases=["SG"]
        ),
        ParamSpec(5, "Heavy metals (as Pb)", RuleType.MAX, high=10, unit="ppm", tolerance_abs=2),
        ParamSpec(
            6, "Appearance", RuleType.TEXT_MATCH, expected_text="Dark brown liquid", critical=False
        ),
    ],
)

GOOD_ROWS = [
    ("Fe content", "13.9", "%"),
    ("Free acid (as HCl)", "0.31", "%"),
    ("Insoluble matter", "0.05", "%"),
    ("SG", "1.42", None),
    ("Heavy metals", "< 5", "ppm"),
    ("Appearance", "Dark brown, clear liquid", None),
]


def coa(source, rows=GOOD_ROWS, **header):
    """Build a COA input with clean defaults."""
    defaults = {
        "product_name": "Ferric Chloride Solution",
        "cas_number": "7705-08-0",
        "batch_number": "FC-2611-07",
        "mfg_date": date(2026, 10, 25),
        "test_date": date(2026, 10, 27),
        "expiry_date": date(2027, 10, 24),
    }
    defaults.update(header)
    return CoaInput(
        source=source,
        results=[ResultInput(n, v, u) for n, v, u in rows],
        **defaults,
    )


def run(*coas, config=None):
    """Check a ferric chloride batch made of `coas`."""
    return check_batch(FECL3, BatchInput("FC-2611-07", list(coas)), today=TODAY, config=config)


def replace_row(name, value, unit="%", rows=GOOD_ROWS):
    """Return result rows with one test's value replaced."""
    return [(n, value, unit) if n == name else (n, v, u) for n, v, u in rows]


def test_unit_aliases():
    assert normalize_unit("mg/kg") == "ppm"
    assert normalize_unit("% w/w") == "%"
    assert normalize_unit("-") is None
    assert normalize_unit("w/v %") == "% w/v"


def test_unit_conversion():
    assert convert(0.0005, "%", "ppm") == pytest.approx(5)
    assert convert(5, "mg/kg", "%") == pytest.approx(0.0005)
    with pytest.raises(UnitMismatchError):
        convert(40, "% w/v", "%")


@pytest.mark.parametrize(
    ("raw", "qualifier", "value", "high"),
    [
        ("41.2 %", Qualifier.EQ, 41.2, None),
        ("41,2", Qualifier.EQ, 41.2, None),
        ("< 0.01", Qualifier.LT, 0.01, None),
        ("NMT 5", Qualifier.LT, 5, None),
        ("≥ 98.5", Qualifier.GT, 98.5, None),
        ("131.0 – 133.5 °C", Qualifier.EQ, 131.0, 133.5),
        ("ND", Qualifier.NOT_DETECTED, None, None),
        ("-0.5", Qualifier.EQ, -0.5, None),
    ],
)
def test_parse_measurement(raw, qualifier, value, high):
    m = parse_measurement(raw)
    assert m.qualifier == qualifier
    assert m.value == value
    assert m.value_high == high


def test_text_helpers():
    assert text_verdict("Complies") is True
    assert text_verdict("Does not comply") is False
    assert text_verdict("Brownish") is None
    assert text_matches("Dark brown liquid", "dark brown clear liquid")
    assert not text_matches("Dark brown liquid", "brown liquid")
    spec = "White to off-white crystalline powder"
    assert text_matches(spec, "White crystalline powder")
    assert text_matches(spec, "Off-white crystalline powder")
    assert not text_matches(spec, "Yellow crystalline powder")


def test_matching_is_strict_when_ambiguous():
    params = [
        ParamSpec(1, "Iron (as Fe)", RuleType.MIN, low=13.8, aliases=["Total iron"]),
        ParamSpec(2, "Ferrous iron (Fe2+)", RuleType.MAX, high=0.25),
    ]
    matched, unmatched = match_results(
        params,
        [
            ResultInput("Total Iron", "13.9"),
            ResultInput("Ferrous iron", "0.1"),
            ResultInput("Chloride", "62"),
        ],
    )
    assert matched[1].raw_value == "13.9"
    assert matched[2].raw_value == "0.1"
    assert [r.name_as_written for r in unmatched] == ["Chloride"]


def test_clean_batch_is_released():
    result = run(coa(CoaSource.FACTORY), coa(CoaSource.LAB))
    assert result.decision == Decision.RELEASE
    assert all(p.status == ParamStatus.PASS for p in result.parameters)
    assert "Ready for release approval" in result.summary


def test_out_of_spec_critical_parameter_holds():
    lab = coa(CoaSource.LAB, replace_row("Insoluble matter", "0.14"))
    result = run(coa(CoaSource.FACTORY), lab)
    assert result.decision == Decision.HOLD
    assert result.summary.startswith("Hold: Insoluble matter")
    check = next(p for p in result.parameters if p.name == "Insoluble matter")
    assert check.status == ParamStatus.FAIL


def test_value_exactly_at_limit_passes():
    rows = replace_row("Free acid (as HCl)", "0.50")
    assert run(coa(CoaSource.FACTORY, rows), coa(CoaSource.LAB, rows)).decision == Decision.RELEASE


def test_unit_conversion_ppm_vs_percent():
    # 0.0004 % = 4 ppm, under the 10 ppm limit
    rows = replace_row("Heavy metals", "0.0004", "%")
    result = run(coa(CoaSource.FACTORY, rows), coa(CoaSource.LAB))
    hm = next(p for p in result.parameters if p.name.startswith("Heavy"))
    assert hm.status == ParamStatus.PASS
    assert hm.readings[0].value == pytest.approx(4)


def test_incomparable_unit_needs_review():
    rows = replace_row("Fe content", "40.1", "% w/v")
    result = run(coa(CoaSource.FACTORY, rows), coa(CoaSource.LAB))
    assert result.decision == Decision.REVIEW
    iron = result.parameters[0]
    assert iron.status == ParamStatus.UNCLEAR
    assert "cannot be compared" in iron.note


def test_less_than_above_the_limit_is_unclear():
    rows = replace_row("Heavy metals", "< 20", "ppm")
    result = run(coa(CoaSource.FACTORY, rows), coa(CoaSource.LAB, rows))
    assert result.decision == Decision.REVIEW


def test_missing_critical_parameter_needs_review():
    rows = [r for r in GOOD_ROWS if r[0] != "Insoluble matter"]
    result = run(coa(CoaSource.FACTORY, rows), coa(CoaSource.LAB, rows))
    assert result.decision == Decision.REVIEW
    assert any(f.code == "missing" for f in result.findings)


def test_missing_non_critical_parameter_does_not_block():
    rows = [r for r in GOOD_ROWS if r[0] != "Appearance"]
    result = run(coa(CoaSource.FACTORY, rows), coa(CoaSource.LAB, rows))
    assert result.decision == Decision.RELEASE


def test_parameter_reported_by_only_one_source_is_enough():
    lab_rows = [r for r in GOOD_ROWS if r[0] in ("Fe content", "Insoluble matter")]
    assert run(coa(CoaSource.FACTORY), coa(CoaSource.LAB, lab_rows)).decision == Decision.RELEASE


def test_factory_and_lab_disagreement_needs_review():
    # Both pass the minimum but differ by more than 2 %.
    lab = coa(CoaSource.LAB, replace_row("Fe content", "13.85"))
    factory = coa(CoaSource.FACTORY, replace_row("Fe content", "14.4"))
    result = run(factory, lab)
    assert result.decision == Decision.REVIEW
    iron = result.parameters[0]
    assert iron.status == ParamStatus.PASS
    assert "Factory reports 14.4 %" in iron.discrepancy


def test_small_absolute_difference_on_small_values_is_tolerated():
    # About 9 % relative, but within the 0.05 absolute tolerance.
    lab = coa(CoaSource.LAB, replace_row("Free acid (as HCl)", "0.34"))
    assert run(coa(CoaSource.FACTORY), lab).decision == Decision.RELEASE


def test_missing_lab_coa_needs_review():
    result = run(coa(CoaSource.FACTORY))
    assert result.decision == Decision.REVIEW
    assert result.summary == "Needs review: Independent lab COA not received yet."


def test_lab_coa_can_be_optional():
    result = run(coa(CoaSource.FACTORY), config=EngineConfig(require_lab_coa=False))
    assert result.decision == Decision.RELEASE


def test_fail_on_factory_coa_holds_even_before_lab():
    factory = coa(CoaSource.FACTORY, replace_row("Fe content", "12.9"))
    assert run(factory).decision == Decision.HOLD


def test_wrong_cas_holds():
    result = run(coa(CoaSource.FACTORY), coa(CoaSource.LAB, cas_number="7758-94-3"))
    assert result.decision == Decision.HOLD
    assert any(f.code == "cas" for f in result.findings)


def test_batch_number_mismatch_needs_review():
    result = run(coa(CoaSource.FACTORY), coa(CoaSource.LAB, batch_number="FC-2611-08"))
    assert result.decision == Decision.REVIEW


def test_batch_number_formatting_differences_are_ignored():
    result = run(coa(CoaSource.FACTORY), coa(CoaSource.LAB, batch_number="fc 261107"))
    assert result.decision == Decision.RELEASE


def test_expired_batch_holds():
    expired = coa(CoaSource.LAB, expiry_date=date(2026, 10, 1))
    assert run(coa(CoaSource.FACTORY), expired).decision == Decision.HOLD


def test_low_confidence_read_needs_review():
    lab = coa(CoaSource.LAB)
    lab.results[0].confidence = 0.55
    result = run(coa(CoaSource.FACTORY), lab)
    assert result.decision == Decision.REVIEW
    assert "low confidence" in result.parameters[0].note


def test_unfamiliar_appearance_wording_is_only_informational():
    rows = replace_row("Appearance", "Reddish-brown liquid", None)
    result = run(coa(CoaSource.FACTORY, rows), coa(CoaSource.LAB))
    appearance = result.parameters[-1]
    assert appearance.status == ParamStatus.UNCLEAR
    assert result.decision == Decision.RELEASE  # non-critical


def test_result_is_json_serialisable():
    import json

    json.dumps(run(coa(CoaSource.FACTORY), coa(CoaSource.LAB)).to_dict(), default=str)


def test_greater_than_below_a_minimum_is_unclear():
    rows = replace_row("Fe content", "> 12")
    result = run(coa(CoaSource.FACTORY, rows), coa(CoaSource.LAB, rows))
    assert result.parameters[0].status == ParamStatus.UNCLEAR


def test_greater_than_at_or_above_minimum_passes():
    rows = replace_row("Fe content", "> 14")
    result = run(coa(CoaSource.FACTORY, rows), coa(CoaSource.LAB, rows))
    assert result.parameters[0].status == ParamStatus.PASS


def test_product_name_ignores_spacing_and_punctuation():
    # The COA spacing differs from the synonym's.
    result = run(
        coa(
            CoaSource.FACTORY, product_name="Iron (III) chloride, anhydrous, 98%", cas_number=None
        ),
        coa(CoaSource.LAB),
    )
    product = next(c for c in result.identity if c.code == "product" and c.source == "factory")
    assert product.status == "pass"


def test_unrelated_product_name_still_fails():
    result = run(coa(CoaSource.FACTORY, product_name="Aluminium chlorohydrate", cas_number=None))
    product = next(c for c in result.identity if c.code == "product")
    assert product.status == "fail"


def test_missing_expiry_is_reported_not_silently_skipped():
    result = run(coa(CoaSource.FACTORY, expiry_date=None), coa(CoaSource.LAB))
    expiry = next(c for c in result.identity if c.code == "expiry" and c.source == "factory")
    assert expiry.status == "missing"
    assert result.decision == Decision.RELEASE  # informational


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("June 2031", date(2031, 6, 1)),
        ("JUN-2031", date(2031, 6, 1)),
        ("Sept. 2026", date(2026, 9, 1)),
        ("06/2031", date(2031, 6, 1)),
        ("2031-06", date(2031, 6, 1)),
        ("03/04/2026", None),  # day/month order unknown: never guessed
        ("28.10.2027", None),
        ("13/2031", None),
        ("Junk 2031", None),
    ],
)
def test_month_start(printed, expected):
    assert month_start(printed) == expected


def test_month_and_year_expiry_is_checked_from_its_first_day():
    # A month-and-year expiry with no full date.
    factory = coa(CoaSource.FACTORY, expiry_date=None, expiry_date_as_printed="June 2031")
    result = run(factory, coa(CoaSource.LAB))
    expiry = next(c for c in result.identity if c.code == "expiry" and c.source == "factory")
    assert expiry.status == "pass"
    assert expiry.message == "Valid until 2031-06-01."
    assumed = next(f for f in result.findings if f.code == "expiry_day_assumed")
    assert assumed.severity == "info"
    assert "“June 2031”" in assumed.message and "2031-06-01" in assumed.message
    assert result.decision == Decision.RELEASE


def test_month_and_year_expiry_in_the_current_month_counts_as_expired():
    # October 2026 is read as 1 October, already past.
    lab = coa(CoaSource.LAB, expiry_date=None, expiry_date_as_printed="October 2026")
    assert run(coa(CoaSource.FACTORY), lab).decision == Decision.HOLD


def test_ambiguous_expiry_is_not_guessed_and_needs_review():
    # 3 April or 4 March: a person reads it.
    factory = coa(CoaSource.FACTORY, expiry_date=None, expiry_date_as_printed="03/04/2026")
    result = run(factory, coa(CoaSource.LAB))
    expiry = next(c for c in result.identity if c.code == "expiry" and c.source == "factory")
    assert expiry.status == "warn"
    assert "“03/04/2026” could mean more than one date" in expiry.message
    assert not any(f.code == "expiry_day_assumed" for f in result.findings)
    assert result.decision == Decision.REVIEW


def test_full_expiry_date_wins_over_the_printed_text():
    factory = coa(CoaSource.FACTORY, expiry_date_as_printed="June 2031")
    result = run(factory, coa(CoaSource.LAB))
    assert not any(f.code == "expiry_day_assumed" for f in result.findings)


def test_factory_coa_from_another_company_needs_review():
    # A catalogue COA from a laboratory uploaded for a factory batch.
    factory = coa(
        CoaSource.FACTORY,
        issuer_name="Meridian Reference Labs Pvt. Ltd.",
        expected_issuer="Kutch Coastal Chemicals",
    )
    result = run(factory, coa(CoaSource.LAB))
    assert result.decision == Decision.REVIEW
    issuer = next(f for f in result.findings if f.code == "issuer")
    assert issuer.message == (
        "This COA is issued by Meridian Reference Labs Pvt. Ltd., but the batch is from "
        "Kutch Coastal Chemicals. (factory COA)"
    )


def test_lab_coa_from_another_lab_needs_review():
    lab = coa(
        CoaSource.LAB,
        issuer_name="Crestline Fine Chemicals",
        expected_issuer="Northbridge Analytical Labs",
    )
    result = run(coa(CoaSource.FACTORY), lab)
    assert result.decision == Decision.REVIEW
    issuer = next(f for f in result.findings if f.code == "issuer")
    assert "but the lab chosen for it is Northbridge Analytical Labs" in issuer.message


@pytest.mark.parametrize(
    "printed",
    [
        "Kutch Coastal Chemicals Pvt. Ltd.",
        "KUTCH-COASTAL CHEMICALS",
        "Kutch Coastal Chemicals LLC",
    ],
)
def test_issuer_name_ignores_spacing_punctuation_and_legal_suffixes(printed):
    factory = coa(
        CoaSource.FACTORY, issuer_name=printed, expected_issuer="Kutch Coastal Chemicals"
    )
    result = run(factory, coa(CoaSource.LAB))
    issuer = next(c for c in result.identity if c.code == "issuer")
    assert issuer.status == "pass"
    assert result.decision == Decision.RELEASE


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("Kutch Coastal", "Kutch Coastal Chemicals"),  # part of the name only
        ("Chemicals", "Kutch Coastal Chemicals"),  # too generic
        ("Northbridge Analytical Labs (Hyderabad)", "Northbridge Analytical Labs"),
    ],
)
def test_partial_issuer_match_needs_review(printed, expected):
    factory = coa(CoaSource.FACTORY, issuer_name=printed, expected_issuer=expected)
    result = run(factory, coa(CoaSource.LAB))
    issuer = next(c for c in result.identity if c.code == "issuer")
    assert issuer.status == "warn"
    assert "only partly matches" in issuer.message
    assert result.decision == Decision.REVIEW


def test_issuer_read_with_low_confidence_needs_review():
    factory = coa(
        CoaSource.FACTORY,
        issuer_name="Kutch Coastal Chemicals",
        issuer_confidence=0.55,
        expected_issuer="Kutch Coastal Chemicals",
    )
    result = run(factory, coa(CoaSource.LAB))
    issuer = next(c for c in result.identity if c.code == "issuer")
    assert issuer.status == "warn"
    assert "low confidence (0.55)" in issuer.message
    assert result.decision == Decision.REVIEW


def test_missing_issuer_is_shown_not_silently_skipped():
    factory = coa(CoaSource.FACTORY, expected_issuer="Kutch Coastal Chemicals")
    result = run(factory, coa(CoaSource.LAB))
    issuer = next(c for c in result.identity if c.code == "issuer")
    assert issuer.status == "missing"
    assert issuer.message == "No issuer on the COA, so who issued it was not checked."
    assert result.decision == Decision.RELEASE  # shown only


def test_lab_coa_without_a_chosen_lab_is_shown_as_unchecked():
    result = run(
        coa(CoaSource.FACTORY), coa(CoaSource.LAB, issuer_name="Crestline Fine Chemicals")
    )
    issuer = next(c for c in result.identity if c.code == "issuer" and c.source == "lab")
    assert issuer.status == "missing"
    assert "no lab was chosen" in issuer.message
