"""Patent grants → CapitalEvent builder.

Reads the newest patents_*.jsonl file in transformed/uspto/. Match to
cohort uses the patent record's pre-computed `linked_companies` list.
One event per (patent, cohort-firm-link) pair.
"""

import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capital_events._common import normalize_date  # noqa: E402
from capital_events.schema import EventType  # noqa: E402


def newest_patent_file(directory: Path) -> Path | None:
    """Return the newest patents_*.jsonl file in a directory, by mtime."""
    if not directory.exists():
        return None
    candidates = list(directory.glob("patents_*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def build_patent_events(
    cohort: Iterable[dict], source_path: Path
) -> Iterator[dict]:
    """Yield CapitalEvent rows for patent grants linked to cohort firms."""
    if source_path is None:
        return
    if source_path.is_dir():
        resolved = newest_patent_file(source_path)
        if resolved is None:
            return
        source_path = resolved
    if not source_path.exists():
        return
    cohort_names = {row["company_name"] for row in cohort}
    with source_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                patent = json.loads(line)
            except json.JSONDecodeError:
                continue
            linked = patent.get("linked_companies") or []
            for linked_name in linked:
                if linked_name not in cohort_names:
                    continue
                yield {
                    "company_name": linked_name,
                    "event_date": normalize_date(patent.get("latest_recorded_date")),
                    "event_type": EventType.PATENT_GRANT.value,
                    "event_subtype": None,
                    "amount_usd": None,
                    "counterparty": None,
                    "source_id": str(patent.get("grant_number") or ""),
                    "metadata": json.dumps({
                        "title": patent.get("title"),
                        "language": patent.get("language"),
                        "assignee_names": patent.get("assignee_names") or [],
                        "assignor_names": patent.get("assignor_names") or [],
                        "assignment_count": patent.get("assignment_count"),
                    }),
                }
