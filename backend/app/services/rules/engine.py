"""The release decision. Claude reads documents; this module decides.

check_batch() compares a batch's COAs with its spec and returns RELEASE, HOLD or REVIEW with every
reason.

  HOLD     critical result out of spec, wrong CAS, wrong product form, or expired
  REVIEW   anything uncertain: missing or unclear values, unit problems, low
           confidence, factory and lab disagreeing, mismatched identity, missing COA
  RELEASE  everything passed (a QC manager still approves)
"""

import re
from datetime import date, timedelta

from app.models.enums import CoaSource, Decision, RuleType
from app.services.rules.grade import compare_grade
from app.services.rules.matching import match_results, normalize_name
from app.services.rules.types import (
    BatchInput,
    CheckStatus,
    CoaInput,
    EngineConfig,
    EngineResult,
    Finding,
    IdentityCheck,
    ParameterCheck,
    ParamSpec,
    ParamStatus,
    ResultInput,
    Severity,
    SourceReading,
    SpecInput,
    UnmatchedResult,
)
from app.services.rules.units import UnitMismatchError, convert, format_unit, normalize_unit
from app.services.rules.values import (
    Measurement,
    Qualifier,
    month_start,
    parse_measurement,
    text_matches,
    text_verdict,
)

ENGINE_VERSION = "rules-3"
_EPS = 1e-9

SOURCE_LABEL = {CoaSource.FACTORY: "factory COA", CoaSource.LAB: "lab COA"}


def fmt(x: float | None) -> str:
    """Format a number without trailing zeros."""
    return "" if x is None else f"{x:g}"


def spec_text(p: ParamSpec) -> str:
    """Return a parameter's limit as text, e.g. max 0.5 %."""
    u = format_unit(p.unit)
    match p.rule_type:
        case RuleType.MIN:
            return f"min {fmt(p.low)}{u}"
        case RuleType.MAX:
            return f"max {fmt(p.high)}{u}"
        case RuleType.RANGE:
            return f"{fmt(p.low)} – {fmt(p.high)}{u}"
        case RuleType.TEXT_MATCH:
            return p.expected_text or ""
        case RuleType.COMPLIES:
            return "Complies"
    return ""


def _numeric_status(p: ParamSpec, m: Measurement, lo: float | None, hi: float | None):
    """Return the status of a numeric reading against the limits."""
    q = m.qualifier
    checks: list[ParamStatus] = []

    if p.rule_type in (RuleType.MIN, RuleType.RANGE) and p.low is not None:
        if q == Qualifier.NOT_DETECTED:
            checks.append(ParamStatus.FAIL)
        elif q == Qualifier.LT:  # "< x": the value is below x
            checks.append(ParamStatus.FAIL if hi <= p.low + _EPS else ParamStatus.UNCLEAR)
        elif q == Qualifier.GT:  # "> x": the value is above x
            checks.append(ParamStatus.PASS if lo >= p.low - _EPS else ParamStatus.UNCLEAR)
        else:
            checks.append(ParamStatus.PASS if lo >= p.low - _EPS else ParamStatus.FAIL)

    if p.rule_type in (RuleType.MAX, RuleType.RANGE) and p.high is not None:
        if q == Qualifier.NOT_DETECTED:
            checks.append(ParamStatus.PASS)
        elif q == Qualifier.GT:
            checks.append(ParamStatus.FAIL if lo >= p.high - _EPS else ParamStatus.UNCLEAR)
        elif q == Qualifier.LT:
            checks.append(ParamStatus.PASS if hi <= p.high + _EPS else ParamStatus.UNCLEAR)
        else:
            checks.append(ParamStatus.PASS if hi <= p.high + _EPS else ParamStatus.FAIL)

    if ParamStatus.FAIL in checks:
        return ParamStatus.FAIL
    if ParamStatus.UNCLEAR in checks:
        return ParamStatus.UNCLEAR
    return ParamStatus.PASS


