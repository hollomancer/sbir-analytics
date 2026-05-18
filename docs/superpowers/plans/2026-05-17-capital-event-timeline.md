# Capital-Event Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce two parquet artifacts (`capital_events.parquet` long-format event stream + `capital_events_per_firm.parquet` wide-format per-firm summary) for the Form D high-confidence SBIR cohort (~3,639 firms), drawing from SBIR awards, Form D filings, enriched M&A events, USAspending Phase 3 contracts, patent grants, and UCC matches.

**Architecture:** Standalone Python script under `scripts/data/`. Per-source builders are pure functions producing `Iterator[CapitalEvent]`. Orchestrator concatenates, sorts, and writes parquet. No Dagster wiring in v1 (promotion is a follow-on per spec).

**Tech Stack:** Python 3.11; pyarrow (already a base dep); pandas (already a base dep); pytest; `sbir_etl.enrichers.matching` for name normalization (reused from UCC1).

**Spec:** [docs/superpowers/specs/2026-05-17-capital-event-timeline-design.md](../specs/2026-05-17-capital-event-timeline-design.md)

---

## File Structure

**Create:**

```
scripts/data/
  build_capital_events.py                 # orchestrator + CLI entry
  capital_events/
    __init__.py
    _common.py                            # data path helper + date normalizers
    schema.py                             # CapitalEvent TypedDict + EventType StrEnum
    summarize.py                          # per-firm wide-format aggregator
    sources/
      __init__.py
      sbir_awards.py
      form_d.py
      ma_events.py
      usaspending.py
      patents.py
      ucc.py

tests/unit/scripts/capital_events/
  __init__.py
  conftest.py                             # shared cohort fixture
  test_common.py
  test_schema.py
  test_sbir_awards.py
  test_form_d.py
  test_ma_events.py
  test_usaspending.py
  test_patents.py
  test_ucc.py
  test_summarize.py
  test_orchestrator.py
```

**Data artifacts produced (written to `$SBIR_DATA_DIR`, gitignored):**

```
capital_events.parquet            # long-format, one row per event
capital_events_per_firm.parquet   # wide-format, one row per cohort firm
capital_events_sample.jsonl       # first 100 events for human inspection
```

**Real source files** (discovered during context exploration; confirmed paths):

| Source | Path under `$SBIR_DATA_DIR` |
|---|---|
| Cohort | `form_d_high_conf_cohort.jsonl` (produced by `scripts/data/ucc/export_cohort.py`) |
| SBIR awards | `raw/sbir/award_data.csv` |
| Form D | `form_d_details.jsonl` |
| MA events | `enriched_sbir_ma_events.jsonl` |
| USAspending Phase 3 | `processed/sbir_phase3/usaspending_phase3_contracts.jsonl` |
| Patents | `transformed/uspto/patents_*.jsonl` (pick newest by mtime — currently small/sample-only, builder must tolerate empty data) |
| UCC matches | `ucc1_pilot_matches.jsonl` (does not exist today; builder emits empty if missing) |

---

## Phase A: Foundations

### Task A1: Cross-source data path helper + date normalizers

**Files:**
- Create: `scripts/data/capital_events/__init__.py` (empty)
- Create: `scripts/data/capital_events/sources/__init__.py` (empty)
- Create: `scripts/data/capital_events/_common.py`
- Create: `tests/unit/scripts/capital_events/__init__.py` (empty)
- Create: `tests/unit/scripts/capital_events/test_common.py`

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p scripts/data/capital_events/sources tests/unit/scripts/capital_events
touch scripts/data/capital_events/__init__.py
touch scripts/data/capital_events/sources/__init__.py
touch tests/unit/scripts/capital_events/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/scripts/capital_events/test_common.py
"""Tests for capital_events common helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events._common import data_dir, data_path, normalize_date  # noqa: E402


def test_data_dir_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("SBIR_DATA_DIR", raising=False)
    assert data_dir() == Path("/Users/hollomancer/projects/sbir-analytics/data")


def test_data_dir_uses_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path


def test_data_path_joins_filename(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))
    assert data_path("foo.jsonl") == tmp_path / "foo.jsonl"


def test_normalize_date_iso_passthrough():
    assert normalize_date("2024-03-15") == "2024-03-15"


def test_normalize_date_mm_dd_yyyy_slashes():
    assert normalize_date("03/15/2024") == "2024-03-15"


def test_normalize_date_iso_with_time():
    assert normalize_date("2024-03-15T10:30:00") == "2024-03-15"


def test_normalize_date_iso_with_zulu():
    assert normalize_date("2024-03-15T10:30:00Z") == "2024-03-15"


def test_normalize_date_empty_returns_empty():
    assert normalize_date("") == ""
    assert normalize_date(None) == ""


def test_normalize_date_invalid_returns_empty():
    assert normalize_date("not-a-date") == ""
    assert normalize_date("13/45/2024") == ""  # invalid date components
```

- [ ] **Step 3: Run test to verify failure**

Run: `pytest tests/unit/scripts/capital_events/test_common.py -v`
Expected: `ImportError` — `capital_events._common` does not exist yet.

- [ ] **Step 4: Write `_common.py`**

```python
# scripts/data/capital_events/_common.py
"""Cross-source helpers for the capital-event timeline builder."""

import os
import re
from datetime import datetime
from pathlib import Path

DEFAULT_DATA_DIR = Path("/Users/hollomancer/projects/sbir-analytics/data")


def data_dir() -> Path:
    """Return the resolved data directory, honoring SBIR_DATA_DIR."""
    override = os.environ.get("SBIR_DATA_DIR")
    return Path(override) if override else DEFAULT_DATA_DIR


def data_path(relative_name: str) -> Path:
    """Return the absolute path for a data file by relative name."""
    p = Path(relative_name)
    if p.is_absolute():
        raise ValueError(f"data_path arg must be relative, got {relative_name}")
    return data_dir() / p


def normalize_date(value: str | None) -> str:
    """Convert various date representations to ISO YYYY-MM-DD.

    Accepts ISO with or without time component, MM/DD/YYYY slash format.
    Returns empty string for None, empty, or unparseable input.
    """
    if not value:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    # Strip trailing time component
    if "T" in s:
        s = s.split("T", 1)[0]
    elif " " in s:
        s = s.split(" ", 1)[0]
    # Try ISO first
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            datetime.strptime(s, "%Y-%m-%d")
            return s
        except ValueError:
            return ""
    # Try MM/DD/YYYY
    if "/" in s:
        try:
            return datetime.strptime(s, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""
```

- [ ] **Step 5: Run test to verify pass**

Run: `pytest tests/unit/scripts/capital_events/test_common.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/data/capital_events/__init__.py scripts/data/capital_events/sources/__init__.py scripts/data/capital_events/_common.py tests/unit/scripts/capital_events/__init__.py tests/unit/scripts/capital_events/test_common.py
git commit -m "feat(capital-events): add data path helper and date normalizer"
```

### Task A2: Schema (CapitalEvent TypedDict + EventType StrEnum)

**Files:**
- Create: `scripts/data/capital_events/schema.py`
- Create: `tests/unit/scripts/capital_events/test_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scripts/capital_events/test_schema.py
"""Schema sanity tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.schema import (  # noqa: E402
    EVENT_TABLE_COLUMNS,
    CapitalEvent,
    EventType,
)


def test_event_type_values():
    assert EventType.SBIR_AWARD.value == "sbir_award"
    assert EventType.FORM_D_FILING.value == "form_d_filing"
    assert EventType.MA_EVENT.value == "ma_event"
    assert EventType.USASPENDING_CONTRACT.value == "usaspending_contract"
    assert EventType.PATENT_GRANT.value == "patent_grant"
    assert EventType.UCC_FILING.value == "ucc_filing"


def test_event_table_columns_match_typeddict():
    expected = {
        "company_name", "event_date", "event_type", "event_subtype",
        "amount_usd", "counterparty", "source_id", "metadata",
    }
    assert set(EVENT_TABLE_COLUMNS) == expected
    # Ordered correctly
    assert EVENT_TABLE_COLUMNS[0] == "company_name"
    assert EVENT_TABLE_COLUMNS[1] == "event_date"
    assert EVENT_TABLE_COLUMNS[2] == "event_type"


def test_capital_event_can_round_trip_as_json():
    import json
    row: CapitalEvent = {
        "company_name": "Acme Inc",
        "event_date": "2024-03-15",
        "event_type": EventType.SBIR_AWARD.value,
        "event_subtype": "sbir_phase_ii",
        "amount_usd": 750000.0,
        "counterparty": "Department of Defense",
        "source_id": "DE-AR0001984",
        "metadata": json.dumps({"branch": "Army", "solicitation_year": 2024}),
    }
    parsed = json.loads(json.dumps(row))
    assert parsed["amount_usd"] == 750000.0
    assert parsed["event_type"] == "sbir_award"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/scripts/capital_events/test_schema.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Write `schema.py`**

