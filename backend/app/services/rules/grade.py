"""Grade check: is the COA for the form and strength the customer ordered?

Word rules only; it flags clear conflicts and leaves unclear cases to other checks.
"""

import re
from dataclasses import dataclass

# Words naming a physical form.
_FORMS: dict[str, tuple[str, ...]] = {
    "solution": ("solution", "soln", "aqueous", "in water"),
    "anhydrous": ("anhydrous",),
    "solid": ("powder", "flake", "flakes", "crystal", "crystals", "crystalline", "granule",
              "granules", "granular", "lump", "lumps", "solid", "prill", "prills"),
}  # fmt: skip

# Forms that cannot both apply to one material.
_CONFLICTS = {
    frozenset({"solution", "anhydrous"}),
    frozenset({"solution", "solid"}),
    frozenset({"solution", "hydrate"}),
    frozenset({"anhydrous", "hydrate"}),
}

# matches "hydrate" and "hexahydrate", never "anhydrous"
_HYDRATE = re.compile(r"\b(?:mono|di|tri|tetra|penta|hexa|hepta|octa|nona|deca)?hydrate\b")
_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*\+?\s*%")


@dataclass(frozen=True)
class Grade:
    """Form words and strength parsed from a grade or product name."""

    forms: frozenset[str]
    strength: float | None  # first percentage in the text

    @property
    def empty(self) -> bool:
        """Return True when nothing comparable was found."""
        return not self.forms and self.strength is None


def parse_grade(text: str | None) -> Grade:
    """Parse form words and the first percentage from a text."""
    if not text:
        return Grade(frozenset(), None)
    low = text.lower()
    forms = {
        form
        for form, words in _FORMS.items()
        if form != "hydrate" and any(re.search(rf"\b{re.escape(w)}\b", low) for w in words)
    }
    if _HYDRATE.search(low):
        forms.add("hydrate")
    m = _PERCENT.search(low)
    strength = float(m.group(1).replace(",", ".")) if m else None
    return Grade(frozenset(forms), strength)


@dataclass(frozen=True)
class GradeComparison:
    """Result of comparing an ordered grade with a printed product name."""

    status: str  # pass, conflict, strength, unknown or skip
    message: str


def _strength_differs(ordered: float, printed: float) -> bool:
    """Return True when strengths differ beyond a nominal gap."""
    return abs(ordered - printed) > max(1.0, 0.05 * ordered)


def compare_grade(ordered_grade: str | None, printed_name: str | None) -> GradeComparison:
    """Compare the order line's grade with the COA's product name."""
    ordered = parse_grade(ordered_grade)
    if ordered.empty:
        # nothing checkable by words
        return GradeComparison("skip", "")
    printed = parse_grade(printed_name)
    if printed.empty:
        return GradeComparison(
            "unknown",
            f"The COA does not say which grade it is, so it was not compared with "
            f"“{ordered_grade}”.",
        )

    clashes = [
        (a, b) for a in printed.forms for b in ordered.forms if frozenset({a, b}) in _CONFLICTS
    ]
    if clashes:
        a, _ = clashes[0]
        return GradeComparison(
            "conflict",
            f"The COA is for {a} material (“{printed_name}”), but the order line is "
            f"“{ordered_grade}”: a different product, even if the results pass.",
        )

    if (
        ordered.strength is not None
        and printed.strength is not None
        and _strength_differs(ordered.strength, printed.strength)
    ):
        return GradeComparison(
            "strength",
            f"The COA says {printed.strength:g}%, but the order line is “{ordered_grade}” "
            f"({ordered.strength:g}%). Check it is the grade the customer ordered.",
        )

    # Only claim a match on what both sides state.
    shared = []
    if ordered.forms & printed.forms:
        shared.append(", ".join(sorted(ordered.forms & printed.forms)))
    if ordered.strength is not None and printed.strength is not None:
        shared.append(f"{printed.strength:g}%")
    if not shared:
        return GradeComparison(
            "unknown",
            f"The COA names “{printed_name}”, which does not state enough to compare with "
            f"“{ordered_grade}”.",
        )
    what = " and ".join(shared)
    return GradeComparison("pass", f"{what[0].upper()}{what[1:]}, as ordered (“{ordered_grade}”).")
