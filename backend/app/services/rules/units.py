"""Unit normalisation and conversion. Pure code: exact, and never guessed by the model."""

import re

# Canonical unit -> spellings seen on real COAs.
_ALIASES: dict[str, tuple[str, ...]] = {
    "%": (
        "%",
        "% w/w",
        "%w/w",
        "% (w/w)",
        "wt%",
        "wt %",
        "% wt",
        "%wt",
        "percent",
        "% m/m",
        "%m/m",
    ),
    "% w/v": ("% w/v", "%w/v", "% (w/v)", "w/v %"),
    "ppm": ("ppm", "mg/kg", "mg / kg", "µg/g", "μg/g", "ug/g", "mcg/g", "parts per million"),
    "ppb": ("ppb", "µg/kg", "μg/kg", "ug/kg"),
    "°C": ("°c", "° c", "deg c", "degc", "deg. c", "celsius", "ºc", "c"),
    "g/mL": ("g/ml", "g/cm3", "g/cm³", "g/cc", "kg/l"),
    "mPa·s": ("mpa·s", "mpa.s", "mpas", "mpa s", "cp", "cps", "centipoise"),
}

_LOOKUP = {spelling: canon for canon, spellings in _ALIASES.items() for spelling in spellings}

# Dimensionless parameters (pH, specific gravity) are written with no unit or a dash.
_DIMENSIONLESS = {"", "-", "–", "—", "n/a", "na", "none", "unitless"}

# Factors to a base unit, per family. Only units in the same family can be converted.
_FACTORS: dict[str, tuple[str, float]] = {
    "%": ("mass_fraction", 1e4),  # 1 % = 10,000 ppm
    "ppm": ("mass_fraction", 1.0),
    "ppb": ("mass_fraction", 1e-3),
}


def normalize_unit(unit: str | None) -> str | None:
    """Map a unit as printed to its canonical form. None means dimensionless.

    Unknown spellings are returned trimmed but unchanged, so they can still be compared
    exactly and shown to a human.
    """
    if unit is None:
        return None
    cleaned = re.sub(r"\s+", " ", unit.strip().lower())
    if cleaned in _DIMENSIONLESS:
        return None
    return _LOOKUP.get(cleaned, unit.strip())


class UnitMismatch(ValueError):
    pass


def convert(value: float, from_unit: str | None, to_unit: str | None) -> float:
    """Convert between canonical units. Raises UnitMismatch when there is no exact conversion."""
    src, dst = normalize_unit(from_unit), normalize_unit(to_unit)
    if src == dst:
        return value
    if src in _FACTORS and dst in _FACTORS:
        src_family, src_factor = _FACTORS[src]
        dst_family, dst_factor = _FACTORS[dst]
        if src_family == dst_family:
            return value * src_factor / dst_factor
    raise UnitMismatch(f"cannot convert {from_unit or 'no unit'} to {to_unit or 'no unit'}")


def format_unit(unit: str | None) -> str:
    return f" {unit}" if unit else ""