```python
# scripts/data/capital_events/schema.py
"""Shared schema for capital-event timeline records."""

from enum import StrEnum
from typing import TypedDict


class EventType(StrEnum):
    SBIR_AWARD = "sbir_award"
    FORM_D_FILING = "form_d_filing"
    MA_EVENT = "ma_event"
    USASPENDING_CONTRACT = "usaspending_contract"
    PATENT_GRANT = "patent_grant"
    UCC_FILING = "ucc_filing"


class CapitalEvent(TypedDict):
    """One capital event for one firm, projected to the common schema."""

    company_name: str               # cohort key
    event_date: str                 # ISO YYYY-MM-DD
    event_type: str                 # EventType.value
    event_subtype: str | None       # per-type qualifier
    amount_usd: float | None        # award $ / raise $ / contract $ / null
    counterparty: str | None        # agency / acquirer / secured party / etc.
    source_id: str                  # unique-within-source row identifier
    metadata: str                   # JSON-encoded extras


# Column order used when writing parquet (kept here so all writers stay aligned)
EVENT_TABLE_COLUMNS: tuple[str, ...] = (
    "company_name",
    "event_date",
    "event_type",
    "event_subtype",
    "amount_usd",
    "counterparty",
    "source_id",
    "metadata",
)
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/unit/scripts/capital_events/test_schema.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/capital_events/schema.py tests/unit/scripts/capital_events/test_schema.py
git commit -m "feat(capital-events): add CapitalEvent schema + EventType enum"
```

### Task A3: Shared conftest with cohort fixture

**Files:**
- Create: `tests/unit/scripts/capital_events/conftest.py`

- [ ] **Step 1: Write conftest**

```python
# tests/unit/scripts/capital_events/conftest.py
"""Shared fixtures for capital_events tests."""

import pytest


@pytest.fixture
def cohort() -> list[dict]:
    """Three synthetic cohort firms covering common test cases.

    - ACME INC: vanilla CA biotech, has SBIR + Form D + MA + patents
    - BORING LLC: SBIR-only, no Form D or MA
    - OUT-OF-STATE CORP: MA firm with diverse events
    """
    return [
        {
            "company_name": "ACME INC",
            "state": "California", "city": "SAN DIEGO", "zip_code": "92101",
            "agency": "Department of Defense",
            "first_award_year": 2018, "last_award_year": 2023,
            "total_award_amount": 1_500_000.0,
            "form_d_filing_count": 1, "form_d_total_raised": 25_000_000.0,
        },
        {
            "company_name": "BORING LLC",
            "state": "Texas", "city": "AUSTIN", "zip_code": "73301",
            "agency": "National Science Foundation",
            "first_award_year": 2020, "last_award_year": 2021,
            "total_award_amount": 250_000.0,
            "form_d_filing_count": 0, "form_d_total_raised": 0.0,
        },
        {
            "company_name": "OUT-OF-STATE CORP",
            "state": "Massachusetts", "city": "CAMBRIDGE", "zip_code": "02139",
            "agency": "Department of Health and Human Services",
            "first_award_year": 2015, "last_award_year": 2022,
            "total_award_amount": 3_200_000.0,
            "form_d_filing_count": 2, "form_d_total_raised": 75_000_000.0,
        },
    ]
```

- [ ] **Step 2: Verify conftest loads (run schema tests with -v, fixture is now available even if unused)**

Run: `pytest tests/unit/scripts/capital_events/ -v`
Expected: 12 passed (9 common + 3 schema; conftest loads silently).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/scripts/capital_events/conftest.py
git commit -m "test(capital-events): add shared cohort fixture"
```

---

## Phase B: Per-source builders

Each builder is a pure function `build_X(cohort, source_path) -> Iterator[CapitalEvent]`. Tests use tiny synthetic fixtures (3–5 rows) via `tmp_path`. Production runs read from the real paths in `$SBIR_DATA_DIR`.

### Task B1: UCC filings builder (simplest — empty if file missing)

**Files:**
- Create: `scripts/data/capital_events/sources/ucc.py`
- Create: `tests/unit/scripts/capital_events/test_ucc.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scripts/capital_events/test_ucc.py
"""Tests for UCC capital-event builder."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.sources.ucc import build_ucc_events  # noqa: E402


def test_returns_empty_when_file_missing(cohort, tmp_path):
    missing = tmp_path / "nope.jsonl"
    events = list(build_ucc_events(cohort, missing))
    assert events == []


def test_yields_one_event_per_match(cohort, tmp_path):
    src = tmp_path / "ucc1_pilot_matches.jsonl"
    src.write_text(json.dumps({
        "cohort_company_name": "ACME INC",
        "match_confidence": "high",
        "match_score": 1.0,
        "filing": {
            "filing_number": "U240107248023",
            "filing_type": "initial",
            "filing_date": "2024-01-30",
            "debtor_name": "ACME INC",
            "debtor_address": "SAN DIEGO, CA",
            "secured_party_name": "LEAF CAPITAL FUNDING, LLC",
            "secured_party_address": "PHILADELPHIA, PA",
            "status_portal": "Active",
            "lapse_date": "2029-01-30",
            "source": "CA",
        },
    }) + "\n")

    events = list(build_ucc_events(cohort, src))
    assert len(events) == 1
    e = events[0]
    assert e["company_name"] == "ACME INC"
    assert e["event_date"] == "2024-01-30"
    assert e["event_type"] == "ucc_filing"
    assert e["event_subtype"] == "initial"
    assert e["amount_usd"] is None
    assert e["counterparty"] == "LEAF CAPITAL FUNDING, LLC"
    assert e["source_id"] == "U240107248023"
    meta = json.loads(e["metadata"])
    assert meta["secured_party_address"] == "PHILADELPHIA, PA"
    assert meta["match_confidence"] == "high"


def test_skips_filings_for_non_cohort_firms(cohort, tmp_path):
    src = tmp_path / "ucc1_pilot_matches.jsonl"
    src.write_text(json.dumps({
        "cohort_company_name": "UNRELATED INC",
        "match_confidence": "high", "match_score": 1.0,
        "filing": {
            "filing_number": "X", "filing_type": "initial",
            "filing_date": "2024-01-01",
            "debtor_name": "UNRELATED INC", "debtor_address": "",
            "secured_party_name": "BANK", "secured_party_address": "",
            "status_portal": "Active", "lapse_date": None, "source": "CA",
        },
    }) + "\n")
    assert list(build_ucc_events(cohort, src)) == []
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/scripts/capital_events/test_ucc.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Write `ucc.py`**

```python
# scripts/data/capital_events/sources/ucc.py
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
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/unit/scripts/capital_events/test_ucc.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/capital_events/sources/ucc.py tests/unit/scripts/capital_events/test_ucc.py
git commit -m "feat(capital-events): add UCC filing event builder"
```

### Task B2: M&A events builder

**Files:**
- Create: `scripts/data/capital_events/sources/ma_events.py`
- Create: `tests/unit/scripts/capital_events/test_ma_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scripts/capital_events/test_ma_events.py
"""Tests for M&A capital-event builder."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.sources.ma_events import build_ma_events  # noqa: E402


def _ma_row(name, date, confidence, acquirer=None, signals=None, press=None):
    return {
        "company_name": name,
        "event_date": date,
        "confidence": confidence,
        "acquirer": acquirer,
        "signals": signals or {},
        "press_wire_signals": press or {},
        "signal_count": 1,
        "form_d_detail": None,
        "efts_detail": None,
        "sbir_context": {"agency": "DoD"},
        "enriched": True,
    }


def test_emits_high_and_medium_drops_low(cohort, tmp_path):
    src = tmp_path / "ma.jsonl"
    src.write_text("\n".join(json.dumps(r) for r in [
        _ma_row("ACME INC", "2023-06-15", "high", acquirer="GiantCo"),
        _ma_row("OUT-OF-STATE CORP", "2022-11-01", "medium"),
        _ma_row("ACME INC", "2024-02-01", "low"),  # dropped
    ]) + "\n")

    events = list(build_ma_events(cohort, src))
    assert len(events) == 2
    by_firm = {e["company_name"]: e for e in events}
    acme = by_firm["ACME INC"]
    assert acme["event_date"] == "2023-06-15"
    assert acme["event_type"] == "ma_event"
    assert acme["event_subtype"] == "high"
    assert acme["counterparty"] == "GiantCo"
    assert acme["amount_usd"] is None
    assert acme["source_id"] == "ACME INC__2023-06-15"


def test_skips_non_cohort_firms(cohort, tmp_path):
    src = tmp_path / "ma.jsonl"
    src.write_text(json.dumps(_ma_row("UNRELATED INC", "2023-01-01", "high")) + "\n")
    assert list(build_ma_events(cohort, src)) == []


