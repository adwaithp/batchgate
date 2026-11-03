"""Reader evals: how well Claude reads COAs, and whether the decision survives misreads.

cd backend && uv run python ../evals/run_evals.py           # read with Claude
cd backend && uv run python ../evals/run_evals.py --cached  # re-score saved readings
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.models.enums import CoaSource, Decision  # noqa: E402
from app.schemas.extraction import CoaExtraction  # noqa: E402
from app.seed import PRODUCTS, SPECS, TOLERANCES  # noqa: E402
from app.services.extraction.reader import ExtractionError, read_coa  # noqa: E402
from app.services.extraction.verify import pdf_text, verify_reading  # noqa: E402
from app.services.rules.engine import check_batch  # noqa: E402
from app.services.rules.matching import match_results, normalize_name  # noqa: E402
from app.services.rules.types import (  # noqa: E402
    BatchInput,
    CoaInput,
    ParamSpec,
    ResultInput,
    SpecInput,
)
from app.services.rules.values import parse_measurement  # noqa: E402

RESULTS = ROOT / "results"
READINGS = RESULTS / "readings"
SUITES = [ROOT / "coas" / "manifest.json", ROOT / "real" / "manifest.json"]
CONTENT_TYPES = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".png": "image/png"}  # fmt: skip
HEADER_FIELDS = [
    "issuer_name", "product_name", "cas_number", "batch_number", "po_reference",
    "mfg_date", "test_date", "expiry_date",
]  # fmt: skip
# Free-text names match if one contains the other.
LOOSE_FIELDS = {"issuer_name", "product_name"}
FACTORY_ISSUER = "Kutch Coastal Chemicals"
LOW_CONFIDENCE = 0.8


@dataclass
class Case:
    """One COA with its true values and expected decision."""

    file: Path
    suite: str
    source: CoaSource
    batch_number: str
    expected: Decision
    why: str
    truth: dict
    spec: SpecInput
    expected_issuer: str | None
    partner: CoaInput | None  # the other source's COA; None means only this COA


def build_spec(product: str, grade: str) -> SpecInput:
    """Return the seeded spec for a product and grade as engine input."""
    s = next(x for x in SPECS if x["product"] == product and x["grade"] == grade)
    p = next(x for x in PRODUCTS if x["name"] == product)
    return SpecInput(
        product_name=product,
        cas_number=p["cas_number"],
        product_synonyms=p["synonyms"],
        grade=grade,
        parameters=[
            ParamSpec(
                id=i,
                name=p["name"],
                rule_type=p["rule_type"],
                low=p["low"],
                high=p["high"],
                unit=p["unit"],
                expected_text=p["expected_text"],
                aliases=p["aliases"],
                critical=p["critical"],
                **TOLERANCES.get(p["name"], {}),
            )
            for i, p in enumerate(s["parameters"], start=1)
        ],
    )


def _date(v):
    """Parse an ISO date, or None."""
    return date.fromisoformat(v) if isinstance(v, str) and v else None


def truth_input(truth: dict, source: CoaSource, expected_issuer: str | None) -> CoaInput:
    """Convert true values to engine input."""
    return CoaInput(
        source=source,
        issuer_name=truth.get("issuer_name"),
        expected_issuer=expected_issuer,
        product_name=truth.get("product_name"),
        cas_number=truth.get("cas_number"),
        batch_number=truth.get("batch_number"),
        mfg_date=_date(truth.get("mfg_date")),
        test_date=_date(truth.get("test_date")),
        expiry_date=_date(truth.get("expiry_date")),
        mfg_date_as_printed=truth.get("mfg_date_as_printed"),
        test_date_as_printed=truth.get("test_date_as_printed"),
        expiry_date_as_printed=truth.get("expiry_date_as_printed"),
        results=[
            ResultInput(r["name_as_written"], r["raw_value"], r.get("unit"))
            for r in truth["results"]
        ],
    )


def load_cases(only: str | None = None) -> list[Case]:
    """Load cases from the manifests, optionally filtered by file name."""
    cases: list[Case] = []
    for path in SUITES:
        if not path.exists():
            continue
        docs = json.loads(path.read_text())
        suite = path.parent.name
        by_file = {d["file"]: d for d in docs}
        for d in docs:
            if only and only not in d["file"]:
                continue
            source = CoaSource(d["upload_to"]["source"])
            spec = build_spec(*d.get("spec", ["Ferric Chloride", "40% solution"]))
            issuers = {
                CoaSource.FACTORY: d.get("expected_issuer", FACTORY_ISSUER),
                CoaSource.LAB: d.get("expected_issuer"),
            }
            partner = None
            if partner_file := d.get("partner", "default"):
                if partner_file == "default":
                    partner_file = (
                        "02_lab_clean.pdf"
                        if source == CoaSource.FACTORY
                        else "01_factory_clean.pdf"
                    )
                p = by_file[partner_file]
                p_source = CoaSource(p["upload_to"]["source"])
                p_issuer = (
                    p["truth"]["issuer_name"] if p_source == CoaSource.LAB else FACTORY_ISSUER
                )
                partner = truth_input(p["truth"], p_source, p_issuer)
            if source == CoaSource.LAB and issuers[CoaSource.LAB] is None:
                issuers[CoaSource.LAB] = d["truth"]["issuer_name"]  # the lab chosen at upload
            cases.append(
                Case(
                    file=path.parent / d["file"],
                    suite=suite,
                    source=source,
                    batch_number=d["upload_to"]["batch"],
                    expected=Decision(d["expected_decision"]),
                    why=d["why"],
                    truth=d["truth"],
                    spec=spec,
                    expected_issuer=issuers[source],
                    partner=partner,
                )
            )
    return cases


def reading_path(case: Case) -> Path:
    """Return where a case's reading is saved."""
    return READINGS / case.suite / f"{case.file.name}.json"


