"""Canonical APEC economy-code helpers used by portable workflows."""

from __future__ import annotations

import re


_ALIASES = {
    "01_AUS": ("aus", "australia"),
    "02_BD": ("bd", "brunei", "brunei darussalam"),
    "03_CDA": ("cda", "canada"),
    "04_CHL": ("chl", "chile"),
    "05_PRC": ("prc", "china", "people's republic of china"),
    "06_HKC": ("hkc", "hong kong", "hong kong china", "hong kong, china"),
    "07_INA": ("ina", "indonesia"),
    "08_JPN": ("jpn", "japan"),
    "09_ROK": ("rok", "korea", "republic of korea", "south korea"),
    "10_MAS": ("mas", "malaysia"),
    "11_MEX": ("mex", "mexico"),
    "12_NZ": ("nz", "new zealand"),
    "13_PNG": ("png", "papua new guinea"),
    "14_PE": ("pe", "peru"),
    "15_PHL": ("phl", "philippines", "the philippines"),
    "16_RUS": ("rus", "russia", "russian federation"),
    "17_SGP": ("sgp", "singapore"),
    "18_CT": ("ct", "chinese taipei"),
    "19_THA": ("tha", "thailand"),
    "20_USA": ("usa", "united states", "united states of america"),
    "21_VN": ("vn", "vietnam", "viet nam"),
}

ECONOMY_CODE_ALIASES = {
    "03_CNA": "03_CDA",
    "17_SIN": "17_SGP",
    "15_RP": "15_PHL",
}

_ALIAS_TO_CODE = {alias.casefold(): code for code, aliases in _ALIASES.items() for alias in (code, *aliases)}
_ATTACHED_CODE = re.compile(r"^(?P<number>\d{2})[_\s-]*(?P<letters>[A-Za-z]{2,3})$")


def canonicalize_economy_code(value: object) -> str:
    """Return a recognised economy in ``NN_CODE`` form."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none"}:
        return ""
    normalized = re.sub(r"\s+", " ", text).strip()
    if compact_match := _ATTACHED_CODE.fullmatch(normalized):
        normalized = f"{compact_match.group('number')}_{compact_match.group('letters').upper()}"
    normalized = ECONOMY_CODE_ALIASES.get(normalized.upper(), normalized)
    if known := _ALIAS_TO_CODE.get(normalized.casefold()):
        return known
    return re.sub(r"[\s-]+", "_", normalized).upper()


__all__ = ["ECONOMY_CODE_ALIASES", "canonicalize_economy_code"]