def test_returns_empty_when_file_missing(cohort, tmp_path):
    assert list(build_ma_events(cohort, tmp_path / "nope.jsonl")) == []


def test_metadata_carries_signals_and_press_wire(cohort, tmp_path):
    src = tmp_path / "ma.jsonl"
    src.write_text(json.dumps(_ma_row(
        "ACME INC", "2023-06-15", "high",
        signals={"form_d_business_combination": True},
        press={"acquisition_announcement_count": 3},
    )) + "\n")
    events = list(build_ma_events(cohort, src))
    meta = json.loads(events[0]["metadata"])
    assert meta["signals"]["form_d_business_combination"] is True
    assert meta["press_wire_signals"]["acquisition_announcement_count"] == 3
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/scripts/capital_events/test_ma_events.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Write `ma_events.py`**

```python
# scripts/data/capital_events/sources/ma_events.py
"""M&A events → CapitalEvent builder.

Reads enriched_sbir_ma_events.jsonl (output of the M&A detection pipeline
with press wire / EDGAR enrichment). Filters to high+medium confidence
per the spec; low-confidence events are dropped to keep noise out.

Note: the file uses the field name `confidence` (not `tier` as some older
specs reference).
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
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/unit/scripts/capital_events/test_ma_events.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/capital_events/sources/ma_events.py tests/unit/scripts/capital_events/test_ma_events.py
git commit -m "feat(capital-events): add M&A event builder"
```

### Task B3: Form D filings builder

**Files:**
- Create: `scripts/data/capital_events/sources/form_d.py`
- Create: `tests/unit/scripts/capital_events/test_form_d.py`

The Form D detail file structure (confirmed from real data):

```json
{
  "company_name": "ACME INC",
  "form_d_cik": "0001234567",
  "match_confidence": {"tier": "high", "person_score": 0.95, "address_score": 1},
  "offering_count": 2,
  "total_raised": 25000000.0,
  "offerings": [
    {
      "accession_number": "0001234567-24-000001",
      "filing_date": "2024-03-15",
      "total_amount_sold": 10000000.0,
      "securities_types": ["Equity"],
      "is_business_combination": false,
      "is_amendment": false,
      "minimum_investment": 25000,
      "num_investors": 12,
      "related_persons": [...],
      ...
    }
  ]
}
```

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scripts/capital_events/test_form_d.py
"""Tests for Form D capital-event builder."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.sources.form_d import (  # noqa: E402
    build_form_d_events,
    classify_securities_types,
)


def _form_d(name, tier, offerings):
    return {
        "company_name": name,
        "form_d_cik": "0001234567",
        "match_confidence": {"tier": tier, "person_score": 1.0, "address_score": 1},
        "offering_count": len(offerings),
        "total_raised": sum(o.get("total_amount_sold") or 0 for o in offerings),
        "offerings": offerings,
    }


def _offering(accession, filing_date, amount, securities=None, is_combo=False, **kw):
    return {
        "accession_number": accession,
        "filing_date": filing_date,
        "total_amount_sold": amount,
        "securities_types": securities or ["Equity"],
        "is_business_combination": is_combo,
        "is_amendment": False,
        "minimum_investment": 25000,
        "num_investors": 5,
        "related_persons": [],
        **kw,
    }


def test_classify_securities_types():
    assert classify_securities_types(["Equity"]) == "equity"
    assert classify_securities_types(["Debt"]) == "debt"
    assert classify_securities_types(["Option, Warrant or Other Right to Acquire Another Security"]) == "option_warrant"
    assert classify_securities_types(["Equity", "Debt"]) == "other"  # mixed
    assert classify_securities_types([]) == "other"
    assert classify_securities_types(None) == "other"


def test_emits_one_event_per_offering(cohort, tmp_path):
    src = tmp_path / "form_d.jsonl"
    src.write_text(json.dumps(_form_d("ACME INC", "high", [
        _offering("ACC-1", "2023-01-15", 5_000_000.0),
        _offering("ACC-2", "2023-08-22", 10_000_000.0, securities=["Debt"]),
    ])) + "\n")

    events = list(build_form_d_events(cohort, src))
    assert len(events) == 2
    e1 = events[0]
    assert e1["company_name"] == "ACME INC"
    assert e1["event_date"] == "2023-01-15"
    assert e1["event_type"] == "form_d_filing"
    assert e1["event_subtype"] == "equity"
    assert e1["amount_usd"] == 5_000_000.0
    assert e1["counterparty"] is None
    assert e1["source_id"] == "ACC-1"

    e2 = events[1]
    assert e2["event_subtype"] == "debt"


def test_business_combination_overrides_subtype(cohort, tmp_path):
    src = tmp_path / "form_d.jsonl"
    src.write_text(json.dumps(_form_d("ACME INC", "high", [
        _offering("ACC-3", "2024-05-01", 50_000_000.0, securities=["Equity"], is_combo=True),
    ])) + "\n")
    events = list(build_form_d_events(cohort, src))
    assert events[0]["event_subtype"] == "combination"


def test_drops_non_high_tier_records(cohort, tmp_path):
    src = tmp_path / "form_d.jsonl"
    src.write_text("\n".join([
        json.dumps(_form_d("ACME INC", "medium", [_offering("ACC-A", "2024-01-01", 1_000_000.0)])),
        json.dumps(_form_d("OUT-OF-STATE CORP", "high", [_offering("ACC-B", "2023-01-01", 5_000_000.0)])),
    ]) + "\n")
    events = list(build_form_d_events(cohort, src))
    assert len(events) == 1
    assert events[0]["company_name"] == "OUT-OF-STATE CORP"


def test_skips_non_cohort_firms(cohort, tmp_path):
    src = tmp_path / "form_d.jsonl"
    src.write_text(json.dumps(_form_d("UNRELATED INC", "high", [
        _offering("ACC-X", "2024-01-01", 1_000_000.0),
    ])) + "\n")
    assert list(build_form_d_events(cohort, src)) == []


def test_metadata_carries_offering_extras(cohort, tmp_path):
    src = tmp_path / "form_d.jsonl"
    src.write_text(json.dumps(_form_d("ACME INC", "high", [
        _offering("ACC-1", "2024-01-01", 5_000_000.0, minimum_investment=50000, num_investors=8),
    ])) + "\n")
    events = list(build_form_d_events(cohort, src))
    meta = json.loads(events[0]["metadata"])
    assert meta["minimum_investment"] == 50000
    assert meta["num_investors"] == 8
    assert meta["business_combination"] is False
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/scripts/capital_events/test_form_d.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Write `form_d.py`**

```python
# scripts/data/capital_events/sources/form_d.py
"""Form D filings → CapitalEvent builder.

