"""SBIR awards → CapitalEvent builder.

Reads raw/sbir/award_data.csv (Title-Case headers). Match against cohort
is by normalized company name (UPPERCASE + strip).
"""

import csv
import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capital_events._common import normalize_date  # noqa: E402
from capital_events.schema import EventType  # noqa: E402


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
    try:
        return float(value) if value not in (None, "") else None
    except (ValueError, TypeError):
        return None


def build_sbir_award_events(
    cohort: Iterable[dict], source_path: Path
) -> Iterator[dict]:
    """Yield CapitalEvent rows for SBIR awards to cohort firms."""
    if not source_path.exists():
        return
    cohort_names = {row["company_name"] for row in cohort}
    with source_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_company = (row.get("Company") or "").strip()
            normalized = raw_company.upper()
            if normalized not in cohort_names:
                continue
            event_date = normalize_date(row.get("Proposal Award Date"))
            source_id = (row.get("Agency Tracking Number") or "").strip() \
                or (row.get("Contract") or "").strip()
            yield {
                "company_name": normalized,
                "event_date": event_date,
                "event_type": EventType.SBIR_AWARD.value,
                "event_subtype": classify_phase(row.get("Phase")),
                "amount_usd": _to_float(row.get("Award Amount")),
                "counterparty": (row.get("Agency") or "").strip() or None,
                "source_id": source_id,
                "metadata": json.dumps({
                    "branch": (row.get("Branch") or "").strip() or None,
                    "solicitation_number": (row.get("Solicitation Number") or "").strip() or None,
                    "solicitation_year": _to_int(row.get("Solicitation Year")),
                    "award_year": _to_int(row.get("Award Year")),
                    "city": (row.get("City") or "").strip() or None,
                    "state": (row.get("State") or "").strip() or None,
                }),
            }
