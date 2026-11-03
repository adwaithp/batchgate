"""Parse printed COA results such as < 0.01 %, Complies or 131.0 - 133.5 °C."""

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Qualifier(StrEnum):
    """A qualifier printed before a number."""

    EQ = "="
    LT = "<"  # also "≤" and "NMT"
    GT = ">"  # also "≥" and "NLT"
    NOT_DETECTED = "nd"


@dataclass(frozen=True)
class Measurement:
    """A parsed result."""

    raw: str
    qualifier: Qualifier | None = None
    value: float | None = None
    # Ranges, e.g. a melting range.
    value_high: float | None = None
    unit: str | None = None
    text: str | None = None  # non-numeric results

    @property
    def is_numeric(self) -> bool:
        """Return True when the result has a number."""
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
    """Parse a number, accepting a decimal comma."""
    return float(s.replace(",", "."))


def parse_measurement(raw: str, unit: str | None = None) -> Measurement:
    """Parse a printed result; the unit column wins over an inline unit."""
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
    """Return True for a pass statement, False for a fail, None if unclear."""
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if any(re.search(rf"\b{re.escape(p)}\b", t) for p in _FAIL_PHRASES):
        return False
    if any(re.search(rf"\b{re.escape(p)}\b", t) for p in _PASS_PHRASES):
        return True
    return None


_STOP = {"a", "an", "the", "to", "and", "or", "of", "in", "with", "free", "from"}


def _words(text: str) -> set[str]:
    """Return the meaningful words of a description."""
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP}


_ALTERNATIVE = re.compile(r"^(.*?)\b([\w-]+)\s+(?:to|or)\s+([\w-]+)\b(.*)$", re.IGNORECASE)


def _variants(expected: str) -> list[str]:
    """Expand a 'X to Y' description into each acceptable variant."""
    m = _ALTERNATIVE.match(expected)
    if not m:
        return [expected]
    prefix, a, b, suffix = m.groups()
    return [f"{prefix}{a}{suffix}", f"{prefix}{b}{suffix}"]


def text_matches(expected: str, observed: str) -> bool:
    """Return True when every word of an acceptable description appears."""
    obs = _words(observed)
    for variant in _variants(expected):
        exp = _words(variant)
        if exp and exp <= obs:
            return True
    return False


_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]  # fmt: skip


def _month_number(word: str) -> int | None:
    """Return a month number from its name, or None."""
    if len(word) < 3:
        return None
    return next((i for i, m in enumerate(_MONTHS, start=1) if m.startswith(word)), None)


def month_start(text: str) -> date | None:
    """Return the first day of a month-and-year date, or None."""
    s = text.strip().lower()
    sep = r"\s*[\s,./'-]\s*"
    if m := re.fullmatch(rf"([a-z]+)\.?{sep}(\d{{4}})", s):
        month, year = _month_number(m[1]), int(m[2])
    elif m := re.fullmatch(rf"(\d{{1,2}}){sep}(\d{{4}})", s):
        month, year = int(m[1]), int(m[2])
    elif m := re.fullmatch(rf"(\d{{4}}){sep}(\d{{1,2}})", s):
        month, year = int(m[2]), int(m[1])
    else:
        return None
    if month is None or not 1 <= month <= 12:
        return None
    return date(year, month, 1)
