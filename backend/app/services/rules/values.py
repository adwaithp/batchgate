"""Turn a result as printed on a COA ("< 0.01 %", "Complies", "131.0 – 133.5 °C") into data."""

import re
from dataclasses import dataclass
from enum import StrEnum


class Qualifier(StrEnum):
    EQ = "="
    LT = "<"  # also "≤", "NMT": the true value is at or below the number
    GT = ">"  # also "≥", "NLT": the true value is at or above the number
    NOT_DETECTED = "nd"


@dataclass(frozen=True)
class Measurement:
    raw: str
    qualifier: Qualifier | None = None
    value: float | None = None
    # For reported ranges, e.g. a melting range "131.0 – 133.5".
    value_high: float | None = None
    unit: str | None = None
    text: str | None = None  # non-numeric results, e.g. "Complies"

    @property
    def is_numeric(self) -> bool:
        return self.value is not None


_NUM = r"[-+]?\d+(?:[.,]\d+)?"
_RANGE_RE = re.compile(rf"^\s*({_NUM})\s*(?:-|–|—|to)\s*({_NUM})\s*(.*)$", re.IGNORECASE)
_SINGLE_RE = re.compile(
    rf"^\s*(<=|>=|≤|≥|<|>|nmt|nlt|not more than|not less than|max\.?|min\.?)?\s*({_NUM})\s*(.*)$",
    re.IGNORECASE,
)
_ND_RE = re.compile(r"^\s*(nd|n\.d\.?|not detected|absent|bdl|below detection( limit)?)\s*$", re.I)

_LT_WORDS = {"<", "<=", "≤", "nmt", "not more than", "max", "max."}
_GT_WORDS = {">", ">=", "≥", "nlt", "not less than", "min", "min."}


def _to_float(s: str) -> float:
    # Some suppliers write decimal commas ("41,2"). Values here never use thousands separators.
    return float(s.replace(",", "."))


def parse_measurement(raw: str, unit: str | None = None) -> Measurement:
    """Parse a printed result. The `unit` column wins over a unit embedded in the value."""
    text = (raw or "").strip()
    if not text:
        return Measurement(raw=raw or "")

    if _ND_RE.match(text):
        return Measurement(raw=raw, qualifier=Qualifier.NOT_DETECTED, unit=unit)

    m = _RANGE_RE.match(text)
    if m and not text.lstrip().startswith(("-", "+")):
        low, high = _to_float(m.group(1)), _to_float(m.group(2))
        if low <= high:
            return Measurement(
                raw=raw,
                qualifier=Qualifier.EQ,
                value=low,
                value_high=high,
                unit=unit or (m.group(3).strip() or None),
            )

    m = _SINGLE_RE.match(text)
    if m:
        word = (m.group(1) or "").lower()
        qualifier = (
            Qualifier.LT
            if word in _LT_WORDS
            else Qualifier.GT
            if word in _GT_WORDS
            else Qualifier.EQ
        )
        embedded_unit = m.group(3).strip() or None
        return Measurement(
            raw=raw, qualifier=qualifier, value=_to_float(m.group(2)), unit=unit or embedded_unit
        )

    return Measurement(raw=raw, text=text, unit=unit)


# --- Text results -------------------------------------------------------------------------

_FAIL_PHRASES = (
    "does not comply",
    "doesn't comply",
    "not comply",
    "non-compliant",
    "noncompliant",
    "does not conform",
    "not conform",
    "nonconform",
    "non-conform",
    "fails",
    "failed",
    "fail",
    "out of spec",
    "oos",
)
_PASS_PHRASES = (
    "complies",
    "comply",
    "compliant",
    "conforms",
    "conform",
    "passes",
    "pass",
    "meets",
    "positive",
    "matches",
    "corresponds",
    "within limits",
    "within limit",
    "ok",
)


def text_verdict(text: str) -> bool | None:
    """True for an explicit pass statement, False for an explicit fail, None if unclear."""
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if any(re.search(rf"\b{re.escape(p)}\b", t) for p in _FAIL_PHRASES):
        return False
    if any(re.search(rf"\b{re.escape(p)}\b", t) for p in _PASS_PHRASES):
        return True
    return None


_STOP = {"a", "an", "the", "to", "and", "or", "of", "in", "with", "free", "from"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP}


_ALTERNATIVE = re.compile(r"^(.*?)\b([\w-]+)\s+(?:to|or)\s+([\w-]+)\b(.*)$", re.IGNORECASE)


def _variants(expected: str) -> list[str]:
    """ "White to off-white crystalline powder" -> both "White crystalline powder" and
    "off-white crystalline powder" are acceptable descriptions."""
    m = _ALTERNATIVE.match(expected)
    if not m:
        return [expected]
    prefix, a, b, suffix = m.groups()
    return [f"{prefix}{a}{suffix}", f"{prefix}{b}{suffix}"]


def text_matches(expected: str, observed: str) -> bool:
    """Conservative: every meaningful word of an acceptable description must appear.

    "Dark brown liquid" matches "Dark brown, clear liquid" but not "Brown liquid".
    Anything else is left for a human (or later, the model) to judge.
    """
    obs = _words(observed)
    for variant in _variants(expected):
        exp = _words(variant)
        if exp and exp <= obs:
            return True
    return False