def _evaluate_numeric(
    p: ParamSpec, m: Measurement, r: ResultInput, reading: SourceReading
) -> bool:
    """Evaluate a reading against a min, max or range limit; False if units can't be compared."""
    if m.is_numeric:
        unit = m.unit if m.unit is not None else p.unit
        try:
            lo = convert(m.value, unit, p.unit)
            hi = convert(m.value_high, unit, p.unit) if m.value_high is not None else lo
        except UnitMismatchError:
            reading.note = (
                f"Unit {m.unit or 'none'} cannot be compared with {p.unit or 'no unit'}."
            )
            return False
        reading.value = lo if m.value_high is None else None
        reading.status = _numeric_status(p, m, lo, hi)
        if m.unit is None and p.unit:
            reading.note = f"No unit printed; read as {p.unit}."
        elif normalize_unit(m.unit) != normalize_unit(p.unit):
            reading.note = f"Converted from {m.unit} to {p.unit}."
        if reading.status == ParamStatus.UNCLEAR:
            reading.note = f"“{r.raw_value}” is not precise enough to compare with the limit."
    elif m.qualifier == Qualifier.NOT_DETECTED:
        reading.status = _numeric_status(p, m, None, None)
        reading.note = "Reported as not detected."
    elif m.text is not None:
        verdict = text_verdict(m.text)
        if verdict is False:
            reading.status = ParamStatus.FAIL
        elif verdict is True and p.rule_type == RuleType.MAX:
            # Limit tests are often reported as a pass statement.
            reading.status = ParamStatus.PASS
            reading.note = "Reported as a pass statement, not a number."
        else:
            reading.note = "Expected a number."
    else:
        reading.status = ParamStatus.MISSING
        reading.note = "No value."
    return True


def _evaluate_text(p: ParamSpec, m: Measurement, r: ResultInput, reading: SourceReading) -> None:
    """Evaluate a description against the spec's expected text."""
    observed = (m.text or r.raw_value or "").strip()
    if not observed:
        reading.status = ParamStatus.MISSING
    elif p.expected_text and text_matches(p.expected_text, observed):
        reading.status = ParamStatus.PASS
    elif text_verdict(observed) is True:
        reading.status = ParamStatus.PASS
        reading.note = "Lab states it complies."
    elif text_verdict(observed) is False:
        reading.status = ParamStatus.FAIL
    else:
        reading.note = "Description differs from the spec wording; needs a person to judge."


def _evaluate_complies(m: Measurement, r: ResultInput, reading: SourceReading) -> None:
    """Evaluate a pass or fail statement."""
    verdict = text_verdict(m.text or r.raw_value or "")
    if verdict is True:
        reading.status = ParamStatus.PASS
    elif verdict is False:
        reading.status = ParamStatus.FAIL
    else:
        reading.note = "No clear pass or fail statement."


def evaluate_reading(
    p: ParamSpec, r: ResultInput, source: CoaSource, coa_id: int | None, cfg: EngineConfig
) -> SourceReading:
    """Evaluate one COA reading against one spec parameter."""
    m = parse_measurement(r.raw_value, r.unit)
    reading = SourceReading(
        source=source,
        coa_id=coa_id,
        raw_value=r.raw_value,
        unit=r.unit,
        value=None,
        status=ParamStatus.UNCLEAR,
        confidence=r.confidence,
    )
    if p.rule_type in (RuleType.MIN, RuleType.MAX, RuleType.RANGE):
        if not _evaluate_numeric(p, m, r, reading):
            return reading
    elif p.rule_type == RuleType.TEXT_MATCH:
        _evaluate_text(p, m, r, reading)
    elif p.rule_type == RuleType.COMPLIES:
        _evaluate_complies(m, r, reading)

    if r.confidence < cfg.low_confidence and reading.status != ParamStatus.MISSING:
        computed = reading.status.value
        reading.status = ParamStatus.UNCLEAR
        reading.note = (
            f"Read with low confidence ({r.confidence:.2f}); would be “{computed}”. Please verify."
        )

    return reading


