"""Tests for the capital-events builder input producer."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "finalize_ma_events", REPO_ROOT / "scripts" / "data" / "finalize_ma_events.py"
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

finalize = _mod.finalize


def test_rows_pass_through_unchanged() -> None:
    """The step produces a file; it must not alter what the events say.

    Every field a consumer reads comes from the events file. Only provenance
    is added.
    """
    event = {
        "company_name": "Acme",
        "confidence": "high",
        "event_date": "2020-01-13",
        "acquirer": "Globex",
        "signals": {"efts_subsidiary": True},
        "efts_detail": {"mention_filers": ["Globex"], "mention_types": ["subsidiary"]},
        "signal_count": 1,
    }
    out = finalize([event], code_version="abc123")
    for key, value in event.items():
        assert out[0][key] == value


def test_provenance_is_stamped() -> None:
    """The historical file recorded no code version, which is how it came to
    reproduce from no commit."""
    out = finalize([{"company_name": "Acme"}], code_version="abc123")
    assert out[0]["finalized_code_version"] == "abc123"
    assert out[0]["finalized_by"] == "finalize_ma_events"


def test_input_is_not_mutated() -> None:
    events = [{"company_name": "Acme", "confidence": "high"}]
    finalize(events, code_version="abc123")
    assert "finalized_by" not in events[0]


def test_empty_input_is_not_an_error() -> None:
    assert finalize([], code_version="abc123") == []