Reads form_d_details.jsonl. Records are kept when their match_confidence.tier
is "high" (same rule the cohort export uses) and the matched company_name
appears in the cohort. One event per offering on the matched record;
business-combination offerings get the special `combination` subtype
regardless of their declared securities type.
"""

import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capital_events.schema import EventType  # noqa: E402

# Map raw securities_types strings → schema subtype values.
_SECURITY_KEYWORDS = {
    "equity": "equity",
    "debt": "debt",
    "option": "option_warrant",
    "warrant": "option_warrant",
    "convertible": "debt",  # convertible notes counted as debt-typed
}


def classify_securities_types(types: list[str] | None) -> str:
    """Project Form D securities_types list to a single subtype label.

    Returns one of: equity / debt / option_warrant / other.
    Mixed-type offerings are labeled "other" — caller can inspect metadata
    for the full original list.
    """
    if not types:
        return "other"
    matched: set[str] = set()
    for t in types:
        lowered = t.lower()
        for keyword, label in _SECURITY_KEYWORDS.items():
            if keyword in lowered:
                matched.add(label)
                break
    if len(matched) == 1:
        return matched.pop()
    return "other"


def build_form_d_events(
    cohort: Iterable[dict], source_path: Path
) -> Iterator[dict]:
    """Yield CapitalEvent rows for Form D offerings against cohort firms."""
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
            tier = (rec.get("match_confidence") or {}).get("tier")
            if tier != "high":
                continue
            for offering in rec.get("offerings") or []:
                securities = offering.get("securities_types") or []
                subtype = (
                    "combination"
                    if offering.get("is_business_combination")
                    else classify_securities_types(securities)
                )
                yield {
                    "company_name": name,
                    "event_date": offering.get("filing_date") or "",
                    "event_type": EventType.FORM_D_FILING.value,
                    "event_subtype": subtype,
                    "amount_usd": offering.get("total_amount_sold"),
                    "counterparty": None,
                    "source_id": offering.get("accession_number") or "",
                    "metadata": json.dumps({
                        "securities_types": securities,
                        "minimum_investment": offering.get("minimum_investment"),
                        "num_investors": offering.get("num_investors"),
                        "business_combination": bool(offering.get("is_business_combination")),
                        "is_amendment": bool(offering.get("is_amendment")),
                    }),
                }
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/unit/scripts/capital_events/test_form_d.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/capital_events/sources/form_d.py tests/unit/scripts/capital_events/test_form_d.py
git commit -m "feat(capital-events): add Form D filing event builder"
```

### Task B4: SBIR awards builder

The SBIR awards CSV uses Title-Case headers with spaces and quotes. Confirmed columns include: `Company`, `Agency`, `Branch`, `Phase`, `Award Year`, `Award Amount`, `Proposal Award Date`, `Agency Tracking Number`, `Solicitation Number`, `Solicitation Year`, `City`, `State`, `Zip`. Cohort name match is uppercase, stripped — same convention as `scripts/data/ucc/export_cohort.py::_normalize_sbir_award`.

**Files:**
- Create: `scripts/data/capital_events/sources/sbir_awards.py`
- Create: `tests/unit/scripts/capital_events/test_sbir_awards.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scripts/capital_events/test_sbir_awards.py
"""Tests for SBIR award capital-event builder."""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.sources.sbir_awards import (  # noqa: E402
    build_sbir_award_events,
    classify_phase,
)


def _write_awards_csv(path: Path, rows: list[dict]) -> None:
    headers = [
        "Company", "Agency", "Branch", "Phase", "Award Year", "Award Amount",
        "Proposal Award Date", "Agency Tracking Number", "Solicitation Number",
        "Solicitation Year", "City", "State", "Zip", "Contract",
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for row in rows:
            w.writerow({h: row.get(h, "") for h in headers})


def test_classify_phase():
    assert classify_phase("Phase I") == "sbir_phase_i"
    assert classify_phase("Phase II") == "sbir_phase_ii"
    assert classify_phase("Phase III") == "sbir_phase_iii"
    assert classify_phase("PHASE II") == "sbir_phase_ii"
    assert classify_phase("Phase I-Direct") == "sbir_phase_i"  # 'I' wins
    assert classify_phase("") == "sbir_phase_unknown"
    assert classify_phase(None) == "sbir_phase_unknown"


def test_emits_one_event_per_matching_award(cohort, tmp_path):
    csv_path = tmp_path / "awards.csv"
    _write_awards_csv(csv_path, [
        {"Company": "Acme Inc", "Agency": "Department of Defense", "Branch": "Army",
         "Phase": "Phase I", "Award Year": "2018", "Award Amount": "150000",
         "Proposal Award Date": "2018-06-15", "Agency Tracking Number": "ATN-001",
         "Solicitation Number": "SBIR-18-001", "Solicitation Year": "2018",
         "City": "San Diego", "State": "California", "Zip": "92101",
         "Contract": "W56HZV-18-C-0001"},
        {"Company": "Acme Inc", "Agency": "Department of Defense", "Branch": "Army",
         "Phase": "Phase II", "Award Year": "2020", "Award Amount": "1000000",
         "Proposal Award Date": "2020-09-01", "Agency Tracking Number": "ATN-002",
         "Solicitation Number": "SBIR-20-002", "Solicitation Year": "2020",
         "City": "San Diego", "State": "California", "Zip": "92101",
         "Contract": "W56HZV-20-C-0002"},
    ])
    events = list(build_sbir_award_events(cohort, csv_path))
    assert len(events) == 2
    by_phase = {e["event_subtype"]: e for e in events}
    p1 = by_phase["sbir_phase_i"]
    assert p1["company_name"] == "ACME INC"
    assert p1["event_date"] == "2018-06-15"
    assert p1["event_type"] == "sbir_award"
    assert p1["amount_usd"] == 150000.0
    assert p1["counterparty"] == "Department of Defense"
    assert p1["source_id"] == "ATN-001"
    meta = json.loads(p1["metadata"])
    assert meta["branch"] == "Army"
    assert meta["solicitation_year"] == 2018


def test_falls_back_to_contract_id_when_atn_missing(cohort, tmp_path):
    csv_path = tmp_path / "awards.csv"
    _write_awards_csv(csv_path, [
        {"Company": "Boring LLC", "Agency": "National Science Foundation", "Branch": "",
         "Phase": "Phase I", "Award Year": "2020", "Award Amount": "250000",
         "Proposal Award Date": "2020-04-01", "Agency Tracking Number": "",
         "Solicitation Number": "NSF-20-501", "Solicitation Year": "2020",
         "City": "Austin", "State": "Texas", "Zip": "73301",
         "Contract": "NSF-2020-100"},
    ])
    events = list(build_sbir_award_events(cohort, csv_path))
    assert len(events) == 1
    assert events[0]["source_id"] == "NSF-2020-100"


def test_skips_non_cohort_firms(cohort, tmp_path):
    csv_path = tmp_path / "awards.csv"
    _write_awards_csv(csv_path, [
        {"Company": "Unrelated Inc", "Agency": "DoD", "Branch": "", "Phase": "Phase I",
         "Award Year": "2020", "Award Amount": "100000", "Proposal Award Date": "2020-01-01",
         "Agency Tracking Number": "X", "Solicitation Number": "", "Solicitation Year": "",
         "City": "", "State": "", "Zip": "", "Contract": ""},
    ])
    assert list(build_sbir_award_events(cohort, csv_path)) == []


def test_returns_empty_when_file_missing(cohort, tmp_path):
    assert list(build_sbir_award_events(cohort, tmp_path / "nope.csv")) == []
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/scripts/capital_events/test_sbir_awards.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Write `sbir_awards.py`**

```python
# scripts/data/capital_events/sources/sbir_awards.py
"""SBIR awards → CapitalEvent builder.

Reads raw/sbir/award_data.csv (Title-Case headers). Match against cohort
is by normalized company name (UPPERCASE + strip), same convention used
by scripts/data/ucc/export_cohort.py.
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
    # Check most-specific first so "Phase III-Direct" classifies as III not I
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
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/unit/scripts/capital_events/test_sbir_awards.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/capital_events/sources/sbir_awards.py tests/unit/scripts/capital_events/test_sbir_awards.py
git commit -m "feat(capital-events): add SBIR award event builder"
```

### Task B5: USAspending Phase 3 contracts builder

The Phase 3 USAspending file uses Title-Case keys: `Award Amount`, `Award ID`, `Awarding Agency`, `Awarding Sub Agency`, `Description`, `End Date`, `Funding Agency`, `Funding Sub Agency`, `NAICS`, `Recipient Name`, `Start Date`, `agency_slug`, `awarding_agency_id`, `generated_internal_id`, `internal_id`.

**Match strategy:** by normalized `Recipient Name` ↔ cohort `company_name`. This is a name-only join, but it's what the Phase 3 work uses; reuse that linkage.

**Files:**
- Create: `scripts/data/capital_events/sources/usaspending.py`
- Create: `tests/unit/scripts/capital_events/test_usaspending.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scripts/capital_events/test_usaspending.py
"""Tests for USAspending Phase 3 contract event builder."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.sources.usaspending import build_usaspending_events  # noqa: E402


def _contract(recipient, award_id, start, amount, agency="Department of Defense"):
    return {
        "Recipient Name": recipient,
        "Award ID": award_id,
        "Award Amount": amount,
        "Start Date": start,
        "End Date": "",
        "Funding Agency": agency,
        "Funding Sub Agency": "Army",
        "Awarding Agency": agency,
        "Awarding Sub Agency": "Army",
        "Description": "Phase III commercialization contract",
        "NAICS": "541715",
        "generated_internal_id": f"GEN-{award_id}",
        "internal_id": f"INT-{award_id}",
        "agency_slug": "dod",
        "awarding_agency_id": 9700,
    }


def test_emits_one_event_per_contract(cohort, tmp_path):
    src = tmp_path / "usaspending.jsonl"
    src.write_text("\n".join(json.dumps(c) for c in [
        _contract("ACME INC", "W56HZV-22-D-0001", "2022-06-01", 5_000_000.0),
        _contract("ACME INC", "W56HZV-23-D-0002", "2023-09-15", 8_000_000.0),
    ]) + "\n")

    events = list(build_usaspending_events(cohort, src))
    assert len(events) == 2
    e = events[0]
    assert e["company_name"] == "ACME INC"
    assert e["event_date"] == "2022-06-01"
    assert e["event_type"] == "usaspending_contract"
    assert e["amount_usd"] == 5_000_000.0
    assert e["counterparty"] == "Department of Defense"
    assert e["source_id"] == "W56HZV-22-D-0001"


def test_falls_back_to_generated_internal_id_when_award_id_missing(cohort, tmp_path):
    src = tmp_path / "usaspending.jsonl"
    contract = _contract("ACME INC", "", "2022-06-01", 1_000_000.0)
    contract["Award ID"] = ""
    src.write_text(json.dumps(contract) + "\n")
    events = list(build_usaspending_events(cohort, src))
    assert events[0]["source_id"] == "GEN-"


def test_metadata_carries_naics_and_subagency(cohort, tmp_path):
    src = tmp_path / "usaspending.jsonl"
    src.write_text(json.dumps(_contract("ACME INC", "AW1", "2023-01-01", 100.0)) + "\n")
    meta = json.loads(list(build_usaspending_events(cohort, src))[0]["metadata"])
    assert meta["naics"] == "541715"
    assert meta["funding_sub_agency"] == "Army"
    assert meta["description"] == "Phase III commercialization contract"


def test_skips_non_cohort_firms(cohort, tmp_path):
    src = tmp_path / "usaspending.jsonl"
    src.write_text(json.dumps(_contract("UNRELATED INC", "X", "2023-01-01", 100.0)) + "\n")
    assert list(build_usaspending_events(cohort, src)) == []


def test_returns_empty_when_file_missing(cohort, tmp_path):
    assert list(build_usaspending_events(cohort, tmp_path / "nope.jsonl")) == []


def test_matches_recipient_name_case_insensitive(cohort, tmp_path):
    """Phase 3 USAspending may have varied casing; cohort key is uppercase."""
    src = tmp_path / "usaspending.jsonl"
    src.write_text(json.dumps(_contract("Acme Inc", "X", "2023-01-01", 100.0)) + "\n")
    events = list(build_usaspending_events(cohort, src))
    assert len(events) == 1
    assert events[0]["company_name"] == "ACME INC"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/scripts/capital_events/test_usaspending.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Write `usaspending.py`**

```python
# scripts/data/capital_events/sources/usaspending.py
"""USAspending Phase 3 contracts → CapitalEvent builder.

