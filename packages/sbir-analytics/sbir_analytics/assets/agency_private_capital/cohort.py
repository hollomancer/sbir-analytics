"""SBIR cohort builder (agency-parameterized).

Filters the SBIR award universe to entries for a configured funding agency
(default: NSF) and stratifies by 5-year vintage bucket plus phase. The
agency match uses normalized substring comparison so variants like
``"NSF"``, ``"National Science Foundation"``, and
``"National Science Foundation (NSF)"`` all resolve to the ``"NSF"`` agency
code. When an explicit ALN/CFDA column is present it is checked first
against the agency's known ALN set; the agency-name column acts as a
fallback when ALN is absent.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from sbir_etl.models.sbir_identification import SBIR_ASSISTANCE_LISTING_NUMBERS


# Map agency_code -> frozenset of ALN strings. Pre-populated for NSF; other
# agencies will fall back to name-only matching when absent.
AGENCY_ALN_MAP: dict[str, frozenset[str]] = {
    agency: frozenset(info["alns"]) for agency, info in SBIR_ASSISTANCE_LISTING_NUMBERS.items()
}

# Back-compat alias — still the NSF ALNs, just accessed via the map.
NSF_ALNS: frozenset[str] = AGENCY_ALN_MAP["NSF"]

# Map agency_code -> extra name tokens that identify the agency when the
# abbreviation alone doesn't appear in the agency column. Matching is
# normalized substring: the agency column value (lowercased + stripped)
# must contain any one of these tokens, or the agency_code itself.
_AGENCY_NAME_TOKENS: dict[str, frozenset[str]] = {
    "NSF": frozenset({"nsf", "national science foundation"}),
    "NIH": frozenset({"nih", "national institutes of health"}),
    "DOD": frozenset({"dod", "department of defense"}),
    "DOE": frozenset({"doe", "department of energy"}),
    "NASA": frozenset({"nasa", "national aeronautics"}),
    "EPA": frozenset({"epa", "environmental protection agency"}),
    "USDA": frozenset({"usda", "department of agriculture"}),
    "HHS": frozenset({"hhs", "health and human services"}),
}

DEFAULT_VINTAGE_BUCKET_SIZE = 5


def vintage_bucket(year: int, *, size: int = DEFAULT_VINTAGE_BUCKET_SIZE) -> str:
    """Map a calendar year to its 5-year vintage label, e.g. 2017 -> ``2015-2019``."""

    if year is None or pd.isna(year):
        raise ValueError("year is required")
    y = int(year)
    start = (y // size) * size
    return f"{start}-{start + size - 1}"


def _normalize_phase(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip().upper()
    if s.startswith("PHASE "):
        s = s[len("PHASE ") :].strip()
    if s in {"I", "1"}:
        return "I"
    if s in {"II", "2"}:
        return "II"
    if s in {"III", "3"}:
        return "III"
    return None


def _is_agency_row(row: pd.Series, agency_code: str = "NSF") -> bool:
    """Return True if ``row`` belongs to the given agency.

    Matching strategy (in priority order):
    1. If the row has an explicit ALN/CFDA number and that number is in the
       agency's known ALN set, accept it.
    2. Normalize the row's ``agency`` column value (lowercase + strip), then
       check whether any of the agency's known name tokens is a substring of
       that value. Tokens include both the abbreviation (e.g. ``"nsf"``) and
       the full name (e.g. ``"national science foundation"``), so all of
       ``"NSF"``, ``"National Science Foundation"``, and
       ``"National Science Foundation (NSF)"`` match agency_code ``"NSF"``.

    For agency codes not in ``_AGENCY_NAME_TOKENS``, falls back to checking
    whether the lowercased agency_code itself appears as a substring.
    """

    code_upper = agency_code.strip().upper()
    alns = AGENCY_ALN_MAP.get(code_upper, frozenset())

    cfda = row.get("cfda_number") or row.get("aln") or row.get("assistance_listing_number")
    if cfda and str(cfda).strip() in alns:
        return True

    agency = row.get("agency")
    if agency is None or (isinstance(agency, float) and pd.isna(agency)):
        return False

    agency_lower = str(agency).strip().lower()
    tokens = _AGENCY_NAME_TOKENS.get(code_upper, frozenset({agency_code.strip().lower()}))
    return any(token in agency_lower for token in tokens)


def _award_year(row: pd.Series) -> int | None:
    for key in ("award_year", "Award Year"):
        v = row.get(key)
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            try:
                return int(str(v).strip())
            except (TypeError, ValueError):
                pass
    for key in ("award_date", "Proposal Award Date"):
        v = row.get(key)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        ts = pd.to_datetime(v, errors="coerce")
        if pd.notna(ts):
            return int(ts.year)
    return None


@dataclass(frozen=True)
class AgencyCohortBuilder:
    """Filter to a funding agency's SBIR/STTR awards and stratify by vintage + phase.

    ``build`` returns a copy of the input frame restricted to rows matching
    ``agency_code`` with two new columns: ``vintage_bucket`` (5-year label)
    and ``phase_label`` (``"I"`` | ``"II"`` | ``"III"``).

    Args:
        agency_code: The agency to filter to. Default ``"NSF"`` preserves
            existing behavior. Match is normalized substring on the agency
            name column and exact on ALN when present.
        vintage_size: Width of vintage buckets in years. Default 5.
    """

    agency_code: str = "NSF"
    vintage_size: int = DEFAULT_VINTAGE_BUCKET_SIZE

    def build(self, awards: pd.DataFrame) -> pd.DataFrame:
        if awards.empty:
            return awards.assign(
                vintage_bucket=pd.Series(dtype="object"), phase_label=pd.Series(dtype="object")
            )
        mask = awards.apply(_is_agency_row, axis=1, agency_code=self.agency_code)
        cohort = awards[mask].copy()
        if cohort.empty:
            cohort["vintage_bucket"] = pd.Series(dtype="object")
            cohort["phase_label"] = pd.Series(dtype="object")
            return cohort
        years = cohort.apply(_award_year, axis=1)
        cohort["vintage_bucket"] = years.map(
            lambda y: vintage_bucket(y, size=self.vintage_size) if y is not None else None
        )
        phase_src = cohort.get("phase", cohort.get("Phase"))
        cohort["phase_label"] = phase_src.map(_normalize_phase) if phase_src is not None else None
        return cohort

    @staticmethod
    def stratum_counts(cohort: pd.DataFrame) -> pd.DataFrame:
        """Return per-stratum row counts: (vintage_bucket, phase_label) -> n."""

        if cohort.empty:
            return pd.DataFrame(columns=["vintage_bucket", "phase_label", "n"])
        grouped = (
            cohort.groupby(["vintage_bucket", "phase_label"], dropna=False)
            .size()
            .reset_index(name="n")
        )
        return grouped.sort_values(["vintage_bucket", "phase_label"]).reset_index(drop=True)


# Back-compat alias: existing code that instantiated NSFCohortBuilder() still works.
class NSFCohortBuilder(AgencyCohortBuilder):
    """NSF-specific cohort builder. Preserved for backward compatibility."""

    def __init__(self, vintage_size: int = DEFAULT_VINTAGE_BUCKET_SIZE) -> None:
        # Use object.__setattr__ because the parent is frozen=True
        object.__setattr__(self, "agency_code", "NSF")
        object.__setattr__(self, "vintage_size", vintage_size)
