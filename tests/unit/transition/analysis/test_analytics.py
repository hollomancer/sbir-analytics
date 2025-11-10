"""
Tests for src/transition/analysis/analytics.py

Tests the TransitionAnalytics module for computing KPIs and breakdowns
from transition detection outputs (award-level, company-level, by agency).
"""

import pandas as pd
import pytest

from src.transition.analysis.analytics import (
    RateResult,
    TransitionAnalytics,
    _company_id_series,
    _first_col,
    _norm_str,
)


pytestmark = pytest.mark.fast



@pytest.fixture
def analytics():
    """Default TransitionAnalytics instance."""
    return TransitionAnalytics(score_threshold=0.60)


@pytest.fixture
def sample_awards():
    """Sample awards DataFrame."""
    return pd.DataFrame(
        {
            "award_id": ["AWD001", "AWD002", "AWD003", "AWD004", "AWD005"],
            "UEI": ["UEI001", "UEI002", "UEI003", "UEI001", "UEI004"],
            "company": ["Acme Corp", "Beta Inc", "Gamma LLC", "Acme Corp", "Delta Tech"],
            "Phase": ["II", "I", "II", "I", "II"],
            "Agency": ["DOD", "NASA", "DOD", "DOD", "NSF"],
            "completion_date": [
                "2023-01-01",
                "2023-02-01",
                "2023-03-01",
                "2023-04-01",
                "2023-05-01",
            ],
        }
    )


@pytest.fixture
def sample_transitions():
    """Sample transitions DataFrame."""
    return pd.DataFrame(
        {
            "award_id": ["AWD001", "AWD001", "AWD003", "AWD005"],
            "contract_id": ["CTR001", "CTR002", "CTR003", "CTR004"],
            "score": [0.85, 0.70, 0.55, 0.75],  # AWD003 below threshold
        }
    )


@pytest.fixture
def sample_contracts():
    """Sample contracts DataFrame."""
    return pd.DataFrame(
        {
            "contract_id": ["CTR001", "CTR002", "CTR003", "CTR004"],
            "action_date": ["2023-06-01", "2023-07-01", "2023-08-01", "2023-09-01"],
        }
    )


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_norm_str_normal_string(self):
        """Test _norm_str with normal string."""
        result = _norm_str("  Test String  ")
        assert result == "Test String"

    def test_norm_str_number(self):
        """Test _norm_str with number."""
        result = _norm_str(123)
        assert result == "123"

    def test_norm_str_none(self):
        """Test _norm_str with None."""
        result = _norm_str(None)
        assert result == ""

    def test_first_col_exact_match(self):
        """Test _first_col finds exact column name match."""
        df = pd.DataFrame({"award_id": [1], "other": [2]})
        result = _first_col(df, ["award_id", "Award ID"])
        assert result == "award_id"

    def test_first_col_case_insensitive(self):
        """Test _first_col finds case-insensitive match."""
        df = pd.DataFrame({"Award_ID": [1], "other": [2]})
        result = _first_col(df, ["award_id", "Award ID"])
        assert result == "Award_ID"

    def test_first_col_no_match(self):
        """Test _first_col returns None when no match."""
        df = pd.DataFrame({"other": [1]})
        result = _first_col(df, ["award_id", "Award ID"])
        assert result is None

    def test_first_col_priority_order(self):
        """Test _first_col returns first matching candidate."""
        df = pd.DataFrame({"award_id": [1], "Award ID": [2]})
        result = _first_col(df, ["award_id", "Award ID"])
        assert result == "award_id"  # First in candidates list


