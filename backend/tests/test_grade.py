"""Grade check: the same chemical in a different form or strength is a different product."""

from dataclasses import replace
from datetime import date

import pytest

from app.models.enums import CoaSource, Decision, RuleType
from app.services.rules.engine import check_batch
from app.services.rules.grade import compare_grade, parse_grade
from app.services.rules.types import BatchInput, CoaInput, ParamSpec, ResultInput, SpecInput

TODAY = date(2026, 11, 3)

# A spec with only tests an anhydrous COA also reports, so every result passes.
SOLUTION_40 = SpecInput(
    product_name="Ferric Chloride",
    cas_number="7705-08-0",
    product_synonyms=["Iron(III) chloride", "FeCl3"],
    grade="40% solution",
    parameters=[
        ParamSpec(1, "Ferric chloride (FeCl3)", RuleType.MIN, low=40, unit="%"),
        ParamSpec(2, "Insoluble matter", RuleType.MAX, high=0.1, unit="%", aliases=["Insolubles"]),
    ],
)
ROWS = [("Ferric chloride", "99.6", "%"), ("Insolubles", "0.08", "%")]


def coa(source, product_name, issuer):
    """Build a COA input with every result passing."""
    return CoaInput(
        source=source,
        results=[ResultInput(n, v, u) for n, v, u in ROWS],
        product_name=product_name,
        cas_number="7705-08-0",
        batch_number="FC-2611-21",
        issuer_name=issuer,
        expected_issuer=issuer,
        mfg_date=date(2026, 9, 1),
        test_date=date(2026, 9, 3),
        expiry_date=date(2028, 9, 1),
    )


def run(spec, product_name):
    """Check a batch whose COAs print `product_name`."""
    batch = BatchInput(
        "FC-2611-21",
        [
            coa(CoaSource.FACTORY, product_name, "Kutch Coastal Chemicals"),
            coa(CoaSource.LAB, product_name, "Westbrook Testing Labs"),
        ],
    )
    return check_batch(spec, batch, today=TODAY)


def grade_checks(result):
    """Return the grade identity checks."""
    return [c for c in result.identity if c.code == "grade"]


@pytest.mark.parametrize(
    ("text", "forms", "strength"),
    [
        ("40% solution", {"solution"}, 40),
        ("Iron (III) chloride, anhydrous, 98%", {"anhydrous"}, 98),
        ("Ferric chloride hexahydrate", {"hydrate"}, None),
        ("Iron(III) chloride, 98+%, powder", {"solid"}, 98),
        ("Aqueous ferric chloride 42 %", {"solution"}, 42),
        ("78% active", set(), 78),
        ("Triazine H2S scavenger (40% active)", set(), 40),
        ("Cosmetic grade", set(), None),
        ("", set(), None),
        (None, set(), None),
    ],
)
def test_parse_grade(text, forms, strength):
    g = parse_grade(text)
    assert set(g.forms) == forms
    assert g.strength == strength


def test_anhydrous_is_never_read_as_a_hydrate():
    assert "hydrate" not in parse_grade("anhydrous").forms


@pytest.mark.parametrize(
    ("ordered", "printed", "status"),
    [
        ("40% solution", "Ferric Chloride Solution 40%", "pass"),
        ("40% solution", "Ferric chloride solution", "pass"),  # form agrees, strength not printed
        ("40% solution", "Ferric chloride 41%", "pass"),  # nominal grades allow a small gap
        ("40% solution", "Iron (III) chloride, anhydrous, 98%", "conflict"),
        ("40% solution", "Ferric chloride hexahydrate", "conflict"),
        ("Anhydrous 98%", "Ferric chloride hexahydrate", "conflict"),
        ("40% solution", "Iron(III) chloride powder", "conflict"),
        ("78% active", "Triazine H2S scavenger (40% active)", "strength"),
        ("40% active", "Triazine H2S scavenger (40% active)", "pass"),
        ("40% solution", "Ferric Chloride", "unknown"),
        ("Anhydrous 98%", "Iron (III) chloride, 98%", "pass"),  # strength agrees
        ("Cosmetic grade", "Piroctone Olamine 99%", "skip"),
        (None, "anything", "skip"),
    ],
)
def test_compare_grade(ordered, printed, status):
    assert compare_grade(ordered, printed).status == status


def test_anhydrous_coa_against_a_solution_order_is_held_even_though_every_result_passes():
    without_grade = run(replace(SOLUTION_40, grade=None), "Iron (III) chloride, anhydrous, 98%")
    assert without_grade.decision == Decision.RELEASE  # without the grade check this would release

    result = run(SOLUTION_40, "Iron (III) chloride, anhydrous, 98%")
    assert result.decision == Decision.HOLD
    assert all(p.status.value == "pass" for p in result.parameters)
    (check,) = {c.message: c for c in grade_checks(result)}.values()
    assert check.status.value == "fail"
    assert "anhydrous" in check.message and "40% solution" in check.message
    assert "different product" in result.summary


def test_the_right_grade_still_releases():
    result = run(SOLUTION_40, "Ferric Chloride Solution 40%")
    assert result.decision == Decision.RELEASE
    assert {c.status.value for c in grade_checks(result)} == {"pass"}


def test_wrong_strength_goes_to_review():
    spec = replace(SOLUTION_40, grade="40% solution")
    result = run(spec, "Ferric chloride solution 30%")
    assert result.decision == Decision.REVIEW
    assert any(f.code == "grade" and f.severity.value == "review" for f in result.findings)


def test_a_coa_that_does_not_state_its_grade_is_noted_but_does_not_block():
    result = run(SOLUTION_40, "Ferric Chloride")
    assert result.decision == Decision.RELEASE
    assert {c.status.value for c in grade_checks(result)} == {"missing"}


def test_specs_without_a_checkable_grade_add_no_check():
    result = run(replace(SOLUTION_40, grade="Technical grade"), "Ferric Chloride")
    assert grade_checks(result) == []
