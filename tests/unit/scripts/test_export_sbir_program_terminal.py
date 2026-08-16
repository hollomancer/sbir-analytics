import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / "scripts" / "data" / "export_sbir_program_terminal.py"


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_sbir_program_terminal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "company_name": "Example Systems",
                "event_date": "2025-01-15",
                "event_type": "sbir_award",
                "event_subtype": "sbir_phase_ii",
                "amount_usd": 1_000_000.0,
                "counterparty": "Department of Energy",
                "source_id": "AWARD-1",
                "metadata": "{}",
            },
            {
                "company_name": "Example Systems",
                "event_date": "2026-03-02",
                "event_type": "form_d_filing",
                "event_subtype": "new_notice",
                "amount_usd": 2_500_000.0,
                "counterparty": None,
                "source_id": "FORM-D-1",
                "metadata": "{}",
            },
        ]
    )


def _summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "company_name": "Example Systems",
                "event_type_count": 2,
                "sbir_award_count": 1,
                "total_sbir_amount": 1_000_000.0,
                "form_d_filing_count": 1,
                "total_form_d_raised": 2_500_000.0,
                "usaspending_contract_count": 0,
                "total_usaspending_obligated": 0.0,
                "patent_count": 0,
                "ma_event_count": 0,
                "ucc_filing_count": 0,
                "last_event_date": "2026-03-02",
            }
        ]
    )


def test_build_terminal_payload_preserves_provenance_and_evidence_boundary(
    tmp_path: Path,
) -> None:
    exporter = _load_exporter()
    events_path = tmp_path / "capital_events.parquet"
    summary_path = tmp_path / "capital_events_per_firm.parquet"
    events_path.write_bytes(b"events artifact")
    summary_path.write_bytes(b"summary artifact")

    payload = exporter.build_terminal_payload(
        _events(),
        _summary(),
        events_path=events_path,
        summary_path=summary_path,
        generated_at=datetime(2026, 4, 1, tzinfo=UTC),
    )

    assert payload["dataset"]["research_question"] == "F1 unified capital-event timeline"
    assert payload["dataset"]["tier"] == "exploratory"
    assert payload["dataset"]["citable"] is False
    assert payload["dataset"]["as_of"] == "2026-03-02"
    assert all(len(source["sha256"]) == 64 for source in payload["dataset"]["sources"])
    assert payload["metrics"][2]["value"] == 1_000_000.0
    assert payload["metrics"][3]["status"] == "lower bound"
    assert payload["firms"][0]["source_ids"] == ["FORM-D-1", "AWARD-1"]
    assert payload["firms"][0]["events"][0]["source_id"] == "FORM-D-1"
    assert payload["firms"][0]["statuses"]["private_capital"] == "lower bound"
    assert payload["firms"][0]["statuses"]["ma_events"] == "lower bound"


def test_build_terminal_payload_rejects_incomplete_events(tmp_path: Path) -> None:
    exporter = _load_exporter()
    events_path = tmp_path / "events"
    summary_path = tmp_path / "summary"
    events_path.write_bytes(b"events")
    summary_path.write_bytes(b"summary")

    with pytest.raises(ValueError, match="events artifact missing columns"):
        exporter.build_terminal_payload(
            pd.DataFrame([{"company_name": "Example Systems"}]),
            _summary(),
            events_path=events_path,
            summary_path=summary_path,
        )


def test_export_terminal_fails_closed_when_artifacts_are_missing(tmp_path: Path) -> None:
    exporter = _load_exporter()

    with pytest.raises(FileNotFoundError, match="run scripts/data/build_capital_events.py"):
        exporter.export_terminal(
            tmp_path / "missing-events.parquet",
            tmp_path / "missing-summary.parquet",
            tmp_path / "terminal.json",
        )