class TestCompanyIdSeries:
    """Tests for _company_id_series function."""

    def test_company_id_series_uei_priority(self):
        """Test company ID uses UEI when available."""
        df = pd.DataFrame(
            {
                "UEI": ["UEI001", "UEI002"],
                "Duns": ["DUNS001", "DUNS002"],
                "company": ["Acme", "Beta"],
            }
        )

        result = _company_id_series(df)

        assert result.iloc[0] == "uei:UEI001"
        assert result.iloc[1] == "uei:UEI002"

    def test_company_id_series_duns_fallback(self):
        """Test company ID falls back to DUNS when UEI missing."""
        df = pd.DataFrame(
            {
                "UEI": ["", "UEI002"],
                "Duns": ["DUNS001", "DUNS002"],
                "company": ["Acme", "Beta"],
            }
        )

        result = _company_id_series(df)

        assert result.iloc[0] == "duns:DUNS001"
        assert result.iloc[1] == "uei:UEI002"

    def test_company_id_series_name_fallback(self):
        """Test company ID falls back to company name when IDs missing."""
        df = pd.DataFrame(
            {
                "UEI": ["", ""],
                "Duns": ["", ""],
                "company": ["Acme Corp", "Beta Inc"],
            }
        )

        result = _company_id_series(df)

        assert result.iloc[0] == "name:acme corp"
        assert result.iloc[1] == "name:beta inc"

    def test_company_id_series_row_index_last_resort(self):
        """Test company ID uses row index as last resort."""
        df = pd.DataFrame({"other_col": [1, 2]})

        result = _company_id_series(df)

        assert result.iloc[0] == "row:0"
        assert result.iloc[1] == "row:1"

    def test_company_id_series_handles_none_values(self):
        """Test company ID handles None/NaN values correctly."""
        df = pd.DataFrame(
            {
                "UEI": ["None", "nan", "UEI003"],
                "company": ["Acme", "Beta", "Gamma"],
            }
        )

        result = _company_id_series(df)

        # None and nan should fall through to name
        assert result.iloc[0] == "name:acme"
        assert result.iloc[1] == "name:beta"
        assert result.iloc[2] == "uei:UEI003"


class TestRateResult:
    """Tests for RateResult dataclass."""

    def test_rate_result_creation(self):
        """Test creating a RateResult."""
        result = RateResult(numerator=75, denominator=100, rate=0.75)

        assert result.numerator == 75
        assert result.denominator == 100
        assert result.rate == 0.75

    def test_rate_result_to_dict(self):
        """Test RateResult serialization to dict."""
        result = RateResult(numerator=75, denominator=100, rate=0.75)

        d = result.to_dict()

        assert d["numerator"] == 75
        assert d["denominator"] == 100
        assert d["rate"] == 0.75


class TestTransitionAnalyticsInitialization:
    """Tests for TransitionAnalytics initialization."""

    def test_initialization_default(self):
        """Test initialization with default threshold."""
        analytics = TransitionAnalytics()

        assert analytics.score_threshold == 0.60

    def test_initialization_custom_threshold(self):
        """Test initialization with custom threshold."""
        analytics = TransitionAnalytics(score_threshold=0.75)

        assert analytics.score_threshold == 0.75


