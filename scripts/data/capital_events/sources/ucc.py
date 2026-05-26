"""UCC matches → CapitalEvent builder.

Reads ucc1_pilot_matches.jsonl (produced by the UCC1 pilot's matcher).
If the file does not exist, yields nothing — UCC data is sparse and
optional in v1. Emits one event per matched filing.
"""

import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capital_events.schema import EventType  # noqa: E402


def build_ucc_events(
    cohort: Iterable[dict], source_path: Path
) -> Iterator[dict]:
    """Yield CapitalEvent rows for matched UCC filings against cohort firms."""
    if not source_path.exists():
        return
    cohort_names = {row["company_name"] for row in cohort}
    with source_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                match = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = match.get("cohort_company_name")
            if name not in cohort_names:
                continue
            filing = match.get("filing") or {}
            yield {
                "company_name": name,
                "event_date": filing.get("filing_date") or "",
                "event_type": EventType.UCC_FILING.value,
                "event_subtype": filing.get("filing_type"),
                "amount_usd": None,
                "counterparty": filing.get("secured_party_name"),
                "source_id": filing.get("filing_number") or "",
                "metadata": json.dumps({
                    "secured_party_address": filing.get("secured_party_address"),
                    "match_confidence": match.get("match_confidence"),
                    "match_score": match.get("match_score"),
                    "status_portal": filing.get("status_portal"),
                    "lapse_date": filing.get("lapse_date"),
                    "source_state": filing.get("source"),
                }),
            }