def _describe_fail(p: ParamSpec, r: SourceReading) -> str:
    """Describe why a reading failed."""
    shown = r.raw_value.strip()
    if r.unit and not re.search(r"[a-zA-Z%°]", shown):
        shown = f"{shown} {r.unit}"
    if r.value is not None and p.high is not None and r.value > p.high:
        return f"{shown} is above {spec_text(p)}"
    if r.value is not None and p.low is not None and r.value < p.low:
        return f"{shown} is below {spec_text(p)}"
    if p.rule_type in (RuleType.TEXT_MATCH, RuleType.COMPLIES):
        return f"reported “{shown}”"
    return f"{shown} is outside {spec_text(p)}"


def _combine(readings: list[SourceReading]) -> ParamStatus:
    """Return the worst status across the factory and lab readings."""
    statuses = {r.status for r in readings}
    for s in (ParamStatus.FAIL, ParamStatus.UNCLEAR, ParamStatus.PASS):
        if s in statuses:
            return s
    return ParamStatus.MISSING


def _discrepancy(p: ParamSpec, readings: list[SourceReading], cfg: EngineConfig) -> str | None:
    """Describe a factory-vs-lab difference beyond tolerance, if any."""
    factory = next((r for r in readings if r.source == CoaSource.FACTORY), None)
    lab = next((r for r in readings if r.source == CoaSource.LAB), None)
    if not factory or not lab or factory.value is None or lab.value is None:
        return None
    if factory.status == ParamStatus.UNCLEAR or lab.status == ParamStatus.UNCLEAR:
        return None
    diff = abs(factory.value - lab.value)
    pct = cfg.default_tolerance_pct if p.tolerance_pct is None else p.tolerance_pct
    allowed = max(p.tolerance_abs or 0.0, pct / 100 * max(abs(factory.value), abs(lab.value)))
    if diff > allowed + _EPS:
        u = format_unit(p.unit)
        return (
            f"Factory reports {fmt(factory.value)}{u}, lab reports {fmt(lab.value)}{u} "
            f"(difference {fmt(round(diff, 6))}{u}, allowed {fmt(round(allowed, 6))}{u})."
        )
    return None


def _norm_cas(cas: str | None) -> str | None:
    """Normalise a CAS number for comparison."""
    if not cas:
        return None
    digits = re.sub(r"[^0-9]", "", cas)
    return digits or None


def _norm_batch(b: str | None) -> str | None:
    """Normalise a batch number for comparison."""
    if not b:
        return None
    return re.sub(r"[^A-Z0-9]", "", b.upper()) or None


def _squash(text: str) -> str:
    """Lowercase letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", normalize_name(text))


def _same_name(a: str, b: str) -> bool:
    """Return True when names match ignoring spacing and punctuation."""
    x, y = _squash(a), _squash(b)
    return bool(x and y) and (x in y or y in x)


_LEGAL_SUFFIXES = {
    "pvt", "private", "ltd", "limited", "llc", "llp", "inc", "incorporated", "co", "company",
    "corp", "corporation", "plc", "gmbh", "ag", "sa", "bv", "fze", "fzco", "fzc",
}  # fmt: skip


def _company(name: str) -> str:
    """Return a company name squashed, without legal suffixes."""
    words = re.findall(r"[a-z0-9]+", normalize_name(name))
    while words and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return "".join(words)


def _product_name_ok(spec: SpecInput, name: str) -> bool:
    """Return True when the printed product name matches."""
    return any(_same_name(name, c) for c in [spec.product_name, *spec.product_synonyms])


class _Checks:
    """Collects one COA's identity checks and the findings they raise."""

    def __init__(self, coa: CoaInput) -> None:
        """Start an empty collection for `coa`."""
        self.source = coa.source
        self.label = SOURCE_LABEL[coa.source]
        self.checks: list[IdentityCheck] = []
        self.findings: list[Finding] = []

    def add(self, code, title, status, message, severity=None) -> None:
        """Record a check and, when it has a severity, a finding."""
        self.checks.append(IdentityCheck(code, title, status, message, self.source))
        if severity:
            self.findings.append(Finding(severity, code, f"{message} ({self.label})"))