class TestComputeAwardTransitionRate:
    """Tests for compute_award_transition_rate method."""

    def test_compute_award_transition_rate_basic(
        self, analytics, sample_awards, sample_transitions
    ):
        """Test computing award transition rate."""
        result = analytics.compute_award_transition_rate(sample_awards, sample_transitions)

        # AWD001 (score 0.85, 0.70) and AWD005 (score 0.75) transition
        # AWD003 has score 0.55 (below 0.60 threshold), so doesn't count
        # 2 out of 5 awards transitioned
        assert result.numerator == 2
        assert result.denominator == 5
        assert result.rate == 0.4

    def test_compute_award_transition_rate_empty_awards(self, analytics):
        """Test award transition rate with empty awards."""
        awards = pd.DataFrame(columns=["award_id"])
        transitions = pd.DataFrame(columns=["award_id", "score"])

        result = analytics.compute_award_transition_rate(awards, transitions)

        assert result.numerator == 0
        assert result.denominator == 0
        assert result.rate == 0.0

    def test_compute_award_transition_rate_no_transitions(self, analytics, sample_awards):
        """Test award transition rate with no transitions."""
        transitions = pd.DataFrame(columns=["award_id", "score"])

        result = analytics.compute_award_transition_rate(sample_awards, transitions)

        assert result.numerator == 0
        assert result.denominator == 5
        assert result.rate == 0.0

    def test_compute_award_transition_rate_all_transitioned(self, analytics):
        """Test award transition rate when all awards transitioned."""
        awards = pd.DataFrame({"award_id": ["AWD001", "AWD002", "AWD003"]})
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "score": [0.85, 0.75, 0.65],
            }
        )

        result = analytics.compute_award_transition_rate(awards, transitions)

        assert result.numerator == 3
        assert result.denominator == 3
        assert result.rate == 1.0

    def test_compute_award_transition_rate_filters_by_threshold(self, analytics):
        """Test award transition rate filters by score threshold."""
        awards = pd.DataFrame({"award_id": ["AWD001", "AWD002", "AWD003"]})
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "score": [0.85, 0.55, 0.50],  # Only AWD001 above 0.60
            }
        )

        result = analytics.compute_award_transition_rate(awards, transitions)

        assert result.numerator == 1
        assert result.denominator == 3
        assert result.rate == pytest.approx(0.333, rel=0.01)


class TestComputeCompanyTransitionRate:
    """Tests for compute_company_transition_rate method."""

    def test_compute_company_transition_rate_basic(
        self, analytics, sample_awards, sample_transitions
    ):
        """Test computing company transition rate."""
        result, company_df = analytics.compute_company_transition_rate(
            sample_awards, sample_transitions
        )

        # Companies: UEI001 (Acme), UEI002 (Beta), UEI003 (Gamma), UEI004 (Delta)
        # Transitioned: UEI001 (AWD001), UEI004 (AWD005)
        # 2 out of 4 companies transitioned
        assert result.numerator == 2
        assert result.denominator == 4
        assert result.rate == 0.5

        # Check company DataFrame
        assert len(company_df) == 4
        assert "company_id" in company_df.columns
        assert "total_awards" in company_df.columns
        assert "transitioned_awards" in company_df.columns
        assert "transitioned" in company_df.columns

    def test_compute_company_transition_rate_empty_awards(self, analytics):
        """Test company transition rate with empty awards."""
        awards = pd.DataFrame(columns=["award_id", "UEI"])
        transitions = pd.DataFrame(columns=["award_id", "score"])

        result, company_df = analytics.compute_company_transition_rate(awards, transitions)

        assert result.numerator == 0
        assert result.denominator == 0
        assert result.rate == 0.0
        assert len(company_df) == 0

    def test_compute_company_transition_rate_multiple_awards_per_company(self, analytics):
        """Test company rate with multiple awards per company."""
        awards = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003", "AWD004"],
                "UEI": ["UEI001", "UEI001", "UEI002", "UEI002"],  # 2 companies, 2 awards each
            }
        )
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001"],  # Only one award from UEI001 transitioned
                "score": [0.85],
            }
        )

        result, company_df = analytics.compute_company_transition_rate(awards, transitions)

        # 1 out of 2 companies transitioned
        assert result.numerator == 1
        assert result.denominator == 2
        assert result.rate == 0.5

        # UEI001 should have 2 total awards, 1 transitioned
        uei001_row = company_df[company_df["company_id"] == "uei:UEI001"].iloc[0]
        assert uei001_row["total_awards"] == 2
        assert uei001_row["transitioned_awards"] == 1
        assert uei001_row["transitioned"] is True

    def test_compute_company_transition_rate_sorted(
        self, analytics, sample_awards, sample_transitions
    ):
        """Test company DataFrame is sorted by transition status and total awards."""
        _, company_df = analytics.compute_company_transition_rate(sample_awards, sample_transitions)

        # First rows should be companies that transitioned
        assert company_df.iloc[0]["transitioned"] is True
        # Within transitioned, should be sorted by total_awards descending


