"""Check Claude's reading against the PDF's text layer.

A value that cannot be found on its test's row gets its confidence capped below the review
threshold, so a person checks it. Scans and photos have no text to check.
"""

import re
from collections import Counter
from pathlib import Path

from app.schemas.extraction import CoaExtraction

UNVERIFIED_CONFIDENCE = 0.5  # below the engine's review threshold (0.8)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def pdf_text(path: Path, content_type: str) -> str | None:
    """Return the PDF's text layer, or None for images and scans."""
    if content_type != "application/pdf":
        return None
    try:
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    except Exception:  # an unreadable text layer leaves nothing to check
        return None
    return text if len(re.findall(r"[A-Za-z0-9]", text)) >= 40 else None


def _squash(text: str) -> str:
    """Return lowercase letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _numbers(text: str | None) -> list[float]:
    """Return the numbers in a text."""
    return [float(n.replace(",", ".")) for n in _NUMBER.findall(text or "")]


def _row_windows(lines: list[str], name: str) -> list[str]:
    """Return each line naming the test, joined with the following line."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    if not words:
        return []
    pattern = re.compile(
        r"(?<![a-z0-9])" + r"[^a-z0-9]*".join(map(re.escape, words)) + r"(?![a-z0-9])"
    )
    return [
        "\n".join(lines[i : i + 2]) for i, line in enumerate(lines) if pattern.search(line.lower())
    ]


def _found(value: str, limit: str | None, window: str) -> bool:
    """Return True when the value appears in the window, ignoring the limit."""
    wanted = _numbers(value)
    if not wanted:  # text result
        return _squash(value) in _squash(window)
    available = Counter(_numbers(window))
    available.subtract(Counter(_numbers(limit)))  # the printed limit is not the result
    for n in wanted:
        if available[n] <= 0:
            return False
        available[n] -= 1
    return True


def verify_reading(reading: CoaExtraction, text: str | None) -> tuple[CoaExtraction, list[str]]:
    """Return the reading with unverifiable rows marked unsure, and warnings."""
    if not text:
        return reading, []
    lines = text.splitlines()
    flagged: list[str] = []
    rows = []
    for row in reading.results:
        windows = _row_windows(lines, row.name_as_written)
        if windows:
            ok = any(_found(row.raw_value, row.limit_as_printed, w) for w in windows)
        else:
            # Name not found as written: only check the value is present.
            ok = _found(row.raw_value, None, text)
        if ok or row.confidence <= UNVERIFIED_CONFIDENCE:
            rows.append(row)
            continue
        flagged.append(
            f"{row.name_as_written}: “{row.raw_value}” isn't on that row in the PDF's text, "
            "so it needs checking."
        )
        rows.append(row.model_copy(update={"confidence": UNVERIFIED_CONFIDENCE}))
    if not flagged:
        return reading, []
    return reading.model_copy(
        update={"results": rows, "warnings": [*reading.warnings, *flagged]}
    ), flagged