def read_case(case: Case, *, cached: bool, reader=read_coa) -> tuple[CoaExtraction | None, str]:
    """Return Claude's reading (or the saved one) and any error."""
    path = reading_path(case)
    if cached:
        if not path.exists():
            return None, "no saved reading (run without --cached first)"
        saved = json.loads(path.read_text())
        if saved.get("error"):
            return None, saved["error"]
        return CoaExtraction.model_validate(saved["reading"]), ""
    content_type = CONTENT_TYPES.get(case.file.suffix.lower(), "application/octet-stream")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        reading = reader(case.file, content_type, case.spec.parameters)
    except ExtractionError as e:
        path.write_text(json.dumps({"error": str(e)}, indent=1))
        return None, str(e)
    path.write_text(
        json.dumps(
            {
                "model": get_settings().extraction_model,
                "read_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "reading": reading.model_dump(mode="json"),
            },
            indent=1,
        )
    )
    return reading, ""


def _squash(v) -> str:
    """Return lowercase letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", str(v).lower()) if v not in (None, "") else ""


def field_ok(name: str, expected, got) -> bool:
    """Return True when a header field was read correctly."""
    e, g = _squash(expected), _squash(got)
    if not e or not g:
        return e == g
    if name in LOOSE_FIELDS:
        return e in g or g in e
    return e == g


def value_ok(expected: str, got: str) -> bool:
    """Return True when two printed values are the same."""
    if _squash(expected) == _squash(got):
        return True
    a, b = parse_measurement(expected), parse_measurement(got)
    return (
        a is not None
        and b is not None
        and a.value is not None
        and a.value == b.value
        and a.qualifier == b.qualifier
    )


def unit_ok(expected: str | None, got: str | None) -> bool:
    """Return True when two printed units are the same."""
    return _unit(expected) == _unit(got)


def _unit(u: str | None) -> str:
    """Normalise a printed unit, treating dashes and n/a as no unit."""
    u = re.sub(r"\s", "", (u or "").lower())
    if u in {"-", "—", "–", "n/a", "na", "none"}:
        return ""
    return {"%w/w": "%", "wt%": "%"}.get(u, u)


def _pair_rows(truth_rows: list[dict], got_rows: list) -> list[tuple[dict, object | None]]:
    """Pair each true row with the reading's row for the same test."""
    free = list(got_rows)
    pairs = []
    for t in truth_rows:
        tn = normalize_name(t["name_as_written"])
        best, score = None, 0.0
        for g in free:
            s = SequenceMatcher(None, tn, normalize_name(g.name_as_written)).ratio()
            if s > score:
                best, score = g, s
        if best is not None and score >= 0.75:
            free.remove(best)
            pairs.append((t, best))
        else:
            pairs.append((t, None))
    return pairs