class TestComputePhaseEffectiveness:
    """Tests for compute_phase_effectiveness method."""

    def test_compute_phase_effectiveness_basic(self, analytics, sample_awards, sample_transitions):
        """Test computing phase effectiveness."""
        result = analytics.compute_phase_effectiveness(sample_awards, sample_transitions)

        # Phase I: AWD002, AWD004 (AWD001 transitions, AWD002 doesn't - but AWD001 is Phase II)
        # Phase II: AWD001, AWD003, AWD005
        # Need to check which actually transitioned above threshold
        # AWD001 (Phase II) - transitions (0.85, 0.70)
        # AWD005 (Phase II) - transitions (0.75)
        # AWD003 (Phase II) - score 0.55 (below threshold)

        assert len(result) > 0
        assert "phase" in result.columns
        assert "total_awards" in result.columns
        assert "transitioned_awards" in result.columns
        assert "rate" in result.columns

    def test_compute_phase_effectiveness_no_phase_column(self, analytics, sample_transitions):
        """Test phase effectiveness when Phase column missing."""
        awards = pd.DataFrame({"award_id": ["AWD001", "AWD002"]})

        result = analytics.compute_phase_effectiveness(awards, sample_transitions)

        assert len(result) == 0

    def test_compute_phase_effectiveness_normalizes_phase_names(self, analytics):
        """Test phase effectiveness normalizes phase names."""
        awards = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003", "AWD004"],
                "Phase": ["Phase I", "phase i", "PHASE II", "Phase II"],
            }
        )
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD003"],
                "score": [0.85, 0.75],
            }
        )

        result = analytics.compute_phase_effectiveness(awards, transitions)

        # Should have normalized to "I" and "II"
        phases = set(result["phase"].tolist())
        assert "I" in phases or "II" in phases


class TestComputeByAgency:
    """Tests for compute_by_agency method."""

    def test_compute_by_agency_basic(self, analytics, sample_awards, sample_transitions):
        """Test computing transition rate by agency."""
        result = analytics.compute_by_agency(sample_awards, sample_transitions)

        assert len(result) > 0
        assert "agency" in result.columns
        assert "total_awards" in result.columns
        assert "transitioned_awards" in result.columns
        assert "rate" in result.columns

        # DOD should have AWD001, AWD003, AWD004
        # AWD001 transitions, AWD003 doesn't (below threshold)
        dod_row = result[result["agency"] == "DOD"]
        if not dod_row.empty:
            assert dod_row.iloc[0]["total_awards"] == 3

    def test_compute_by_agency_no_agency_column(self, analytics, sample_transitions):
        """Test agency breakdown when Agency column missing."""
        awards = pd.DataFrame({"award_id": ["AWD001", "AWD002"]})

        result = analytics.compute_by_agency(awards, sample_transitions)

        assert len(result) == 0

    def test_compute_by_agency_normalizes_names(self, analytics):
        """Test agency breakdown normalizes agency names."""
        awards = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "Agency": ["  DOD  ", "dod", "NASA"],
            }
        )
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "score": [0.85, 0.75],
            }
        )

        result = analytics.compute_by_agency(awards, transitions)

        # DOD should be normalized to uppercase and combined
        dod_row = result[result["agency"] == "DOD"]
        assert not dod_row.empty
        assert dod_row.iloc[0]["total_awards"] == 2

    def test_compute_by_agency_sorted_by_rate(self, analytics):
        """Test agency breakdown is sorted by rate and total awards."""
        awards = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003", "AWD004"],
                "Agency": ["DOD", "NASA", "DOD", "NSF"],
            }
        )
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],  # Both DOD and NASA have 1 transition
                "score": [0.85, 0.75],
            }
        )

        result = analytics.compute_by_agency(awards, transitions)

        # Should be sorted by rate descending
        assert result.iloc[0]["rate"] >= result.iloc[1]["rate"]


