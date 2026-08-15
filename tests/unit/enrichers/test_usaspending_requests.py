"""Request building for USAspending refresh."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sbir_etl.enrichers.usaspending.requests import (
    filter_by_window,
    has_identifier,
    stale_awards_to_requests,
)
from sbir_etl.exceptions import ValidationError


pytestmark = pytest.mark.fast


def test_nan_identifiers_become_none_not_the_string_nan() -> None:
    """A NaN cell must not reach the API as the literal string 'nan' (regression)."""

    frame = pd.DataFrame(
        [{"award_id": "A1", "UEI": np.nan, "Duns": None, "CAGE": "", "Contract": "W911-24-C-1"}]
    )

    requests = stale_awards_to_requests(frame)

    assert requests == [
        {"award_id": "A1", "uei": None, "duns": None, "cage": None, "piid": "W911-24-C-1"}
    ]


def test_identifiers_are_read_from_alternate_column_names() -> None:
    frame = pd.DataFrame([{"Award_ID": "A2", "recipient_uei": "ABC123456789"}])

    requests = stale_awards_to_requests(frame)

    assert requests[0]["award_id"] == "A2"
    assert requests[0]["uei"] == "ABC123456789"


def test_has_identifier_rejects_award_id_only_requests() -> None:
    assert not has_identifier({"award_id": "A1"})
    assert not has_identifier({"award_id": "A1", "uei": None, "piid": None})
    assert has_identifier({"award_id": "A1", "piid": "W911-24-C-1"})


def test_missing_award_id_column_raises() -> None:
    with pytest.raises(ValidationError):
        stale_awards_to_requests(pd.DataFrame([{"UEI": "ABC123456789"}]))


def test_empty_frame_returns_no_requests() -> None:
    assert stale_awards_to_requests(pd.DataFrame()) == []


def test_filter_by_window_restricts_to_the_requested_range() -> None:
    frame = pd.DataFrame(
        [
            {"award_id": "A1", "award_date": "2024-03-01"},
            {"award_id": "A2", "award_date": "2025-03-01"},
        ]
    )

    filtered = filter_by_window(frame, "2024-01-01:2024-12-31")

    assert filtered["award_id"].tolist() == ["A1"]


def test_filter_by_window_rejects_a_frame_with_no_date_column() -> None:
    with pytest.raises(ValidationError):
        filter_by_window(pd.DataFrame([{"award_id": "A1"}]), "2024-01-01:2024-12-31")


def test_filter_by_window_rejects_a_malformed_window() -> None:
    frame = pd.DataFrame([{"award_id": "A1", "award_date": "2024-03-01"}])
    with pytest.raises(ValidationError):
        filter_by_window(frame, "2024-01-01")