def _check_product(spec: SpecInput, coa: CoaInput, out: _Checks) -> None:
    """Check the CAS number and product name; CAS decides when present."""
    expected_cas, got_cas = _norm_cas(spec.cas_number), _norm_cas(coa.cas_number)
    cas_ok = False
    if got_cas and expected_cas:
        if got_cas == expected_cas:
            cas_ok = True
            out.add("cas", "CAS number", CheckStatus.PASS, f"CAS {coa.cas_number} matches.")
        else:
            out.add(
                "cas",
                "CAS number",
                CheckStatus.FAIL,
                f"CAS {coa.cas_number} does not match {spec.cas_number}: wrong material.",
                Severity.HOLD,
            )

    if coa.product_name:
        if _product_name_ok(spec, coa.product_name):
            out.add(
                "product",
                "Product",
                CheckStatus.PASS,
                f"“{coa.product_name}” is {spec.product_name}.",
            )
        elif cas_ok:
            out.add(
                "product",
                "Product",
                CheckStatus.WARN,
                f"Name “{coa.product_name}” differs, but the CAS number matches.",
            )
        else:
            out.add(
                "product",
                "Product",
                CheckStatus.FAIL,
                f"Product “{coa.product_name}” does not match {spec.product_name}.",
                Severity.REVIEW,
            )
    elif not got_cas:
        out.add(
            "product",
            "Product",
            CheckStatus.MISSING,
            "COA does not name the product or give a CAS number.",
            Severity.REVIEW,
        )


def _check_grade(spec: SpecInput, coa: CoaInput, out: _Checks) -> None:
    """Check the printed product name against the order line's grade."""
    if spec.grade:
        g = compare_grade(spec.grade, coa.product_name)
        if g.status == "pass":
            out.add("grade", "Grade", CheckStatus.PASS, g.message)
        elif g.status == "conflict":
            out.add("grade", "Grade", CheckStatus.FAIL, g.message, Severity.HOLD)
        elif g.status == "strength":
            out.add("grade", "Grade", CheckStatus.FAIL, g.message, Severity.REVIEW)
        elif g.status == "unknown":
            out.add("grade", "Grade", CheckStatus.MISSING, g.message, Severity.INFO)


def _check_issuer(coa: CoaInput, cfg: EngineConfig, out: _Checks) -> None:
    """Check who issued the COA; only the expected company name passes."""
    printed, expected = coa.issuer_name, coa.expected_issuer
    if not printed:
        out.add(
            "issuer",
            "Issued by",
            CheckStatus.MISSING,
            "No issuer on the COA, so who issued it was not checked.",
            Severity.INFO,
        )
    elif not expected:
        out.add(
            "issuer",
            "Issued by",
            CheckStatus.MISSING,
            f"Issued by {printed}; no lab was chosen for this COA to compare it with.",
            Severity.INFO,
        )
    else:
        p, e = _company(printed), _company(expected)
        should_be = (
            f"the batch is from {expected}"
            if coa.source == CoaSource.FACTORY
            else f"the lab chosen for it is {expected}"
        )
        if p and p == e:
            if coa.issuer_confidence < cfg.low_confidence:
                out.add(
                    "issuer",
                    "Issued by",
                    CheckStatus.WARN,
                    f"Issuer read as “{printed}” with low confidence "
                    f"({coa.issuer_confidence:.2f}); check who issued it.",
                    Severity.REVIEW,
                )
            else:
                out.add("issuer", "Issued by", CheckStatus.PASS, f"Issued by {printed}.")
        elif p and e and (p in e or e in p):
            out.add(
                "issuer",
                "Issued by",
                CheckStatus.WARN,
                f"Issued by “{printed}”, which only partly matches {expected}; "
                "check who issued it.",
                Severity.REVIEW,
            )
        else:
            out.add(
                "issuer",
                "Issued by",
                CheckStatus.FAIL,
                f"This COA is issued by {printed}, but {should_be}.",
                Severity.REVIEW,
            )