class TestComputeAvgTimeToTransitionByAgency:
    """Tests for compute_avg_time_to_transition_by_agency method."""

    def test_compute_avg_time_to_transition_basic(
        self, analytics, sample_awards, sample_transitions, sample_contracts
    ):
        """Test computing average time to transition by agency."""
        result = analytics.compute_avg_time_to_transition_by_agency(
            sample_awards, sample_transitions, sample_contracts
        )

        # Should have computed time deltas
        if not result.empty:
            assert "agency" in result.columns
            assert "n" in result.columns
            assert "avg_days" in result.columns
            assert "p50_days" in result.columns
            assert "p90_days" in result.columns

    def test_compute_avg_time_to_transition_no_contracts(
        self, analytics, sample_awards, sample_transitions
    ):
        """Test time to transition with no contracts DataFrame."""
        result = analytics.compute_avg_time_to_transition_by_agency(
            sample_awards, sample_transitions, None
        )

        assert len(result) == 0

    def test_compute_avg_time_to_transition_missing_columns(self, analytics):
        """Test time to transition when required columns missing."""
        awards = pd.DataFrame({"award_id": ["AWD001"]})  # Missing agency and dates
        transitions = pd.DataFrame({"award_id": ["AWD001"], "contract_id": ["CTR001"]})
        contracts = pd.DataFrame({"contract_id": ["CTR001"]})  # Missing date

        result = analytics.compute_avg_time_to_transition_by_agency(awards, transitions, contracts)

        assert len(result) == 0

    def test_compute_avg_time_to_transition_filters_negative_days(self, analytics):
        """Test time to transition filters out negative days (contract before award)."""
        awards = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "Agency": ["DOD", "NASA"],
                "completion_date": ["2023-06-01", "2023-06-01"],
            }
        )
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
                "score": [0.85, 0.75],
            }
        )
        contracts = pd.DataFrame(
            {
                "contract_id": ["CTR001", "CTR002"],
                "action_date": ["2023-07-01", "2023-05-01"],  # CTR002 before award (negative)
            }
        )

        result = analytics.compute_avg_time_to_transition_by_agency(awards, transitions, contracts)

        # Should only include AWD001 (positive days)
        if not result.empty:
            assert result["n"].sum() <= 1  # At most 1 valid transition


