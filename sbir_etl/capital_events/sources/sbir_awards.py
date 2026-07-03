"""SBIR awards → CapitalEvent builder.

Reads raw/sbir/award_data.csv (Title-Case headers). Match against cohort
is by normalized company name (UPPERCASE + strip).
"""

import csv
import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from sbir_etl.capital_events._common import normalize_date
from sbir_etl.capital_events.schema import EventType


def classify_phase(phase: str | None) -> str:
    """Project the SBIR Phase column to a stable subtype label."""
    if not phase:
        return "sbir_phase_unknown"
    upper = phase.upper()
    if "III" in upper:
        return "sbir_phase_iii"
    if "II" in upper:
        return "sbir_phase_ii"
    if "I" in upper:
        return "sbir_phase_i"
    return "sbir_phase_unknown"


def _to_int(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _to_float(value) -> float | None:
    """Parse a number, tolerating `$` / comma formatting that may appear in
    SBIR award amounts (matches sbir_etl/ucc/export_cohort.py pattern)."""
    if value in (None, ""):
        return None
    s = str(value).replace(",", "").replace("$", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def build_sbir_award_events(cohort: Iterable[dict], source_path: Path) -> Iterator[dict]:
    """Yield CapitalEvent rows for SBIR awards to cohort firms."""
    if not source_path.exists():
        return
    # Build {UPPERCASE: canonical} so we can match case-insensitively but
    # emit the cohort's canonical name (preserves case used downstream).
    canonical_by_upper = {row["company_name"].upper(): row["company_name"] for row in cohort}
    with source_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_company = (row.get("Company") or "").strip()
            canonical = canonical_by_upper.get(raw_company.upper())
            if canonical is None:
                continue
            # Date resolution: prefer Proposal Award Date; fall back to
            # Award Year (with a Jan-1 placeholder day) when the explicit
            # date is missing. ~21% of real SBIR rows lack Proposal Award
            # Date but have Award Year. Document the fallback in metadata.
            raw_date = row.get("Proposal Award Date")
            event_date = normalize_date(raw_date)
            date_source = "proposal_award_date"
            if not event_date:
                award_year = _to_int(row.get("Award Year"))
                if award_year and 1900 <= award_year <= 2100:
                    event_date = f"{award_year}-01-01"
                    date_source = "award_year_fallback"
            if not event_date:
                # No usable date; skip rather than emit an empty-date event
                # that breaks chronological ordering.
                continue
            source_id = (row.get("Agency Tracking Number") or "").strip() or (
                row.get("Contract") or ""
            ).strip()
            yield {
                "company_name": canonical,
                "event_date": event_date,
                "event_type": EventType.SBIR_AWARD.value,
                "event_subtype": classify_phase(row.get("Phase")),
                "amount_usd": _to_float(row.get("Award Amount")),
                "counterparty": (row.get("Agency") or "").strip() or None,
                "source_id": source_id,
                "metadata": json.dumps(
                    {
                        "branch": (row.get("Branch") or "").strip() or None,
                        "solicitation_number": (row.get("Solicitation Number") or "").strip()
                        or None,
                        "solicitation_year": _to_int(row.get("Solicitation Year")),
                        "award_year": _to_int(row.get("Award Year")),
                        "city": (row.get("City") or "").strip() or None,
                        "state": (row.get("State") or "").strip() or None,
                        "date_source": date_source,
                    }
                ),
            }