def _check_batch_number(batch: BatchInput, coa: CoaInput, out: _Checks) -> None:
    """Check the COA is for this batch."""
    if not coa.batch_number:
        out.add(
            "batch_number",
            "Batch number",
            CheckStatus.MISSING,
            "No batch number on the COA.",
            Severity.REVIEW,
        )
    elif _norm_batch(coa.batch_number) != _norm_batch(batch.batch_number):
        out.add(
            "batch_number",
            "Batch number",
            CheckStatus.FAIL,
            f"COA batch {coa.batch_number} is not {batch.batch_number}.",
            Severity.REVIEW,
        )
    else:
        out.add("batch_number", "Batch number", CheckStatus.PASS, f"Batch {coa.batch_number}.")


def _check_dates(coa: CoaInput, today: date, cfg: EngineConfig, out: _Checks) -> None:
    """Check test and manufacturing dates and the expiry."""
    if coa.mfg_date and coa.test_date and coa.test_date < coa.mfg_date:
        out.add(
            "dates",
            "Dates",
            CheckStatus.FAIL,
            f"Tested ({coa.test_date}) before it was made ({coa.mfg_date}).",
            Severity.REVIEW,
        )
    if coa.test_date and coa.test_date > today:
        out.add(
            "dates",
            "Dates",
            CheckStatus.FAIL,
            f"Test date {coa.test_date} is in the future.",
            Severity.REVIEW,
        )
    # A month-and-year expiry is taken as its first day.
    expiry, printed = coa.expiry_date, coa.expiry_date_as_printed
    if expiry is None and printed and (expiry := month_start(printed)):
        out.findings.append(
            Finding(
                Severity.INFO,
                "expiry_day_assumed",
                f"Expiry printed as “{printed}”, with no day; checked as {expiry}, "
                f"the earliest it could mean ({out.label}).",
            )
        )
    if expiry is None and printed:
        # A printed date that is not clear needs a person.
        out.add(
            "expiry",
            "Expiry",
            CheckStatus.WARN,
            f"Expiry printed as “{printed}” could mean more than one date; "
            "check it against the document.",
            Severity.REVIEW,
        )
    elif expiry is None:
        out.add(
            "expiry",
            "Expiry",
            CheckStatus.MISSING,
            "No expiry date on the COA, so shelf life was not checked.",
            Severity.INFO,
        )
    elif expiry < today:
        out.add("expiry", "Expiry", CheckStatus.FAIL, f"Expired on {expiry}.", Severity.HOLD)
    elif expiry <= today + timedelta(days=cfg.expiry_warning_days):
        out.add("expiry", "Expiry", CheckStatus.WARN, f"Expires soon, on {expiry}.", Severity.INFO)
    else:
        out.add("expiry", "Expiry", CheckStatus.PASS, f"Valid until {expiry}.")


def _identity_checks(
    spec: SpecInput, batch: BatchInput, coa: CoaInput, today: date, cfg: EngineConfig
) -> tuple[list[IdentityCheck], list[Finding]]:
    """Check product, grade, issuer, batch number and dates on one COA."""
    out = _Checks(coa)
    _check_product(spec, coa, out)
    _check_grade(spec, coa, out)
    _check_issuer(coa, cfg, out)
    _check_batch_number(batch, coa, out)
    _check_dates(coa, today, cfg, out)
    return out.checks, out.findings


