"""Unit tests for award history extraction logic."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from sbir_etl.enrichers.award_history import (
    _build_history_from_df,
    get_company_history,
    get_pi_history,
)


pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# Helper to build a test DataFrame
# ---------------------------------------------------------------------------


def _make_awards_df(rows: list[dict]) -> pd.DataFrame:
    """Create a DataFrame with the columns expected by _build_history_from_df."""
    cols = [
        "_group_key", "Phase", "Agency", "Award Amount",
        "Proposal Award Date", "Award Title", "Program",
    ]
    for col in cols:
        for row in rows:
            row.setdefault(col, "")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# _build_history_from_df
# ---------------------------------------------------------------------------


class TestBuildHistoryFromDF:
    def test_basic_aggregation(self):
        df = _make_awards_df([
            {
                "_group_key": "ACME CORP",
                "Phase": "Phase I",
                "Agency": "DOD",
                "Award Amount": "150000",
                "Proposal Award Date": "2021-06-01",
                "Award Title": "Widget Research",
                "Program": "SBIR",
            },
            {
                "_group_key": "ACME CORP",
                "Phase": "Phase II",
                "Agency": "DOD",
                "Award Amount": "1000000",
                "Proposal Award Date": "2023-01-15",
                "Award Title": "Widget Prototype",
                "Program": "SBIR",
            },
        ])

        result = _build_history_from_df(df, "_group_key")

        assert "ACME CORP" in result
        entry = result["ACME CORP"]
        assert entry["total_awards"] == 2
        assert entry["total_funding"] == 1150000.0
        assert "Phase I" in entry["phases"]
        assert "Phase II" in entry["phases"]
        assert entry["agencies"] == ["DOD"]
        assert entry["earliest_date"] is not None
        assert entry["latest_date"] is not None
        assert len(entry["sample_titles"]) == 2

    def test_multiple_groups(self):
        df = _make_awards_df([
            {
                "_group_key": "ACME CORP",
                "Phase": "Phase I",
                "Agency": "DOD",
                "Award Amount": "100000",
                "Proposal Award Date": "2021-01-01",
                "Award Title": "Title A",
                "Program": "SBIR",
            },
            {
                "_group_key": "BETA INC",
                "Phase": "Phase I",
                "Agency": "NASA",
                "Award Amount": "200000",
                "Proposal Award Date": "2022-06-01",
                "Award Title": "Title B",
                "Program": "STTR",
            },
        ])

        result = _build_history_from_df(df, "_group_key")

        assert len(result) == 2
        assert result["ACME CORP"]["total_funding"] == 100000.0
        assert result["BETA INC"]["agencies"] == ["NASA"]

    def test_extra_set_cols(self):
        df = _make_awards_df([
            {
                "_group_key": "JANE DOE",
                "Phase": "Phase I",
                "Agency": "DOD",
                "Award Amount": "100000",
                "Proposal Award Date": "2021-01-01",
                "Award Title": "Research A",
                "Program": "SBIR",
                "Company": "Acme Corp",
            },
        ])

        result = _build_history_from_df(df, "_group_key", extra_set_cols=["Company"])

        assert "companies" in result["JANE DOE"]
        assert result["JANE DOE"]["companies"] == ["Acme Corp"]

    def test_empty_group_key_skipped(self):
        df = _make_awards_df([
            {
                "_group_key": "",
                "Phase": "Phase I",
                "Agency": "DOD",
                "Award Amount": "50000",
                "Award Title": "Phantom",
                "Program": "SBIR",
            },
        ])

        result = _build_history_from_df(df, "_group_key")
        assert len(result) == 0


# ---------------------------------------------------------------------------
# get_company_history (DuckDB path)
# ---------------------------------------------------------------------------


class TestGetCompanyHistory:
    def test_duckdb_path(self):
        awards = [{"Company": "Acme Corp"}, {"Company": "Beta Inc"}]

        mock_extractor = MagicMock()
        df = _make_awards_df([
            {
                "_group_key": "ACME CORP",
                "Phase": "Phase I",
                "Agency": "DOD",
                "Award Amount": "150000",
                "Proposal Award Date": "2021-06-01",
                "Award Title": "Widget Research",
                "Program": "SBIR",
            },
        ])
        mock_extractor.duckdb_client.execute_query_df.return_value = df

        result = get_company_history(
            awards, source=None, extractor=mock_extractor, table="sbir_awards"
        )

        assert "ACME CORP" in result
        assert result["ACME CORP"]["total_awards"] == 1
        mock_extractor.duckdb_client.execute_query_df.assert_called_once()

    def test_empty_awards_returns_empty(self):
        result = get_company_history([])
        assert result == {}

    def test_empty_df_returns_empty(self):
        awards = [{"Company": "Acme Corp"}]
        mock_extractor = MagicMock()
        mock_extractor.duckdb_client.execute_query_df.return_value = pd.DataFrame()

        result = get_company_history(
            awards, source=None, extractor=mock_extractor, table="sbir_awards"
        )
        assert result == {}

    def test_no_source_or_extractor_returns_empty(self):
        awards = [{"Company": "Acme Corp"}]
        result = get_company_history(awards)
        assert result == {}


# ---------------------------------------------------------------------------
# get_pi_history (DuckDB path)
# ---------------------------------------------------------------------------


class TestGetPIHistory:
    def test_duckdb_path(self):
        awards = [{"PI Name": "Jane Doe"}]

        mock_extractor = MagicMock()
        rows = [
            {
                "_group_key": "JANE DOE",
                "Company": "Acme Corp",
                "Phase": "Phase I",
                "Agency": "NASA",
                "Award Amount": "200000",
                "Proposal Award Date": "2022-03-01",
                "Award Title": "Space Widget",
                "Program": "SBIR",
            },
            {
                "_group_key": "JANE DOE",
                "Company": "Beta Inc",
                "Phase": "Phase II",
                "Agency": "NASA",
                "Award Amount": "750000",
                "Proposal Award Date": "2024-01-15",
                "Award Title": "Space Widget v2",
                "Program": "SBIR",
            },
        ]
        df = _make_awards_df(rows)
        mock_extractor.duckdb_client.execute_query_df.return_value = df

        result = get_pi_history(
            awards, source=None, extractor=mock_extractor, table="sbir_awards"
        )

        assert "JANE DOE" in result
        entry = result["JANE DOE"]
        assert entry["total_awards"] == 2
        assert entry["total_funding"] == 950000.0
        assert "companies" in entry
        assert sorted(entry["companies"]) == ["Acme Corp", "Beta Inc"]

    def test_empty_pi_names_returns_empty(self):
        result = get_pi_history([{"PI Name": ""}])
        assert result == {}

    def test_no_source_or_extractor_returns_empty(self):
        awards = [{"PI Name": "Jane Doe"}]
        result = get_pi_history(awards)
        assert result == {}
