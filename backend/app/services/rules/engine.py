"""The release decision. AI reads documents; this module decides.

check_batch() takes one batch's COAs and the spec of the order line it belongs to, and returns
RELEASE, HOLD or REVIEW with every reason spelled out. It never calls a model.

Policy, in one place:
  HOLD    a critical parameter is out of spec, the CAS number is wrong, or the batch has expired
  REVIEW  anything uncertain: missing or unreadable values, unit problems, low-confidence reads,
          factory and lab disagreeing, batch numbers not matching, a COA still to come
  RELEASE everything passed and nothing is uncertain (a QC manager still approves)
"""

import re
from datetime import date, timedelta

from app.models.enums import CoaSource, Decision, RuleType
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
from app.services.rules.units import UnitMismatch, convert, format_unit, normalize_unit
from app.services.rules.values import (
    Measurement,
    Qualifier,
    parse_measurement,
    text_matches,
    text_verdict,
)

ENGINE_VERSION = "rules-1"
_EPS = 1e-9

SOURCE_LABEL = {CoaSource.FACTORY: "factory COA", CoaSource.LAB: "lab COA"}


def fmt(x: float | None) -> str:
    return "" if x is None else f"{x:g}"


def spec_text(p: ParamSpec) -> str:
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


# ---- One reading against one parameter ---------------------------------------------------


def _numeric_status(p: ParamSpec, m: Measurement, lo: float | None, hi: float | None):
    """Status of a numeric reading (already in the spec's unit) against min/max/range."""
    q = m.qualifier
    checks: list[ParamStatus] = []

    if p.rule_type in (RuleType.MIN, RuleType.RANGE) and p.low is not None:
        if q == Qualifier.NOT_DETECTED:
            checks.append(ParamStatus.FAIL)
        elif q == Qualifier.LT:  # "< x": the true value is somewhere below x
            checks.append(ParamStatus.FAIL if hi <= p.low + _EPS else ParamStatus.UNCLEAR)
        elif q == Qualifier.GT:  # "> x": the true value is somewhere above x
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


def evaluate_reading(
    p: ParamSpec, r: ResultInput, source: CoaSource, coa_id: int | None, cfg: EngineConfig
) -> SourceReading:
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
        if m.is_numeric:
            unit = m.unit if m.unit is not None else p.unit
            try:
                lo = convert(m.value, unit, p.unit)
                hi = convert(m.value_high, unit, p.unit) if m.value_high is not None else lo
            except UnitMismatch:
                reading.note = (
                    f"Unit {m.unit or 'none'} cannot be compared with {p.unit or 'no unit'}."
                )
                return reading
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
                # Limit tests (e.g. heavy metals) are often reported as a pass statement.
                reading.status = ParamStatus.PASS
                reading.note = "Reported as a pass statement, not a number."
            else:
                reading.note = "Expected a number."
        else:
            reading.status = ParamStatus.MISSING
            reading.note = "No value."

    elif p.rule_type == RuleType.TEXT_MATCH:
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

    elif p.rule_type == RuleType.COMPLIES:
        verdict = text_verdict(m.text or r.raw_value or "")
        if verdict is True:
            reading.status = ParamStatus.PASS
        elif verdict is False:
            reading.status = ParamStatus.FAIL
        else:
            reading.note = "No clear pass or fail statement."

    if r.confidence < cfg.low_confidence and reading.status != ParamStatus.MISSING:
        computed = reading.status.value
        reading.status = ParamStatus.UNCLEAR
        reading.note = (
            f"Read with low confidence ({r.confidence:.2f}); would be “{computed}”. Please verify."
        )

    return reading


def _describe_fail(p: ParamSpec, r: SourceReading) -> str:
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
    statuses = {r.status for r in readings}
    for s in (ParamStatus.FAIL, ParamStatus.UNCLEAR, ParamStatus.PASS):
        if s in statuses:
            return s
    return ParamStatus.MISSING


def _discrepancy(p: ParamSpec, readings: list[SourceReading], cfg: EngineConfig) -> str | None:
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


# ---- Identity: is this the right material, batch, and still in date? ---------------------


def _norm_cas(cas: str | None) -> str | None:
    if not cas:
        return None
    digits = re.sub(r"[^0-9]", "", cas)
    return digits or None