Reads processed/sbir_phase3/usaspending_phase3_contracts.jsonl. Matches
to cohort firms by normalized Recipient Name (uppercase + strip), same
convention used elsewhere in the pilot.
"""

import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capital_events._common import normalize_date  # noqa: E402
from capital_events.schema import EventType  # noqa: E402


def build_usaspending_events(
    cohort: Iterable[dict], source_path: Path
) -> Iterator[dict]:
    """Yield CapitalEvent rows for Phase 3 USAspending contracts to cohort firms."""
    if not source_path.exists():
        return
    cohort_names = {row["company_name"] for row in cohort}
    with source_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                contract = json.loads(line)
            except json.JSONDecodeError:
                continue
            recipient = (contract.get("Recipient Name") or "").strip().upper()
            if recipient not in cohort_names:
                continue
            event_date = normalize_date(contract.get("Start Date"))
            source_id = (contract.get("Award ID") or "").strip() \
                or f"GEN-{contract.get('Award ID', '')}"
            # If both Award ID and generated_internal_id are present, prefer Award ID.
            # If Award ID is empty, fall back to "GEN-<generated_internal_id>"
            if not (contract.get("Award ID") or "").strip():
                gen_id = (contract.get("generated_internal_id") or "").strip()
                source_id = f"GEN-{gen_id}" if gen_id else f"GEN-"
            yield {
                "company_name": recipient,
                "event_date": event_date,
                "event_type": EventType.USASPENDING_CONTRACT.value,
                "event_subtype": None,  # contract type not consistently surfaced
                "amount_usd": float(contract.get("Award Amount") or 0) or None,
                "counterparty": (contract.get("Funding Agency") or "").strip() or None,
                "source_id": source_id,
                "metadata": json.dumps({
                    "funding_sub_agency": (contract.get("Funding Sub Agency") or "").strip() or None,
                    "awarding_agency": (contract.get("Awarding Agency") or "").strip() or None,
                    "awarding_sub_agency": (contract.get("Awarding Sub Agency") or "").strip() or None,
                    "naics": (contract.get("NAICS") or "").strip() or None,
                    "description": (contract.get("Description") or "").strip() or None,
                    "end_date": normalize_date(contract.get("End Date")) or None,
                    "agency_slug": contract.get("agency_slug"),
                    "generated_internal_id": contract.get("generated_internal_id"),
                }),
            }
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/unit/scripts/capital_events/test_usaspending.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/capital_events/sources/usaspending.py tests/unit/scripts/capital_events/test_usaspending.py
git commit -m "feat(capital-events): add USAspending Phase 3 contract event builder"
```

### Task B6: Patent grants builder

The transformed patent files have keys: `assignee_names, assignment_count, assignor_names, grant_number, language, latest_recorded_date, linked_companies, title`. **Key insight from spec exploration:** `linked_companies` is the existing cohort linkage produced by the patent transformer — match by intersecting that list against cohort names rather than rebuilding name-resolution logic.

Multiple timestamped snapshot files exist; pick the newest by mtime.

**Files:**
- Create: `scripts/data/capital_events/sources/patents.py`
- Create: `tests/unit/scripts/capital_events/test_patents.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scripts/capital_events/test_patents.py
"""Tests for patent grant event builder."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.sources.patents import (  # noqa: E402
    build_patent_events,
    newest_patent_file,
)


def _patent(grant_num, date, linked_companies=None, assignees=None, title="Test patent"):
    return {
        "grant_number": grant_num,
        "latest_recorded_date": date,
        "title": title,
        "language": "en",
        "assignee_names": assignees or ["ACME INC"],
        "assignor_names": [],
        "assignment_count": 0,
        "linked_companies": linked_companies or ["ACME INC"],
    }


def test_newest_patent_file_picks_latest_mtime(tmp_path):
    older = tmp_path / "patents_20240101T000000.jsonl"
    older.write_text("")
    time.sleep(0.01)  # ensure differing mtimes
    newer = tmp_path / "patents_20240601T000000.jsonl"
    newer.write_text("")
    assert newest_patent_file(tmp_path) == newer


def test_newest_patent_file_returns_none_when_no_files(tmp_path):
    assert newest_patent_file(tmp_path) is None


def test_emits_one_event_per_linked_patent(cohort, tmp_path):
    src = tmp_path / "patents_20260418T142224.jsonl"
    src.write_text("\n".join(json.dumps(p) for p in [
        _patent("11000001", "2023-05-15", linked_companies=["ACME INC"]),
        _patent("11000002", "2024-02-01", linked_companies=["ACME INC"], title="Better patent"),
    ]) + "\n")
    events = list(build_patent_events(cohort, src))
    assert len(events) == 2
    e = events[0]
    assert e["company_name"] == "ACME INC"
    assert e["event_date"] == "2023-05-15"
    assert e["event_type"] == "patent_grant"
    assert e["event_subtype"] is None
    assert e["amount_usd"] is None
    assert e["counterparty"] is None
    assert e["source_id"] == "11000001"
    meta = json.loads(e["metadata"])
    assert meta["title"] == "Test patent"


def test_emits_one_event_per_cohort_firm_when_multiple_linked(cohort, tmp_path):
    """A patent linked to two cohort firms produces two events (joint assignment)."""
    src = tmp_path / "patents_20260418T142224.jsonl"
    src.write_text(json.dumps(_patent(
        "11000003", "2024-01-01",
        linked_companies=["ACME INC", "OUT-OF-STATE CORP"],
    )) + "\n")
    events = list(build_patent_events(cohort, src))
    assert len(events) == 2
    assert {e["company_name"] for e in events} == {"ACME INC", "OUT-OF-STATE CORP"}


def test_skips_patents_not_linked_to_cohort(cohort, tmp_path):
    src = tmp_path / "patents_20260418T142224.jsonl"
    src.write_text(json.dumps(_patent(
        "11000004", "2024-01-01", linked_companies=["UNRELATED INC"],
    )) + "\n")
    assert list(build_patent_events(cohort, src)) == []


def test_returns_empty_when_file_missing(cohort, tmp_path):
    assert list(build_patent_events(cohort, tmp_path / "nope.jsonl")) == []
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/scripts/capital_events/test_patents.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Write `patents.py`**

```python
# scripts/data/capital_events/sources/patents.py
"""Patent grants → CapitalEvent builder.

Reads the newest patents_*.jsonl file in transformed/uspto/. Match to
cohort firms uses the patent record's pre-computed `linked_companies`
list (produced by the upstream patent transformer); we avoid replicating
the entity-resolution logic here.

One event per (patent, cohort-firm-link) pair: a patent jointly assigned
to two cohort firms yields two events. This is the right modeling for
"events per firm" since both firms experience the grant.
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
    """Yield CapitalEvent rows for patent grants linked to cohort firms.

    A patent linked to N cohort firms produces N events. source_path may
    be either a specific patents_*.jsonl file or a directory containing
    them (in which case the newest by mtime is used).
    """
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
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/unit/scripts/capital_events/test_patents.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/capital_events/sources/patents.py tests/unit/scripts/capital_events/test_patents.py
git commit -m "feat(capital-events): add patent grant event builder"
```

---

## Phase C: Aggregation + orchestration

### Task C1: Per-firm summary (wide-format aggregator)

