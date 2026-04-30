"""NSF SBIR cohort builder.

Filters the SBIR award universe to NSF entries (ALN ``47.041`` / ``47.084``,
which are NSF-exclusive per ``sbir_etl.models.sbir_identification``) and
stratifies by 5-year vintage bucket plus phase. The agency-name column is
used as the primary filter when an explicit ALN/CFDA column is unavailable
on SBIR.gov source records — both routes produce the same NSF-only slice
because the relevant ALNs are exclusive.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from sbir_etl.models.sbir_identification import SBIR_ASSISTANCE_LISTING_NUMBERS, is_sbir_grant


NSF_ALNS: frozenset[str] = frozenset(SBIR_ASSISTANCE_LISTING_NUMBERS["NSF"]["alns"])

NSF_AGENCY_TOKENS: frozenset[str] = frozenset(
    {
        "nsf",
        "national science foundation",
    }
)

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


def _is_nsf_row(row: pd.Series) -> bool:
    cfda = row.get("cfda_number") or row.get("aln") or row.get("assistance_listing_number")
    if cfda and str(cfda).strip() in NSF_ALNS:
        return True
    if cfda and is_sbir_grant(str(cfda).strip(), strict=True) and str(cfda).strip() in NSF_ALNS:
        return True
    agency = row.get("agency")
    if agency is None or (isinstance(agency, float) and pd.isna(agency)):
        return False
    return str(agency).strip().lower() in NSF_AGENCY_TOKENS


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
class NSFCohortBuilder:
    """Filter to NSF SBIR/STTR awards and stratify by vintage + phase.

    ``build`` returns a copy of the input frame restricted to NSF rows with
    two new columns: ``vintage_bucket`` (5-year label) and ``phase_label``
    (``"I"`` | ``"II"`` | ``"III"``).
    """

    vintage_size: int = DEFAULT_VINTAGE_BUCKET_SIZE

    def build(self, awards: pd.DataFrame) -> pd.DataFrame:
        if awards.empty:
            return awards.assign(
                vintage_bucket=pd.Series(dtype="object"), phase_label=pd.Series(dtype="object")
            )
        mask = awards.apply(_is_nsf_row, axis=1)
        nsf = awards[mask].copy()
        if nsf.empty:
            nsf["vintage_bucket"] = pd.Series(dtype="object")
            nsf["phase_label"] = pd.Series(dtype="object")
            return nsf
        years = nsf.apply(_award_year, axis=1)
        nsf["vintage_bucket"] = years.map(
            lambda y: vintage_bucket(y, size=self.vintage_size) if y is not None else None
        )
        phase_src = nsf.get("phase", nsf.get("Phase"))
        nsf["phase_label"] = phase_src.map(_normalize_phase) if phase_src is not None else None
        return nsf

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