class TestSummarize:
    """Tests for summarize method."""

    def test_summarize_basic(self, analytics, sample_awards, sample_transitions, sample_contracts):
        """Test generating summary dict."""
        summary = analytics.summarize(sample_awards, sample_transitions, sample_contracts)

        assert "score_threshold" in summary
        assert summary["score_threshold"] == 0.60

        assert "award_transition_rate" in summary
        assert "numerator" in summary["award_transition_rate"]
        assert "denominator" in summary["award_transition_rate"]
        assert "rate" in summary["award_transition_rate"]

        assert "company_transition_rate" in summary

    def test_summarize_includes_phase_effectiveness(
        self, analytics, sample_awards, sample_transitions
    ):
        """Test summary includes phase effectiveness."""
        summary = analytics.summarize(sample_awards, sample_transitions)

        assert "phase_effectiveness" in summary
        assert isinstance(summary["phase_effectiveness"], list)

    def test_summarize_includes_top_agencies(self, analytics, sample_awards, sample_transitions):
        """Test summary includes top agencies."""
        summary = analytics.summarize(sample_awards, sample_transitions)

        assert "top_agencies" in summary
        assert isinstance(summary["top_agencies"], list)
        # Should limit to top 10
        assert len(summary["top_agencies"]) <= 10

    def test_summarize_with_contracts_includes_time_to_transition(
        self, analytics, sample_awards, sample_transitions, sample_contracts
    ):
        """Test summary includes time-to-transition when contracts provided."""
        summary = analytics.summarize(sample_awards, sample_transitions, sample_contracts)

        assert "avg_time_to_transition_by_agency" in summary

    def test_summarize_without_contracts(self, analytics, sample_awards, sample_transitions):
        """Test summary without contracts DataFrame."""
        summary = analytics.summarize(sample_awards, sample_transitions, contracts_df=None)

        # Should still work but may not include time-to-transition
        assert "award_transition_rate" in summary
        assert "company_transition_rate" in summary


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_awards_with_duplicate_ids(self, analytics):
        """Test handling awards with duplicate IDs."""
        awards = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD001", "AWD002"],  # Duplicate AWD001
                "UEI": ["UEI001", "UEI001", "UEI002"],
            }
        )
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "score": [0.85],
            }
        )

        result = analytics.compute_award_transition_rate(awards, transitions)

        # Should deduplicate award IDs
        assert result.denominator == 2  # AWD001, AWD002

    def test_transitions_without_score_column(self, analytics, sample_awards):
        """Test transitions without score column uses all transitions."""
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                # No score column
            }
        )

        # Should not crash, and should count all transitions
        result = analytics.compute_award_transition_rate(sample_awards, transitions)

        assert result.numerator > 0

    def test_awards_with_missing_values(self, analytics):
        """Test handling awards with missing/null values."""
        awards = pd.DataFrame(
            {
                "award_id": ["AWD001", None, "AWD003"],
                "UEI": ["UEI001", "UEI002", None],
            }
        )
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "score": [0.85],
            }
        )

        # Should handle nulls gracefully
        result = analytics.compute_award_transition_rate(awards, transitions)

        assert result.denominator > 0

    def test_empty_dataframes_all_methods(self, analytics):
        """Test all methods handle empty DataFrames gracefully."""
        empty_awards = pd.DataFrame(columns=["award_id", "UEI", "Phase", "Agency"])
        empty_transitions = pd.DataFrame(columns=["award_id", "score"])
        empty_contracts = pd.DataFrame(columns=["contract_id", "action_date"])

        # All methods should return empty/zero results without crashing
        assert analytics.compute_award_transition_rate(empty_awards, empty_transitions).rate == 0.0
        result, df = analytics.compute_company_transition_rate(empty_awards, empty_transitions)
        assert result.rate == 0.0
        assert len(df) == 0

        assert len(analytics.compute_phase_effectiveness(empty_awards, empty_transitions)) == 0
        assert len(analytics.compute_by_agency(empty_awards, empty_transitions)) == 0
        assert (
            len(
                analytics.compute_avg_time_to_transition_by_agency(
                    empty_awards, empty_transitions, empty_contracts
                )
            )
            == 0
        )

    def test_case_insensitive_column_matching(self, analytics):
        """Test analytics handles case-insensitive column names."""
        awards = pd.DataFrame(
            {
                "AWARD_ID": ["AWD001", "AWD002"],  # Uppercase
                "uei": ["UEI001", "UEI002"],  # Lowercase
                "Phase": ["I", "II"],  # Mixed
            }
        )
        transitions = pd.DataFrame(
            {
                "Award_ID": ["AWD001"],  # Different case
                "Score": [0.85],  # Capitalized
            }
        )

        # Should handle case variations
        result = analytics.compute_award_transition_rate(awards, transitions)

        assert result.denominator == 2
        assert result.numerator == 1

    def test_non_numeric_scores_handled(self, analytics, sample_awards):
        """Test handling non-numeric score values."""
        transitions = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "score": ["invalid", 0.85, "error"],  # Non-numeric values
            }
        )

        # Should handle non-numeric scores via pd.to_numeric with errors='coerce'
        result = analytics.compute_award_transition_rate(sample_awards, transitions)

        # Only AWD002 with score 0.85 should count
        assert result.numerator == 1