**Files:**
- Create: `scripts/data/capital_events/summarize.py`
- Create: `tests/unit/scripts/capital_events/test_summarize.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scripts/capital_events/test_summarize.py
"""Tests for per-firm summary aggregator."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.summarize import summarize_per_firm  # noqa: E402


def _events_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=[
        "company_name", "event_date", "event_type", "event_subtype",
        "amount_usd", "counterparty", "source_id", "metadata",
    ])


def _event(company, date, etype, subtype=None, amount=None, counterparty=None,
           source_id="X", metadata="{}"):
    return {
        "company_name": company, "event_date": date, "event_type": etype,
        "event_subtype": subtype, "amount_usd": amount,
        "counterparty": counterparty, "source_id": source_id, "metadata": metadata,
    }


def test_summary_includes_one_row_per_cohort_firm(cohort):
    events = _events_df([])
    summary = summarize_per_firm(events, cohort)
    assert len(summary) == 3
    assert set(summary["company_name"]) == {"ACME INC", "BORING LLC", "OUT-OF-STATE CORP"}


def test_summary_counts_and_sums_sbir_events(cohort):
    events = _events_df([
        _event("ACME INC", "2018-06-15", "sbir_award", "sbir_phase_i", 150000.0),
        _event("ACME INC", "2020-09-01", "sbir_award", "sbir_phase_ii", 1000000.0),
        _event("BORING LLC", "2020-04-01", "sbir_award", "sbir_phase_i", 250000.0),
    ])
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert acme["sbir_award_count"] == 2
    assert acme["total_sbir_amount"] == 1_150_000.0


def test_summary_form_d_aggregations(cohort):
    events = _events_df([
        _event("ACME INC", "2023-01-15", "form_d_filing", "equity", 5_000_000.0),
        _event("ACME INC", "2023-08-22", "form_d_filing", "debt", 10_000_000.0),
    ])
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert acme["form_d_filing_count"] == 2
    assert acme["total_form_d_raised"] == 15_000_000.0


def test_summary_ma_flags_and_dates(cohort):
    events = _events_df([
        _event("ACME INC", "2024-02-01", "ma_event", "medium"),
        _event("ACME INC", "2024-03-01", "ma_event", "high"),
    ])
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert acme["has_ma_event"] is True or acme["has_ma_event"] == True  # bool/numpy
    assert acme["first_ma_event_date"] == "2024-02-01"
    assert acme["ma_confidence_max_tier"] == "high"


def test_summary_first_and_last_event_dates(cohort):
    events = _events_df([
        _event("ACME INC", "2018-06-15", "sbir_award", "sbir_phase_i", 150000.0),
        _event("ACME INC", "2024-02-01", "ma_event", "high"),
        _event("ACME INC", "2023-08-22", "form_d_filing", "equity", 10_000_000.0),
    ])
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert acme["first_event_date"] == "2018-06-15"
    assert acme["last_event_date"] == "2024-02-01"
    assert acme["event_type_count"] == 3


def test_summary_zero_event_firm_has_zero_counts(cohort):
    """A cohort firm with no events should still appear with zeros."""
    events = _events_df([])
    summary = summarize_per_firm(events, cohort)
    boring = summary[summary.company_name == "BORING LLC"].iloc[0]
    assert boring["sbir_award_count"] == 0
    assert boring["form_d_filing_count"] == 0
    assert boring["has_ma_event"] is False or boring["has_ma_event"] == False
    assert pd.isna(boring["first_event_date"])
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/scripts/capital_events/test_summarize.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Write `summarize.py`**

```python
# scripts/data/capital_events/summarize.py
"""Per-firm wide-format aggregator over the long-format events table."""

import pandas as pd