@dataclass
class Score:
    """Scores for one case."""

    file: str
    suite: str
    expected: str
    got: str | None = None
    error: str = ""
    fields_right: int = 0
    fields_total: int = 0
    values_right: int = 0
    values_total: int = 0
    rows_missed: int = 0
    rows_extra: int = 0
    wrong_but_flagged: int = 0  # misread values that came with confidence < 0.8
    wrong_and_confident: int = 0
    caught_by_text_check: int = 0  # misreads the text check marked unsure
    needless_flags: int = 0  # right values the text check marked unsure anyway
    mistakes: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def decision_ok(self) -> bool:
        """Return True when the decision matches."""
        return self.got == self.expected

    @property
    def false_release(self) -> bool:
        """Return True when a batch that should not ship was released."""
        return self.got == Decision.RELEASE.value and self.expected != Decision.RELEASE.value


def engine_input(reading: CoaExtraction, case: Case) -> CoaInput:
    """Return what the app would give the engine for this reading."""
    results = [
        ResultInput(
            r.name_as_written, r.raw_value, r.unit, confidence=min(max(r.confidence, 0), 1)
        )
        for r in reading.results
    ]
    # as the worker does: hints only fill gaps name matching leaves
    matched, _ = match_results(case.spec.parameters, results)
    claimed, by_name = set(matched), {id(ri) for ri in matched.values()}
    valid = {p.id for p in case.spec.parameters}
    for ri, r in zip(results, reading.results, strict=True):
        if id(ri) not in by_name and r.parameter_id in valid and r.parameter_id not in claimed:
            ri.parameter_id = r.parameter_id
            claimed.add(r.parameter_id)
    return CoaInput(
        source=case.source,
        issuer_name=reading.issuer_name,
        issuer_confidence=min(max(reading.issuer_confidence, 0), 1),
        expected_issuer=case.expected_issuer,
        product_name=reading.product_name,
        cas_number=reading.cas_number,
        batch_number=reading.batch_number,
        mfg_date=reading.mfg_date,
        test_date=reading.test_date,
        expiry_date=reading.expiry_date,
        mfg_date_as_printed=reading.mfg_date_as_printed,
        test_date_as_printed=reading.test_date_as_printed,
        expiry_date_as_printed=reading.expiry_date_as_printed,
        results=results,
    )


def score_case(
    case: Case,
    reading: CoaExtraction | None,
    error: str,
    today: date,
    text: str | None = None,
) -> Score:
    """Score a reading, then decide on it after the text check."""
    s = Score(file=case.file.name, suite=case.suite, expected=case.expected.value, error=error)
    if reading is None:
        # A failed read means manual entry, not a false release.
        s.got = None
        s.mistakes.append(f"read failed: {error}")
        return s

    for name in HEADER_FIELDS:
        expected, got = case.truth.get(name), getattr(reading, name)
        got = got.isoformat() if isinstance(got, date) else got
        s.fields_total += 1
        if field_ok(name, expected, got):
            s.fields_right += 1
        else:
            s.mistakes.append(f"{name}: expected {expected!r}, read {got!r}")

    checked, _ = verify_reading(reading, text)
    unsure_after_check = {
        id(raw)
        for raw, after in zip(reading.results, checked.results, strict=True)
        if after.confidence < raw.confidence
    }
    pairs = _pair_rows(case.truth["results"], reading.results)
    s.rows_extra = len(reading.results) - sum(1 for _, g in pairs if g is not None)
    for t, g in pairs:
        s.values_total += 1
        if g is None:
            s.rows_missed += 1
            s.mistakes.append(f"missed row {t['name_as_written']!r}")
            continue
        if value_ok(t["raw_value"], g.raw_value) and unit_ok(t.get("unit"), g.unit):
            s.values_right += 1
            s.needless_flags += id(g) in unsure_after_check
            continue
        s.caught_by_text_check += id(g) in unsure_after_check
        flagged = g.confidence < LOW_CONFIDENCE
        s.wrong_but_flagged += flagged
        s.wrong_and_confident += not flagged
        s.mistakes.append(
            f"{t['name_as_written']}: expected {t['raw_value']!r} {t.get('unit') or ''}, "
            f"read {g.raw_value!r} {g.unit or ''} (confidence {g.confidence:.2f})"
        )

    coas = [engine_input(checked, case)] + ([case.partner] if case.partner else [])
    result = check_batch(case.spec, BatchInput(case.batch_number, coas), today=today)
    s.got, s.summary = result.decision.value, result.summary
    return s


