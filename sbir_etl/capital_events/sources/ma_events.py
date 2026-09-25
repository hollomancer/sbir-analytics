"""M&A candidates → CapitalEvent builder.

Reads enriched_sbir_ma_events.jsonl. Filters to high+medium confidence.
The file uses field name `confidence` (not `tier`).
"""

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from sbir_etl.capital_events.schema import EventType

_KEEP_CONFIDENCES = {"high", "medium"}


def build_ma_events(cohort: Iterable[dict], source_path: Path) -> Iterator[dict]:
    """Yield CapitalEvent rows for high+medium-confidence M&A candidates."""
    if not source_path.exists():
        return
    cohort_names = {row["company_name"] for row in cohort}
    with source_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = rec.get("company_name")
            if name not in cohort_names:
                continue
            confidence = rec.get("confidence")
            if confidence not in _KEEP_CONFIDENCES:
                continue
            acquirer = rec.get("acquirer")
            if not acquirer:
                # A row with no acquirer cannot support an exit claim; a consumer
                # cannot distinguish unknown-acquirer from firm-was-the-buyer.
                continue
            event_date = rec.get("event_date") or ""
            yield {
                "company_name": name,
                "event_date": event_date,
                "event_type": EventType.MA_EVENT.value,
                "event_subtype": confidence,
                "amount_usd": None,
                "counterparty": acquirer,
                "source_id": f"{name}__{event_date}",
                "metadata": json.dumps(
                    {
                        "signals": rec.get("signals") or {},
                        # Recomputed from signals, not forwarded: legacy rows
                        # carry a stored count that includes a removed source.
                        "signal_count": sum(
                            1 for value in (rec.get("signals") or {}).values() if value is True
                        ),
                        "candidate_status": (rec.get("cross_enrichment") or {}).get(
                            "candidate_status", "unvalidated_public_record_candidate"
                        ),
                        "legal_event_validated": (rec.get("cross_enrichment") or {}).get(
                            "legal_event_validated", False
                        ),
                        "cross_enrichment": rec.get("cross_enrichment") or {},
                    }
                ),
            }
