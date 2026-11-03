"""Unit normalisation and exact conversion."""

import re

# Canonical unit -> spellings seen on COAs.
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

# Spellings meaning no unit.
_DIMENSIONLESS = {"", "-", "–", "—", "n/a", "na", "none", "unitless"}

# Conversion factors to a base unit, per family.
_FACTORS: dict[str, tuple[str, float]] = {
    "%": ("mass_fraction", 1e4),  # 1 % = 10,000 ppm
    "ppm": ("mass_fraction", 1.0),
    "ppb": ("mass_fraction", 1e-3),
}


def normalize_unit(unit: str | None) -> str | None:
    """Return the canonical unit, None for dimensionless, else the input trimmed."""
    if unit is None:
        return None
    cleaned = re.sub(r"\s+", " ", unit.strip().lower())
    if cleaned in _DIMENSIONLESS:
        return None
    return _LOOKUP.get(cleaned, unit.strip())


class UnitMismatchError(ValueError):
    """The units cannot be converted exactly."""


def convert(value: float, from_unit: str | None, to_unit: str | None) -> float:
    """Convert a value between canonical units."""
    src, dst = normalize_unit(from_unit), normalize_unit(to_unit)
    if src == dst:
        return value
    if src in _FACTORS and dst in _FACTORS:
        src_family, src_factor = _FACTORS[src]
        dst_family, dst_factor = _FACTORS[dst]
        if src_family == dst_family:
            return value * src_factor / dst_factor
    raise UnitMismatchError(f"cannot convert {from_unit or 'no unit'} to {to_unit or 'no unit'}")


def format_unit(unit: str | None) -> str:
    """Return " unit" for display, or an empty string."""
    return f" {unit}" if unit else ""
