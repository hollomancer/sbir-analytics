"""Unit tests for M&A (mergers and acquisitions) detection from USPTO patent assignments."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from src.assets.ma_detection import company_mergers_and_acquisitions


@pytest.fixture
def ensure_reports_dir():
    """Ensure reports directory exists for test output."""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    yield reports_dir
    # Cleanup: remove test output file if created
    ma_file = reports_dir / "ma_events.json"
    if ma_file.exists():
        ma_file.unlink()


def test_company_mergers_and_acquisitions_with_events(ensure_reports_dir):
    """Test M&A detection from patent assignments."""
    sbir_awards = pd.DataFrame(
        {
            "company_name": ["Company A", "Company B", "Company C"],
            "award_amount": [100000, 200000, 300000],
        }
    )

    # Patent assignments showing Company A transferred to Company D
    uspto_assignments = pd.DataFrame(
        {
            "assignor_name": ["Company A", "Company A", "Company B"],
            "assignee_name": ["Company A", "Company D", "Company B"],
            "assignment_date": [date(2020, 1, 1), date(2021, 1, 1), date(2020, 1, 1)],
        }
    )

    ma_events = company_mergers_and_acquisitions(sbir_awards, uspto_assignments)

    assert len(ma_events) > 0
    assert any(
        event.acquiring_company_name == "Company D" and event.acquired_company_name == "Company A"
        for event in ma_events
    )


def test_company_mergers_and_acquisitions_no_events(ensure_reports_dir):
    """Test M&A detection returns empty when no M&A events found."""
    sbir_awards = pd.DataFrame(
        {
            "company_name": ["Company A", "Company B", "Company C"],
            "award_amount": [100000, 200000, 300000],
        }
    )

    # No ownership changes - assignor and assignee are the same
    uspto_assignments = pd.DataFrame(
        {
            "assignor_name": ["Company A", "Company B", "Company C"],
            "assignee_name": ["Company A", "Company B", "Company C"],
            "assignment_date": [date(2020, 1, 1), date(2021, 1, 1), date(2020, 1, 1)],
        }
    )

    ma_events = company_mergers_and_acquisitions(sbir_awards, uspto_assignments)

    assert len(ma_events) == 0
