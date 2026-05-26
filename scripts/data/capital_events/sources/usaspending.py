"""USAspending Phase 3 contracts → CapitalEvent builder.

Reads processed/sbir_phase3/usaspending_phase3_contracts.jsonl. Matches
to cohort firms by normalized Recipient Name (uppercase + strip).
"""

import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capital_events._common import normalize_date  # noqa: E402
from capital_events.schema import EventType  # noqa: E402


def _naics_code(value) -> str | None:
    """Extract NAICS code. Real Phase 3 USAspending has NAICS as
    ``{"code": "541611", "description": "..."}``; tests use a bare string.
    Tolerate both shapes."""
    if isinstance(value, dict):
        code = value.get("code")
        return str(code).strip() if code else None
    if isinstance(value, str):
        return value.strip() or None
    return None


def _naics_description(value) -> str | None:
    """Extract NAICS description from the dict form; None for legacy strings."""
    if isinstance(value, dict):
        desc = value.get("description")
        return str(desc).strip() if desc else None
    return None


def build_usaspending_events(
    cohort: Iterable[dict], source_path: Path
) -> Iterator[dict]:
    """Yield CapitalEvent rows for Phase 3 USAspending contracts to cohort firms."""
    if not source_path.exists():
        return
    # {UPPERCASE: canonical} — case-insensitive match, canonical emission
    canonical_by_upper = {row["company_name"].upper(): row["company_name"] for row in cohort}
    with source_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                contract = json.loads(line)
            except json.JSONDecodeError:
                continue
            recipient_raw = (contract.get("Recipient Name") or "").strip()
            canonical = canonical_by_upper.get(recipient_raw.upper())
            if canonical is None:
                continue
            event_date = normalize_date(contract.get("Start Date"))
            award_id = (contract.get("Award ID") or "").strip()
            if award_id:
                source_id = award_id
            else:
                source_id = (contract.get("generated_internal_id") or "").strip() or "GEN-"
            yield {
                "company_name": canonical,
                "event_date": event_date,
                "event_type": EventType.USASPENDING_CONTRACT.value,
                "event_subtype": None,
                "amount_usd": float(contract.get("Award Amount") or 0) or None,
                "counterparty": (contract.get("Funding Agency") or "").strip() or None,
                "source_id": source_id,
                "metadata": json.dumps({
                    "funding_sub_agency": (contract.get("Funding Sub Agency") or "").strip() or None,
                    "awarding_agency": (contract.get("Awarding Agency") or "").strip() or None,
                    "awarding_sub_agency": (contract.get("Awarding Sub Agency") or "").strip() or None,
                    "naics": _naics_code(contract.get("NAICS")),
                    "naics_description": _naics_description(contract.get("NAICS")),
                    "description": (contract.get("Description") or "").strip() or None,
                    "end_date": normalize_date(contract.get("End Date")) or None,
                    "agency_slug": contract.get("agency_slug"),
                    "generated_internal_id": contract.get("generated_internal_id"),
                }),
            }
