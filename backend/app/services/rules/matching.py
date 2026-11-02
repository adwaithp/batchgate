"""Match result rows on a COA ("Fe content (as Fe)") to spec parameters ("Iron (as Fe)")."""

import re
from difflib import SequenceMatcher

from app.services.rules.types import ParamSpec, ResultInput

_SPELLING = {"sulphated": "sulfated", "sulphate": "sulfate", "sulphur": "sulfur", "colour": "color"}


def normalize_name(name: str) -> str:
    s = name.lower()
    for uk, us in _SPELLING.items():
        s = s.replace(uk, us)
    s = re.sub(r"@.*$", "", s)  # "Specific gravity @ 25 °C" -> "specific gravity"
    s = re.sub(r"[^a-z0-9()+ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _keys(name: str) -> set[str]:
    full = normalize_name(name)
    keys = {full.replace("(", "").replace(")", "").strip()}
    without_parens = re.sub(r"\(.*?\)", "", full).strip()
    if without_parens:
        keys.add(re.sub(r"\s+", " ", without_parens))
    return {k for k in keys if k}


def _param_keys(p: ParamSpec) -> set[str]:
    keys: set[str] = set()
    for n in [p.name, *p.aliases]:
        keys |= _keys(n)
    return keys


FUZZY_THRESHOLD = 0.88


def match_results(
    params: list[ParamSpec], results: list[ResultInput]
) -> tuple[dict[int, ResultInput], list[ResultInput]]:
    """Return {parameter_id: result} and the results that matched nothing.

    Order of trust: an explicit parameter_id, then exact name/alias keys, then a fuzzy match
    only when it is clearly the single best candidate. Ambiguous rows stay unmatched so a
    person decides, instead of the engine guessing.
    """
    by_id = {p.id: p for p in params}
    keys = {p.id: _param_keys(p) for p in params}
    matched: dict[int, ResultInput] = {}
    unmatched: list[ResultInput] = []

    def claim(pid: int, r: ResultInput) -> None:
        if pid in matched:
            unmatched.append(r)  # duplicate row for the same test: keep the first
        else:
            matched[pid] = r

    pending: list[ResultInput] = []
    for r in results:
        if r.parameter_id is not None and r.parameter_id in by_id:
            claim(r.parameter_id, r)
        else:
            pending.append(r)

    for r in pending:
        rkeys = _keys(r.name_as_written)
        exact = [pid for pid, pk in keys.items() if rkeys & pk]
        if len(exact) == 1:
            claim(exact[0], r)
            continue
        if len(exact) > 1:
            unmatched.append(r)
            continue

        target = normalize_name(r.name_as_written)
        scored = sorted(
            (
                (max(SequenceMatcher(None, target, k).ratio() for k in pk), pid)
                for pid, pk in keys.items()
            ),
            reverse=True,
        )
        if scored and scored[0][0] >= FUZZY_THRESHOLD:
            runner_up = scored[1][0] if len(scored) > 1 else 0.0
            if scored[0][0] - runner_up >= 0.05:
                claim(scored[0][1], r)
                continue
        unmatched.append(r)

    return matched, unmatched
