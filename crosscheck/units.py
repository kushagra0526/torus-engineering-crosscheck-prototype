"""Quantities with units -> canonical values (psig, degF, kW/kVA, m3/h, ft).

Gauge vs absolute matters: 115 psia is 100.3 psig, not 115.
"""

from __future__ import annotations

import re

ATM_PSI = 14.696
BAR_PSI = 14.5038

_NUM = r"(-?\d[\d,]*\.?\d*)"
_Q = re.compile(_NUM + r"\s*(" + "|".join([
    r"psi\s*\(?g\)?", r"psig", r"psi\s*\(?a\)?", r"psia", r"barg", r"bar\s*\(?g\)?", r"bara", r"bar\s*\(?a\)?",
    r"kg/cm2\s*\(?g\)?", r"kpa\s*\(?g\)?", r"kpag", r"kpa\s*\(?a\)?", r"kpaa", r"mpa\s*\(?g\)?", r"mpag",
    r"°\s*f", r"deg\s*f", r"°\s*c", r"deg\s*c", r"f\b", r"c\b",
    r"mva", r"kva", r"kw", r"hp", r"m3/h", r"m³/h", r"gpm", r"ft", r"m\b",
]) + r")", re.I)


def parse(text: str):
    """First quantity in `text` -> (value, kind, canonical_unit) or None."""
    m = _Q.search(text)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    u = re.sub(r"[\s()]", "", m.group(2).lower()).replace("°", "deg").replace("³", "3")
    table = {
        "psig": (lambda x: x, "pressure"), "psi": (lambda x: x, "pressure"),
        "psia": (lambda x: x - ATM_PSI, "pressure"),
        "barg": (lambda x: x * BAR_PSI, "pressure"), "bara": (lambda x: x * BAR_PSI - ATM_PSI, "pressure"),
        "kpag": (lambda x: x * BAR_PSI / 100, "pressure"), "kpaa": (lambda x: x * BAR_PSI / 100 - ATM_PSI, "pressure"),
        "mpag": (lambda x: x * BAR_PSI * 10, "pressure"),
        "kg/cm2g": (lambda x: x * 14.2233, "pressure"),
        "degf": (lambda x: x, "temp"), "f": (lambda x: x, "temp"),
        "degc": (lambda x: x * 9 / 5 + 32, "temp"), "c": (lambda x: x * 9 / 5 + 32, "temp"),
        "mva": (lambda x: x * 1000, "kva"), "kva": (lambda x: x, "kva"),
        "kw": (lambda x: x, "kw"), "hp": (lambda x: x * 0.7457, "kw"),
        "m3/h": (lambda x: x, "flow"), "gpm": (lambda x: x * 0.22712, "flow"),
        "ft": (lambda x: x, "head"), "m": (lambda x: x * 3.28084, "head"),
    }
    if u not in table:
        return None
    f, kind = table[u]
    return f(v), kind, u


def parse_naive(text: str):
    """What a literal checker does: convert units but ignore gauge/absolute."""
    q = parse(text)
    if q is None:
        return None
    v, kind, u = q
    if u in ("psia", "bara", "kpaa"):
        v += ATM_PSI
    return v, kind, u