def _pct(a: int, b: int) -> str:
    """Format a percentage."""
    return f"{100 * a / b:.0f}%" if b else "–"


def report(scores: list[Score], model: str) -> str:
    """Render the results as Markdown."""
    n = len(scores)
    fr = [s for s in scores if s.false_release]
    lines = [
        "# BatchGate eval results",
        "",
        f"Model `{model}` · {n} documents · {datetime.now(UTC):%Y-%m-%d}",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| **False releases** (released when it should not) | **{len(fr)}** |",
        f"| Correct decision | {sum(s.decision_ok for s in scores)} / {n} |",
        f"| Header fields read correctly | {_pct(sum(s.fields_right for s in scores), sum(s.fields_total for s in scores))} |",  # noqa: E501
        f"| Result values read correctly | {_pct(sum(s.values_right for s in scores), sum(s.values_total for s in scores))} |",  # noqa: E501
        f"| Misread values that Claude flagged as unsure | {sum(s.wrong_but_flagged for s in scores)} of {sum(s.wrong_but_flagged + s.wrong_and_confident for s in scores)} |",  # noqa: E501
        f"| Misreads caught by the PDF text check | {sum(s.caught_by_text_check for s in scores)} |",  # noqa: E501
        "| Right values the text check flagged anyway | "
        f"{sum(s.needless_flags for s in scores)} |",
        f"| Unneeded reviews (should have released) | {sum(s.expected == 'release' and s.got in ('review', 'hold') for s in scores)} |",  # noqa: E501
        f"| Reads that failed (manual entry) | {sum(s.got is None for s in scores)} |",
        "",
        "| Document | Expected | BatchGate | Fields | Values | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for s in scores:
        mark = "✅" if s.decision_ok else ("❌ **false release**" if s.false_release else "⚠️")
        notes = "; ".join(s.mistakes[:3]) + (" …" if len(s.mistakes) > 3 else "")
        lines.append(
            f"| `{s.file}` ({s.suite}) | {s.expected} | {s.got or 'manual'} {mark} | "
            f"{s.fields_right}/{s.fields_total} | {s.values_right}/{s.values_total} | "
            f"{notes.replace('|', '/')} |"
        )
    lines += [
        "",
        "Decisions are made by the rules engine on Claude's reading, never by Claude. A failed "
        "read falls back to manual entry and is never released on its own.",
    ]
    return "\n".join(lines) + "\n"


def _swap_digits(value: str) -> str | None:
    """Return a near-miss misread of a value."""
    digits = [i for i, ch in enumerate(value) if ch.isdigit()]
    if len(digits) < 2:
        return None
    a, b = digits[-2], digits[-1]
    chars = list(value)
    if chars[a] != chars[b]:
        chars[a], chars[b] = chars[b], chars[a]
    else:
        chars[b] = str((int(chars[b]) + 1) % 10)
    return "".join(chars)


def _partner_values(case: Case, reading: CoaExtraction) -> dict[int, str]:
    """Return the other COA's value for each row Claude read."""
    if case.partner is None:
        return {}
    ours = [ResultInput(r.name_as_written, r.raw_value, r.unit) for r in reading.results]
    mine, _ = match_results(case.spec.parameters, ours)
    theirs, _ = match_results(case.spec.parameters, case.partner.results)
    index = {id(ri): i for i, ri in enumerate(ours)}
    return {index[id(ri)]: theirs[pid].raw_value for pid, ri in mine.items() if pid in theirs}


def planted_misreads(reading: CoaExtraction, partner_values: dict[int, str] | None = None):
    """Yield readings with one numeric result replaced by a wrong value."""
    partner_values = partner_values or {}
    for i, row in enumerate(reading.results):
        if not re.search(r"\d", row.raw_value):
            continue
        limit_numbers = _NUMBERS.findall(row.limit_as_printed or "")
        for kind, wrong in (("limit", limit_numbers[0] if limit_numbers else None),
                            ("digit swap", _swap_digits(row.raw_value)),
                            ("other COA's value", partner_values.get(i))):  # fmt: skip
            if wrong is None or value_ok(row.raw_value, wrong):
                continue
            rows = list(reading.results)
            rows[i] = row.model_copy(update={"raw_value": wrong, "confidence": 1.0})
            yield kind, row.name_as_written, wrong, reading.model_copy(update={"results": rows})


_NUMBERS = re.compile(r"\d+(?:\.\d+)?")


def stress(cases: list[Case], today: date) -> str:
    """Count planted misreads that would release, with and without the check."""
    tally = {"text": [0, 0, 0, 0, 0], "none": [0, 0, 0, 0, 0]}  # planted, unseen, false release
    for case in cases:
        reading, _ = read_case(case, cached=True)
        if reading is None:
            continue
        content_type = CONTENT_TYPES.get(case.file.suffix.lower(), "")
        text = pdf_text(case.file, content_type)
        bucket = tally["text" if text else "none"]
        for _kind, _name, _wrong, bad in planted_misreads(reading, _partner_values(case, reading)):
            bucket[0] += 1
            for col, check_text in ((1, None), (3, text)):
                checked, _ = verify_reading(bad, check_text)
                coas = [engine_input(checked, case)] + ([case.partner] if case.partner else [])
                d = check_batch(case.spec, BatchInput(case.batch_number, coas), today=today)
                if d.decision == Decision.RELEASE:
                    bucket[col] += 1
                    bucket[col + 1] += case.expected != Decision.RELEASE
    t, n = tally["text"], tally["none"]
    return "\n".join(
        [
            "## Stress test: planted misreads",
            "",
            "Each numeric value Claude read is replaced, one at a time, by a confident wrong "
            "value (its own printed limit, two digits swapped, or the other COA's value for the "
            "same test), then decided again. *Unseen* means the batch was released, so no person "
            "looked at the wrong value.",
            "",
            "| Documents | Planted misreads | Unseen without the text check "
            "| Unseen with it | False releases without / with |",
            "|---|---|---|---|---|",
            f"| PDFs with a text layer | {t[0]} | {t[1]} | **{t[3]}** | {t[2]} / **{t[4]}** |",
            "| Scans and photos (nothing to check) "
            f"| {n[0]} | {n[1]} | {n[3]} | {n[2]} / {n[4]} |",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    """Run the evals and write evals/results/latest.md."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cached", action="store_true", help="score saved readings, no API calls")
    parser.add_argument("--only", help="run documents whose file name contains this")
    args = parser.parse_args(argv)

    if not args.cached and not get_settings().anthropic_api_key:
        print("No ANTHROPIC_API_KEY set. Add it to backend/.env, or use --cached.")
        return 2

    cases = load_cases(args.only)
    today = date.today()
    scores = []
    for case in cases:
        print(f"· {case.suite}/{case.file.name} …", end=" ", flush=True)
        reading, error = read_case(case, cached=args.cached)
        content_type = CONTENT_TYPES.get(case.file.suffix.lower(), "")
        s = score_case(case, reading, error, today, pdf_text(case.file, content_type))
        scores.append(s)
        verdict = "ok" if s.decision_ok else ("FALSE RELEASE" if s.false_release else "differs")
        print(f"{s.got or 'manual'} (expected {s.expected}) {verdict}")

    RESULTS.mkdir(exist_ok=True)
    text = report(scores, get_settings().extraction_model) + "\n" + stress(cases, today)
    (RESULTS / "latest.md").write_text(text)
    (RESULTS / "latest.json").write_text(
        json.dumps(
            [asdict(s) | {"false_release": s.false_release} for s in scores], indent=1, default=str
        )
    )
    print("\n" + text)
    return 1 if any(s.false_release for s in scores) else 0


if __name__ == "__main__":
    sys.exit(main())