def check_batch(
    spec: SpecInput,
    batch: BatchInput,
    *,
    today: date | None = None,
    config: EngineConfig | None = None,
) -> EngineResult:
    """Check a batch's COAs against its spec and return the decision."""
    cfg = config or EngineConfig()
    today = today or date.today()
    findings: list[Finding] = []
    identity: list[IdentityCheck] = []
    unmatched: list[UnmatchedResult] = []

    sources = {c.source for c in batch.coas}
    if CoaSource.FACTORY not in sources:
        findings.append(
            Finding(Severity.REVIEW, "factory_coa_missing", "Factory COA not received yet.")
        )
    if cfg.require_lab_coa and CoaSource.LAB not in sources:
        findings.append(
            Finding(
                Severity.REVIEW,
                "lab_coa_missing",
                "Independent lab COA not received yet.",
            )
        )

    # Match each COA's rows to parameters, then evaluate each parameter.
    per_param: dict[int, list[SourceReading]] = {p.id: [] for p in spec.parameters}
    by_id = {p.id: p for p in spec.parameters}
    for coa in batch.coas:
        matched, rest = match_results(spec.parameters, coa.results)
        for pid, result in matched.items():
            per_param[pid].append(evaluate_reading(by_id[pid], result, coa.source, coa.id, cfg))
        unmatched += [
            UnmatchedResult(coa.source, r.name_as_written, r.raw_value, r.unit) for r in rest
        ]
        checks, id_findings = _identity_checks(spec, batch, coa, today, cfg)
        identity += checks
        findings += id_findings

    parameters: list[ParameterCheck] = []
    for p in spec.parameters:
        readings = per_param[p.id]
        status = _combine(readings)
        check = ParameterCheck(
            parameter_id=p.id,
            name=p.name,
            spec_text=spec_text(p),
            critical=p.critical,
            status=status,
            readings=readings,
        )

        if status == ParamStatus.FAIL:
            failing = [r for r in readings if r.status == ParamStatus.FAIL]
            where = " and ".join(SOURCE_LABEL[r.source] for r in failing)
            check.note = f"{_describe_fail(p, failing[0])} ({where})."
            findings.append(
                Finding(
                    Severity.HOLD if p.critical else Severity.REVIEW,
                    "out_of_spec",
                    f"{p.name}: {check.note}",
                    p.id,
                )
            )
        elif status == ParamStatus.UNCLEAR:
            note = next(r.note for r in readings if r.status == ParamStatus.UNCLEAR)
            check.note = note
            findings.append(
                Finding(
                    Severity.REVIEW if p.critical else Severity.INFO,
                    "unclear",
                    f"{p.name}: {note}",
                    p.id,
                )
            )
        elif status == ParamStatus.MISSING and batch.coas:
            check.note = "Not reported on any COA."
            findings.append(
                Finding(
                    Severity.REVIEW if p.critical else Severity.INFO,
                    "missing",
                    f"{p.name}: not reported on any COA.",
                    p.id,
                )
            )

        disc = _discrepancy(p, readings, cfg)
        if disc:
            check.discrepancy = disc
            findings.append(Finding(Severity.REVIEW, "discrepancy", f"{p.name}: {disc}", p.id))

        parameters.append(check)

    if any(f.severity == Severity.HOLD for f in findings):
        decision = Decision.HOLD
    elif any(f.severity == Severity.REVIEW for f in findings):
        decision = Decision.REVIEW
    else:
        decision = Decision.RELEASE

    return EngineResult(
        decision=decision,
        summary=_summary(decision, findings, parameters, sources),
        parameters=parameters,
        identity=identity,
        findings=sorted(findings, key=lambda f: list(Severity).index(f.severity)),
        unmatched=unmatched,
    )


def _summary(
    decision: Decision,
    findings: list[Finding],
    parameters: list[ParameterCheck],
    sources: set[CoaSource],
) -> str:
    """Return a one-sentence summary of the decision."""
    if decision == Decision.RELEASE:
        docs = " and ".join(SOURCE_LABEL[s] for s in sorted(sources))
        return (
            f"All {len(parameters)} parameters are within spec on the {docs}. "
            "Ready for release approval."
        )
    severity = Severity.HOLD if decision == Decision.HOLD else Severity.REVIEW
    reasons = [f for f in findings if f.severity == severity]
    head = "Hold" if decision == Decision.HOLD else "Needs review"
    more = f" (+{len(reasons) - 1} more)" if len(reasons) > 1 else ""
    return f"{head}: {reasons[0].message}{more}"
