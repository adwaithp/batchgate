# Rules engine

`backend/app/services/rules/` decides whether a batch can ship. It is plain Python with no
database and no AI: dataclasses in (`types.py`), dataclasses out, so it is easy to test and to
evaluate. `check_batch()` takes the spec of the batch's order line and the batch's active COAs and
returns a decision with every finding.

## Policy

| Decision | When |
|---|---|
| **HOLD** | A critical result is out of spec, the CAS number is wrong, the COA is for a different form of the product than the ordered grade (anhydrous vs solution), or the batch has expired |
| **REVIEW** | Anything uncertain: a missing or unreadable value, a unit that cannot be converted, a value not precise enough for the limit, a low-confidence reading, factory and lab disagreeing beyond tolerance, a strength that differs from the grade, a mismatched batch number, product or issuer, an unclear expiry date, or a required lab COA still missing |
| **RELEASE** | Everything passed and nothing is uncertain; a QC manager still approves |

Settings that shape the policy (see [Development](development.md#configuration)):
`require_lab_coa`, `default_tolerance_pct` (2 % relative) and `low_confidence_threshold` (0.8).

## Checking a result

1. **Matching** (`matching.py`): each COA row is matched to a spec parameter by an explicit id,
   then exact name or alias, then a fuzzy match only when one candidate is clearly best. Ambiguous
   rows stay unmatched for a person.
2. **Parsing** (`values.py`): the printed value becomes data: numbers with qualifiers (`< 0.01`,
   `NMT 0.5`), ranges (`131.0 – 133.5`), not detected (`ND`), and text (`Complies`). Decimal
   commas are accepted.
3. **Units** (`units.py`): the many spellings seen on COAs are normalised (`wt%` and `% m/m` are
   `%`, `mg/kg` is `ppm`), and mass fractions are converted exactly between %, ppm and ppb. Units
   that cannot be converted, such as % w/v against % w/w, are never guessed.
4. **Evaluation** by rule type:
   - `min`, `max`, `range`: the converted value against the limits. `< 20` against a maximum of 10
     is unclear. A pass statement is accepted for a maximum (limit tests).
   - `text_match`: every meaningful word of an acceptable description must appear;
     "White to off-white" accepts either variant.
   - `complies`: an explicit pass or fail statement.
5. **Confidence**: a reading below the threshold becomes unclear, showing what it would have been.
6. **Factory vs lab**: both readings are combined (worst status wins) and compared against the
   parameter's absolute or relative tolerance.
7. **Severity**: a failing critical parameter holds the batch and a failing non-critical one needs
   review. An unclear or missing critical parameter needs review; a non-critical one is only noted.

## Identity checks

Each COA is also checked for what it is about:

| Check | Pass | Otherwise |
|---|---|---|
| CAS number | matches the product | wrong material: HOLD |
| Product name | matches the product or a synonym | REVIEW (a warning only if the CAS matches) |
| Grade | form and strength agree with the order line's grade | form conflict: HOLD; strength differs: REVIEW; not stated: INFO |
| Issuer | same company as the batch's factory, or the lab chosen at upload, ignoring legal suffixes | partial match, different name or low confidence: REVIEW |
| Batch number | the batch being released | REVIEW |
| Dates | test date after manufacture and not in the future | REVIEW |
| Expiry | in date | expired: HOLD; expires within 30 days: INFO |

## Grade check

`grade.py` reads the form (anhydrous, hydrate, solution, solid) and strength (the first
percentage) from the order line's grade and the product name printed on the COA. Anhydrous and a
solution are different products even when every result passes: an anhydrous 98 % COA checked
against a 40 % solution line would otherwise release on assay alone. Grades are nominal, so
strengths may differ by up to max(1 point, 5 %).

## Dates

Dates are never guessed. A full, unambiguous date is checked directly. A month-and-year expiry
("June 2031") is checked as its first day, the earliest it could mean, with an INFO finding. A
printed date whose day and month order is unclear ("03/04/2026") goes to a person.

## Engine version

Each verdict records the engine version (`ENGINE_VERSION`), so a decision can be traced to the
rules that made it. Re-running an unchanged check does not add verdict history.
