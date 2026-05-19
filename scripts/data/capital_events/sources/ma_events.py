"""M&A events → CapitalEvent builder.

Reads enriched_sbir_ma_events.jsonl. Filters to high+medium confidence.
The file uses field name `confidence` (not `tier`).
"""

import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capital_events.schema import EventType  # noqa: E402

_KEEP_CONFIDENCES = {"high", "medium"}


def build_ma_events(
    cohort: Iterable[dict], source_path: Path
) -> Iterator[dict]:
    """Yield CapitalEvent rows for high+medium-confidence MA events."""
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
            event_date = rec.get("event_date") or ""
            yield {
                "company_name": name,
                "event_date": event_date,
                "event_type": EventType.MA_EVENT.value,
                "event_subtype": confidence,
                "amount_usd": None,
                "counterparty": rec.get("acquirer"),
                "source_id": f"{name}__{event_date}",
                "metadata": json.dumps({
                    "signals": rec.get("signals") or {},
                    "press_wire_signals": rec.get("press_wire_signals") or {},
                    "signal_count": rec.get("signal_count"),
                    "enriched": rec.get("enriched", False),
                }),
            }