def _norm_batch(b: str | None) -> str | None:
    if not b:
        return None
    return re.sub(r"[^A-Z0-9]", "", b.upper()) or None


def _product_name_ok(spec: SpecInput, name: str) -> bool:
    observed = normalize_name(name)
    for candidate in [spec.product_name, *spec.product_synonyms]:
        c = normalize_name(candidate)
        if c and (c in observed or observed in c):
            return True
    return False


def _identity_checks(
    spec: SpecInput, batch: BatchInput, coa: CoaInput, today: date, cfg: EngineConfig
) -> tuple[list[IdentityCheck], list[Finding]]:
    label = SOURCE_LABEL[coa.source]
    checks: list[IdentityCheck] = []
    findings: list[Finding] = []

    def add(code, title, status, message, severity=None):
        checks.append(IdentityCheck(code, title, status, message, coa.source))
        if severity:
            findings.append(Finding(severity, code, f"{message} ({label})"))

    # Product: CAS is decisive when present; the name is a softer check.
    expected_cas, got_cas = _norm_cas(spec.cas_number), _norm_cas(coa.cas_number)
    cas_ok = False
    if got_cas and expected_cas:
        if got_cas == expected_cas:
            cas_ok = True
            add("cas", "CAS number", CheckStatus.PASS, f"CAS {coa.cas_number} matches.")
        else:
            add(
                "cas",
                "CAS number",
                CheckStatus.FAIL,
                f"CAS {coa.cas_number} does not match {spec.cas_number}: wrong material.",
                Severity.HOLD,
            )

    if coa.product_name:
        if _product_name_ok(spec, coa.product_name):
            add("product", "Product", CheckStatus.PASS, f"“{coa.product_name}” matches.")
        elif cas_ok:
            add(
                "product",
                "Product",
                CheckStatus.WARN,
                f"Name “{coa.product_name}” differs, but the CAS number matches.",
            )
        else:
            add(
                "product",
                "Product",
                CheckStatus.FAIL,
                f"Product “{coa.product_name}” does not match {spec.product_name}.",
                Severity.REVIEW,
            )
    elif not got_cas:
        add(
            "product",
            "Product",
            CheckStatus.MISSING,
            "COA does not name the product or give a CAS number.",
            Severity.REVIEW,
        )

    # Batch number must be the same batch we are releasing.
    if not coa.batch_number:
        add(
            "batch_number",
            "Batch number",
            CheckStatus.MISSING,
            "No batch number on the COA.",
            Severity.REVIEW,
        )
    elif _norm_batch(coa.batch_number) != _norm_batch(batch.batch_number):
        add(
            "batch_number",
            "Batch number",
            CheckStatus.FAIL,
            f"COA batch {coa.batch_number} is not {batch.batch_number}.",
            Severity.REVIEW,
        )
    else:
        add("batch_number", "Batch number", CheckStatus.PASS, f"Batch {coa.batch_number}.")

    # Dates
    if coa.mfg_date and coa.test_date and coa.test_date < coa.mfg_date:
        add(
            "dates",
            "Dates",
            CheckStatus.FAIL,
            f"Tested ({coa.test_date}) before it was made ({coa.mfg_date}).",
            Severity.REVIEW,
        )
    if coa.test_date and coa.test_date > today:
        add(
            "dates",
            "Dates",
            CheckStatus.FAIL,
            f"Test date {coa.test_date} is in the future.",
            Severity.REVIEW,
        )
    if coa.expiry_date:
        if coa.expiry_date < today:
            add(
                "expiry",
                "Expiry",
                CheckStatus.FAIL,
                f"Expired on {coa.expiry_date}.",
                Severity.HOLD,
            )
        elif coa.expiry_date <= today + timedelta(days=cfg.expiry_warning_days):
            add(
                "expiry",
                "Expiry",
                CheckStatus.WARN,
                f"Expires soon, on {coa.expiry_date}.",
                Severity.INFO,
            )
        else:
            add("expiry", "Expiry", CheckStatus.PASS, f"Valid until {coa.expiry_date}.")

    return checks, findings


# ---- The whole batch ---------------------------------------------------------------------


def check_batch(
    spec: SpecInput,
    batch: BatchInput,
    *,
    today: date | None = None,
    config: EngineConfig | None = None,
) -> EngineResult:
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

    # Match each COA's rows to parameters, then evaluate parameter by parameter.
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