def summarize_per_firm(events: pd.DataFrame, cohort: list[dict]) -> pd.DataFrame:
    """Aggregate events to one row per cohort firm.

    Inputs:
      events: long-format events DataFrame with columns matching the
              CapitalEvent schema.
      cohort: list of cohort row dicts; every cohort firm is represented
              in the output even when it has zero events.

    Returns DataFrame with one row per firm, columns documented in the
    spec's "Wide-format per-firm summary" section.
    """
    cohort_df = pd.DataFrame(cohort)

    if events.empty:
        agg = pd.DataFrame(columns=["company_name"])
    else:
        # Per-type counts and sums via groupby
        by_firm_type = events.groupby(
            ["company_name", "event_type"], dropna=False
        ).agg(
            count=("source_id", "size"),
            total_amount=("amount_usd", "sum"),
            first_date=("event_date", "min"),
        ).reset_index()
        # Pivot to wide format
        counts = by_firm_type.pivot(
            index="company_name", columns="event_type", values="count"
        ).fillna(0).astype(int)
        sums = by_firm_type.pivot(
            index="company_name", columns="event_type", values="total_amount"
        ).fillna(0.0)
        firsts = by_firm_type.pivot(
            index="company_name", columns="event_type", values="first_date"
        )
        agg = pd.DataFrame({
            "sbir_award_count": counts.get("sbir_award", pd.Series(dtype=int)),
            "total_sbir_amount": sums.get("sbir_award", pd.Series(dtype=float)),
            "form_d_filing_count": counts.get("form_d_filing", pd.Series(dtype=int)),
            "total_form_d_raised": sums.get("form_d_filing", pd.Series(dtype=float)),
            "ma_event_count": counts.get("ma_event", pd.Series(dtype=int)),
            "first_ma_event_date": firsts.get("ma_event", pd.Series(dtype=str)),
            "usaspending_contract_count": counts.get("usaspending_contract", pd.Series(dtype=int)),
            "total_usaspending_obligated": sums.get("usaspending_contract", pd.Series(dtype=float)),
            "first_usaspending_year": firsts.get("usaspending_contract", pd.Series(dtype=str)).map(
                lambda s: int(s[:4]) if isinstance(s, str) and len(s) >= 4 else None
            ),
            "patent_count": counts.get("patent_grant", pd.Series(dtype=int)),
            "first_patent_year": firsts.get("patent_grant", pd.Series(dtype=str)).map(
                lambda s: int(s[:4]) if isinstance(s, str) and len(s) >= 4 else None
            ),
            "ucc_filing_count": counts.get("ucc_filing", pd.Series(dtype=int)),
        }).reset_index()

        # Cross-type derivations
        first_overall = events.groupby("company_name")["event_date"].min()
        last_overall = events.groupby("company_name")["event_date"].max()
        type_count = events.groupby("company_name")["event_type"].nunique()
        agg["first_event_date"] = agg["company_name"].map(first_overall)
        agg["last_event_date"] = agg["company_name"].map(last_overall)
        agg["event_type_count"] = agg["company_name"].map(type_count).fillna(0).astype(int)

        # MA tier max
        ma_only = events[events["event_type"] == "ma_event"]
        if not ma_only.empty:
            ma_max_tier = (
                ma_only.groupby("company_name")["event_subtype"]
                .apply(lambda s: "high" if (s == "high").any() else "medium")
            )
            agg["ma_confidence_max_tier"] = agg["company_name"].map(ma_max_tier)
        else:
            agg["ma_confidence_max_tier"] = None

    # Left-join cohort so every cohort firm has a row, fill zero-event firms
    result = cohort_df.merge(agg, on="company_name", how="left")
    fill_zero_int_cols = [
        "sbir_award_count", "form_d_filing_count", "ma_event_count",
        "usaspending_contract_count", "patent_count", "ucc_filing_count",
        "event_type_count",
    ]
    fill_zero_float_cols = [
        "total_sbir_amount", "total_form_d_raised", "total_usaspending_obligated",
    ]
    for col in fill_zero_int_cols:
        if col in result.columns:
            result[col] = result[col].fillna(0).astype(int)
        else:
            result[col] = 0
    for col in fill_zero_float_cols:
        if col in result.columns:
            result[col] = result[col].fillna(0.0)
        else:
            result[col] = 0.0
    result["has_ma_event"] = result["ma_event_count"] > 0
    result["has_ucc_match"] = result["ucc_filing_count"] > 0
    return result
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/unit/scripts/capital_events/test_summarize.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/capital_events/summarize.py tests/unit/scripts/capital_events/test_summarize.py
git commit -m "feat(capital-events): add per-firm wide-format summarizer"
```

### Task C2: Orchestrator (CLI entry point)

**Files:**
- Create: `scripts/data/build_capital_events.py`
- Create: `tests/unit/scripts/capital_events/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scripts/capital_events/test_orchestrator.py
"""End-to-end test for the capital-events orchestrator."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def _write_cohort(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_orchestrator_end_to_end(tmp_path, monkeypatch):
    """Synthetic data in all 5 active sources → parquet output with expected rows."""
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))

    # 1 cohort firm
    cohort_path = tmp_path / "form_d_high_conf_cohort.jsonl"
    _write_cohort(cohort_path, [{
        "company_name": "ACME INC", "state": "California", "city": "SAN DIEGO",
        "zip_code": "92101", "agency": "Department of Defense",
        "first_award_year": 2018, "last_award_year": 2023,
        "total_award_amount": 1_500_000.0, "form_d_filing_count": 1,
        "form_d_total_raised": 25_000_000.0,
    }])

    # SBIR awards CSV
    awards_path = tmp_path / "raw" / "sbir" / "award_data.csv"
    awards_path.parent.mkdir(parents=True, exist_ok=True)
    with awards_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "Company", "Agency", "Branch", "Phase", "Award Year", "Award Amount",
            "Proposal Award Date", "Agency Tracking Number", "Solicitation Number",
            "Solicitation Year", "City", "State", "Zip", "Contract",
        ])
        w.writeheader()
        w.writerow({"Company": "Acme Inc", "Agency": "Department of Defense",
                    "Branch": "Army", "Phase": "Phase II", "Award Year": "2020",
                    "Award Amount": "1000000", "Proposal Award Date": "2020-09-01",
                    "Agency Tracking Number": "ATN-1", "Solicitation Number": "S1",
                    "Solicitation Year": "2020", "City": "San Diego",
                    "State": "California", "Zip": "92101", "Contract": "C1"})

    # Form D
    form_d_path = tmp_path / "form_d_details.jsonl"
    form_d_path.write_text(json.dumps({
        "company_name": "ACME INC",
        "match_confidence": {"tier": "high", "person_score": 1.0, "address_score": 1},
        "total_raised": 5_000_000.0, "offering_count": 1, "form_d_cik": "0001",
        "offerings": [{
            "accession_number": "A1", "filing_date": "2023-01-15",
            "total_amount_sold": 5_000_000.0, "securities_types": ["Equity"],
            "is_business_combination": False, "is_amendment": False,
            "minimum_investment": 25000, "num_investors": 5, "related_persons": [],
        }],
    }) + "\n")

    # MA events
    ma_path = tmp_path / "enriched_sbir_ma_events.jsonl"
    ma_path.write_text(json.dumps({
        "company_name": "ACME INC", "event_date": "2024-02-01",
        "confidence": "high", "acquirer": "GiantCo", "signals": {},
        "press_wire_signals": {}, "signal_count": 1, "form_d_detail": None,
        "efts_detail": None, "sbir_context": {"agency": "DoD"}, "enriched": True,
    }) + "\n")

    # USAspending
    us_dir = tmp_path / "processed" / "sbir_phase3"
    us_dir.mkdir(parents=True, exist_ok=True)
    (us_dir / "usaspending_phase3_contracts.jsonl").write_text(json.dumps({
        "Recipient Name": "ACME INC", "Award ID": "AW1",
        "Award Amount": 2_000_000.0, "Start Date": "2022-06-01", "End Date": "",
        "Funding Agency": "Department of Defense", "Funding Sub Agency": "Army",
        "Awarding Agency": "Department of Defense", "Awarding Sub Agency": "Army",
        "Description": "Phase III", "NAICS": "541715",
        "generated_internal_id": "GEN1", "internal_id": "INT1",
        "agency_slug": "dod", "awarding_agency_id": 9700,
    }) + "\n")

    # Patents
    pat_dir = tmp_path / "transformed" / "uspto"
    pat_dir.mkdir(parents=True, exist_ok=True)
    (pat_dir / "patents_20260418T142224.jsonl").write_text(json.dumps({
        "grant_number": "11000001", "latest_recorded_date": "2023-05-15",
        "title": "Test", "language": "en",
        "assignee_names": ["ACME INC"], "assignor_names": [],
        "assignment_count": 0, "linked_companies": ["ACME INC"],
    }) + "\n")

    # Run the orchestrator
    result = subprocess.run(
        [sys.executable, "scripts/data/build_capital_events.py"],
        env={"SBIR_DATA_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"orchestrator failed:\n{result.stderr}"

    # Verify outputs
    events_parquet = tmp_path / "capital_events.parquet"
    summary_parquet = tmp_path / "capital_events_per_firm.parquet"
    sample_jsonl = tmp_path / "capital_events_sample.jsonl"
    assert events_parquet.exists()
    assert summary_parquet.exists()
    assert sample_jsonl.exists()

    events = pd.read_parquet(events_parquet)
    assert set(events.columns) == {
        "company_name", "event_date", "event_type", "event_subtype",
        "amount_usd", "counterparty", "source_id", "metadata",
    }
    # 5 events (sbir, form_d, ma, usaspending, patent) — UCC absent
    assert len(events) == 5
    assert set(events["event_type"]) == {
        "sbir_award", "form_d_filing", "ma_event",
        "usaspending_contract", "patent_grant",
    }
    # Sorted by (company, date, type)
    assert events["event_date"].is_monotonic_increasing  # all same firm

    summary = pd.read_parquet(summary_parquet)
    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["company_name"] == "ACME INC"
    assert row["sbir_award_count"] == 1
    assert row["form_d_filing_count"] == 1
    assert row["ma_event_count"] == 1
    assert row["usaspending_contract_count"] == 1
    assert row["patent_count"] == 1
    assert bool(row["has_ma_event"]) is True
    assert bool(row["has_ucc_match"]) is False
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/scripts/capital_events/test_orchestrator.py -v`
Expected: failure (orchestrator script doesn't exist).

- [ ] **Step 3: Write `build_capital_events.py`**

```python
#!/usr/bin/env python3
"""Build the capital-event timeline parquet artifacts.

Reads per-source data files in $SBIR_DATA_DIR, projects each into the
common CapitalEvent schema, concatenates, sorts, writes:
  - capital_events.parquet          (long-format)
  - capital_events_per_firm.parquet (wide-format summary)
  - capital_events_sample.jsonl     (first 100 events for inspection)

Source files that are missing produce zero events from that source —
the script doesn't fail. Per-source counts are printed on stderr.

Usage:
    python scripts/data/build_capital_events.py
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capital_events._common import data_path  # noqa: E402
from capital_events.schema import EVENT_TABLE_COLUMNS  # noqa: E402
from capital_events.sources.form_d import build_form_d_events  # noqa: E402
from capital_events.sources.ma_events import build_ma_events  # noqa: E402
from capital_events.sources.patents import build_patent_events  # noqa: E402
from capital_events.sources.sbir_awards import build_sbir_award_events  # noqa: E402
from capital_events.sources.ucc import build_ucc_events  # noqa: E402
from capital_events.sources.usaspending import build_usaspending_events  # noqa: E402
from capital_events.summarize import summarize_per_firm  # noqa: E402


def _read_cohort(path: Path) -> list[dict]:
    cohort: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                cohort.append(json.loads(line))
    return cohort


def _to_dataframe(events: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(events, columns=list(EVENT_TABLE_COLUMNS))
    return df.sort_values(
        ["company_name", "event_date", "event_type"], kind="stable"
    ).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path,
                        default=data_path("form_d_high_conf_cohort.jsonl"))
    parser.add_argument("--sbir-awards", type=Path,
                        default=data_path("raw/sbir/award_data.csv"))
    parser.add_argument("--form-d", type=Path,
                        default=data_path("form_d_details.jsonl"))
    parser.add_argument("--ma-events", type=Path,
                        default=data_path("enriched_sbir_ma_events.jsonl"))
    parser.add_argument("--usaspending", type=Path,
                        default=data_path("processed/sbir_phase3/usaspending_phase3_contracts.jsonl"))
    parser.add_argument("--patents-dir", type=Path,
                        default=data_path("transformed/uspto"))
    parser.add_argument("--ucc-matches", type=Path,
                        default=data_path("ucc1_pilot_matches.jsonl"))
    parser.add_argument("--out-events", type=Path,
                        default=data_path("capital_events.parquet"))
    parser.add_argument("--out-summary", type=Path,
                        default=data_path("capital_events_per_firm.parquet"))
    parser.add_argument("--out-sample", type=Path,
                        default=data_path("capital_events_sample.jsonl"))
    args = parser.parse_args()

    if not args.cohort.exists():
        print(f"ERROR: cohort file not found: {args.cohort}", file=sys.stderr)
        return 1

    cohort = _read_cohort(args.cohort)
    print(f"Loaded cohort: {len(cohort)} firms", file=sys.stderr)

    counts: Counter = Counter()
    all_events: list[dict] = []

    for source_name, builder, source_path in [
        ("sbir_award", build_sbir_award_events, args.sbir_awards),
        ("form_d_filing", build_form_d_events, args.form_d),
        ("ma_event", build_ma_events, args.ma_events),
        ("usaspending_contract", build_usaspending_events, args.usaspending),
        ("patent_grant", build_patent_events, args.patents_dir),
        ("ucc_filing", build_ucc_events, args.ucc_matches),
    ]:
        before = len(all_events)
        try:
            for evt in builder(cohort, source_path):
                all_events.append(evt)
            counts[source_name] = len(all_events) - before
            print(f"  {source_name}: {counts[source_name]} events", file=sys.stderr)
        except FileNotFoundError as e:
            print(f"  {source_name}: SKIPPED ({e})", file=sys.stderr)
        except Exception as e:
            print(f"  {source_name}: ERROR ({type(e).__name__}: {e})", file=sys.stderr)

    events_df = _to_dataframe(all_events)
    print(f"Total events: {len(events_df)}", file=sys.stderr)

    args.out_events.parent.mkdir(parents=True, exist_ok=True)
    events_df.to_parquet(args.out_events, index=False)

    summary_df = summarize_per_firm(events_df, cohort)
    summary_df.to_parquet(args.out_summary, index=False)

    with args.out_sample.open("w") as f:
        for row in events_df.head(100).to_dict("records"):
            f.write(json.dumps(row, default=str) + "\n")

    print(f"Wrote {args.out_events}", file=sys.stderr)
    print(f"Wrote {args.out_summary}", file=sys.stderr)
    print(f"Wrote {args.out_sample} (head 100)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/unit/scripts/capital_events/test_orchestrator.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run all capital_events tests**

Run: `pytest tests/unit/scripts/capital_events/ -v`
Expected: ≥30 passed across all modules.

- [ ] **Step 6: Commit**

```bash
git add scripts/data/build_capital_events.py tests/unit/scripts/capital_events/test_orchestrator.py
git commit -m "feat(capital-events): add orchestrator CLI + end-to-end test"
```

---

## Phase D: End-to-end run + results memo

### Task D1: Run against real cohort; record counts

- [ ] **Step 1: Sanity-check that the cohort export exists**

```bash
wc -l "$SBIR_DATA_DIR"/form_d_high_conf_cohort.jsonl
```

Expected: 3,639 rows. If missing, run `python scripts/data/ucc/export_cohort.py` first (it's the upstream dep from PR #303).

- [ ] **Step 2: Run the orchestrator**

```bash
python scripts/data/build_capital_events.py
```

Expected stderr summary:
```
Loaded cohort: 3639 firms
  sbir_award: N events
  form_d_filing: N events
  ma_event: N events
  usaspending_contract: N events
  patent_grant: N events
  ucc_filing: 0 events    (no ucc1_pilot_matches.jsonl in main yet)
Total events: N
Wrote .../capital_events.parquet
Wrote .../capital_events_per_firm.parquet
Wrote .../capital_events_sample.jsonl (head 100)
```

- [ ] **Step 3: Sanity-check the outputs**

```bash
python3 <<'PY'
import pandas as pd
import os

dd = os.environ["SBIR_DATA_DIR"]
events = pd.read_parquet(f"{dd}/capital_events.parquet")
summary = pd.read_parquet(f"{dd}/capital_events_per_firm.parquet")

print("EVENTS")
print(f"  total rows: {len(events):,}")
print(f"  unique firms: {events['company_name'].nunique():,}")
print(f"  by type:\n{events['event_type'].value_counts().to_string()}")
print(f"  date range: {events['event_date'].min()} → {events['event_date'].max()}")

print("\nSUMMARY")
print(f"  total firms (should = 3639): {len(summary):,}")
print(f"  firms with ≥1 SBIR award: {(summary['sbir_award_count']>0).sum():,}")
print(f"  firms with ≥1 Form D filing: {(summary['form_d_filing_count']>0).sum():,}")
print(f"  firms with MA event: {summary['has_ma_event'].sum():,}")
print(f"  firms with USAspending contract: {(summary['usaspending_contract_count']>0).sum():,}")
print(f"  firms with patent grant: {(summary['patent_count']>0).sum():,}")
PY
```

- [ ] **Step 4: Spot-check 5 specific firms**

```bash
python3 <<'PY'
import pandas as pd, os
dd = os.environ["SBIR_DATA_DIR"]
events = pd.read_parquet(f"{dd}/capital_events.parquet")
for firm in ["Inhibrx, Inc.", "ACTIVE MOTIF, INC.", "AADI, LLC",
             "PACIFIC BIOSCIENCES OF CALIFORNIA, INC.", "TRANSPHORM, INC."]:
    rows = events[events["company_name"].str.upper() == firm.upper()]
    print(f"\n=== {firm}: {len(rows)} events ===")
    print(rows[["event_date","event_type","event_subtype","amount_usd","counterparty"]].head(20).to_string(index=False))
PY
```

Confirm each firm's timeline tells a coherent capital story (SBIR awards before Form D, Form D before any MA event, etc.).

- [ ] **Step 5: Record counts in commit message** (no code change, but capture the numbers)

```bash
# No staged changes; record the run output as a marker commit message
# only if there are housekeeping files (e.g., updated .gitignore for outputs)
# Otherwise skip to D2.
```

### Task D2: Write results memo

**Files:**
- Create: `docs/research/capital-events-v1.md`

- [ ] **Step 1: Write the memo from a template**

```markdown
# Capital-Event Timeline v1 — Results

**Date:** YYYY-MM-DD
**Branch:** `claude/capital-events-timeline`
**Cohort:** Form D high-confidence (~3,639 firms; from
`scripts/data/ucc/export_cohort.py`)

## Summary

[1-2 sentences: total event count, per-source breakdown, any surprises.]

## Per-source counts

| Source | Events | Cohort firms with ≥1 event |
|---|---|---|
| sbir_award          | N | N |
| form_d_filing       | N | N |
| ma_event            | N | N |
| usaspending_contract| N | N |
| patent_grant        | N | N |
| ucc_filing          | N | N |

## Cohort coverage

- Firms with ≥1 SBIR award: N (% of cohort)
- Firms with ≥1 Form D filing: N (%)
- Firms with ≥1 MA event: N (%)
- Firms with any USAspending Phase III contract: N (%)
- Firms with ≥1 patent grant: N (%)
- Firms with ≥1 UCC filing: N (%)

## Spot-check vignettes

### Inhibrx, Inc.
[firm-level event timeline; does it tell a coherent capital story?]

### Active Motif, Inc.
[similar; should include the UCC events from the UCC1 pilot if loaded]

### AADI, LLC
[…]

## Known gaps and data-quality notes

- [e.g., patents: only N events because patents_*.jsonl files are
  currently sample-only; full PatentsView ingestion not run]
- [e.g., USAspending coverage limited to Phase III dataset; Phase I/II
  contracts not separately exported]
- [e.g., UCC filings empty because ucc1_pilot_matches.jsonl not produced
  in the bulk run]

## Downstream questions this enables

(Computed downstream from this artifact in follow-on analyses.)

- Time from first SBIR award to first Form D filing, by agency / vintage
- Phase II → MA exit latency by agency
- Capital intensity (Form D total / SBIR total) distribution
- Stage classification on top of the events table (pre-seed / growth / exit)

## Validation against the spec's gate-condition statement

[Confirm the artifact's columns match the spec's schema; the per-firm
summary has every documented column; row counts are non-zero per source
where source data exists.]
```

- [ ] **Step 2: Fill in actual numbers from Task D1**

Replace each `N` placeholder with the count from the Task D1 outputs.
Fill the firm vignettes with the actual event timelines from the spot-check.

- [ ] **Step 3: Commit**

```bash
git add docs/research/capital-events-v1.md
git commit -m "docs(capital-events): record v1 results from initial build"
```

---

## Self-Review Notes

Walked the spec's requirements:

- **Architecture** (standalone script, no Dagster): Task C2 orchestrator
- **6 event types**: Tasks B1–B6 each implement one
- **Cohort scope (Form D high-conf, 3,639 firms)**: orchestrator's `--cohort` default points to the exported file; tests use synthetic 3-firm cohort
- **Schema** (long-format with 8 columns + wide summary): Task A2 defines schema, C1 builds summary, C2 writes both parquets
- **Error handling** (missing source → 0 events, no fail): per-source builders all guard with `source_path.exists()`; orchestrator wraps with try/except
- **Testing** (unit tests per builder, end-to-end orchestrator): all 6 builders have dedicated test files; orchestrator has subprocess-based end-to-end test
- **Worktree-aware data paths**: `_common.py::data_dir()` mirrors the UCC1 pattern
- **Sample.jsonl for inspection**: orchestrator writes head 100

Placeholder scan: none — all task steps contain full code or full commands.

Type/name consistency: `CapitalEvent` TypedDict used across all builders; `EventType` enum values used as `event_type` strings; cohort row dict shape consistent across `conftest.py`, source builders, summarizer.

Spec coverage: all SHALL items + non-goals respected. The two known-unknown deps the spec called out (USAspending cache path, patents source path) are resolved to the actual confirmed paths.

Test coverage estimate: 9 (common) + 3 (schema) + 3 (ucc) + 4 (ma) + 6 (form_d) + 5 (sbir) + 6 (usaspending) + 6 (patents) + 6 (summarize) + 1 (orchestrator) = **49 tests**, well above the spec's ≥30 target.
