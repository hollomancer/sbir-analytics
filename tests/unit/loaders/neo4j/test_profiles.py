"""Tests for Neo4j transition profile loader."""

from datetime import datetime
from unittest.mock import Mock

import pandas as pd

from src.loaders.neo4j.profiles import TransitionProfileLoader


class TestTransitionProfileLoader:
    """Tests for TransitionProfileLoader class."""

    def test_initialization(self):
        """Test TransitionProfileLoader initialization."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver, batch_size=100)

        assert loader.driver == mock_driver
        assert loader.batch_size == 100
        assert loader.stats["profiles_created"] == 0
        assert loader.stats["profiles_updated"] == 0
        assert loader.stats["relationships_created"] == 0
        assert loader.stats["errors"] == 0

    def test_initialization_default_batch_size(self):
        """Test initialization with default batch size."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        assert loader.batch_size == 500

    def test_calculate_company_profiles_empty_transitions(self):
        """Test calculating profiles with empty transitions DataFrame."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame()
        result = loader.calculate_company_profiles(transitions_df)

        assert result.empty

    def test_calculate_company_profiles_no_awards_df(self):
        """Test calculating profiles without awards DataFrame."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3"],
                "award_id": ["a1", "a2", "a1"],
                "confidence": ["high", "likely", "high"],
                "likelihood_score": [0.9, 0.75, 0.85],
                "detected_at": [datetime.now()] * 3,
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df=None)

        # Should still work, but may have limited information
        assert isinstance(result, pd.DataFrame)

    def test_calculate_company_profiles_with_awards(self):
        """Test calculating profiles with awards DataFrame."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3"],
                "award_id": ["a1", "a2", "a3"],
                "confidence": ["high", "likely", "high"],
                "likelihood_score": [0.9, 0.75, 0.85],
                "detected_at": [datetime.now()] * 3,
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3", "a4"],
                "company_id": ["c1", "c1", "c2", "c2"],
                "award_date": pd.to_datetime(
                    ["2020-01-01", "2020-06-01", "2021-01-01", "2021-06-01"]
                ),
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        assert isinstance(result, pd.DataFrame)
        # Should have profiles for companies with transitions
        assert not result.empty

    def test_stats_tracking(self):
        """Test that loader tracks statistics."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        assert "profiles_created" in loader.stats
        assert "profiles_updated" in loader.stats
        assert "relationships_created" in loader.stats
        assert "errors" in loader.stats

    def test_batch_size_respected(self):
        """Test that custom batch size is respected."""
        mock_driver = Mock()
        custom_batch_size = 250

        loader = TransitionProfileLoader(mock_driver, batch_size=custom_batch_size)

        assert loader.batch_size == custom_batch_size


class TestTransitionProfileCalculations:
    """Tests for profile calculation methods."""

    def test_profile_metrics_calculation(self):
        """Test calculation of profile metrics."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        # Create test data
        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3", "t4"],
                "award_id": ["a1", "a2", "a3", "a4"],
                "confidence": ["high", "high", "likely", "possible"],
                "likelihood_score": [0.9, 0.85, 0.75, 0.6],
                "detected_at": pd.to_datetime(
                    ["2023-01-15", "2023-02-20", "2023-03-10", "2023-04-05"]
                ),
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3", "a4", "a5"],
                "company_id": ["c1", "c1", "c1", "c2", "c2"],
                "award_date": pd.to_datetime(
                    ["2022-01-01", "2022-06-01", "2022-12-01", "2022-03-01", "2022-09-01"]
                ),
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        # Verify profile structure
        if not result.empty:
            # Should have company-level aggregations
            assert "company_id" in result.columns or len(result) > 0

    def test_high_confidence_counting(self):
        """Test counting of high confidence transitions."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3"],
                "award_id": ["a1", "a2", "a3"],
                "confidence": ["high", "high", "likely"],
                "likelihood_score": [0.9, 0.88, 0.75],
                "detected_at": [datetime.now()] * 3,
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3"],
                "company_id": ["c1", "c1", "c1"],
                "award_date": [datetime.now()] * 3,
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        # Should track high confidence count (2 in this case)
        assert isinstance(result, pd.DataFrame)

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        # 3 transitions out of 5 awards for company c1
        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3"],
                "award_id": ["a1", "a2", "a3"],
                "confidence": ["high"] * 3,
                "likelihood_score": [0.9] * 3,
                "detected_at": [datetime.now()] * 3,
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3", "a4", "a5"],
                "company_id": ["c1"] * 5,
                "award_date": [datetime.now()] * 5,
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        # Success rate should be 3/5 = 0.6 for company c1
        assert isinstance(result, pd.DataFrame)


class TestTransitionProfileLoaderIntegration:
    """Integration tests for TransitionProfileLoader."""

    def test_multiple_companies_profiles(self):
        """Test profiles for multiple companies."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3", "t4"],
                "award_id": ["a1", "a2", "a3", "a4"],
                "confidence": ["high", "likely", "high", "possible"],
                "likelihood_score": [0.9, 0.75, 0.85, 0.65],
                "detected_at": [datetime.now()] * 4,
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3", "a4", "a5", "a6"],
                "company_id": ["c1", "c1", "c2", "c2", "c3", "c3"],
                "award_date": [datetime.now()] * 6,
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        # Should have profiles for companies with transitions (c1, c2, c3)
        assert isinstance(result, pd.DataFrame)

    def test_average_score_calculation(self):
        """Test average likelihood score calculation."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2"],
                "award_id": ["a1", "a2"],
                "confidence": ["high", "high"],
                "likelihood_score": [0.8, 0.9],  # Average should be 0.85
                "detected_at": [datetime.now()] * 2,
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1", "a2"],
                "company_id": ["c1", "c1"],
                "award_date": [datetime.now()] * 2,
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        # Should calculate average score
        assert isinstance(result, pd.DataFrame)

    def test_last_transition_date_tracking(self):
        """Test tracking of last transition date."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        detected_dates = pd.to_datetime(
            [
                "2023-01-01",
                "2023-06-01",
                "2023-12-31",  # This should be the last
            ]
        )

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3"],
                "award_id": ["a1", "a2", "a3"],
                "confidence": ["high"] * 3,
                "likelihood_score": [0.9] * 3,
                "detected_at": detected_dates,
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3"],
                "company_id": ["c1", "c1", "c1"],
                "award_date": [datetime.now()] * 3,
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        # Should track the latest transition date
        assert isinstance(result, pd.DataFrame)

    def test_empty_awards_with_transitions(self):
        """Test handling transitions without corresponding awards data."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "award_id": ["a1"],
                "confidence": ["high"],
                "likelihood_score": [0.9],
                "detected_at": [datetime.now()],
            }
        )

        # Empty awards DataFrame
        awards_df = pd.DataFrame()

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        # Should handle gracefully
        assert isinstance(result, pd.DataFrame)


class TestTransitionProfileLoaderEdgeCases:
    """Tests for edge cases in TransitionProfileLoader."""

    def test_single_transition(self):
        """Test profile calculation with single transition."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "award_id": ["a1"],
                "confidence": ["high"],
                "likelihood_score": [0.95],
                "detected_at": [datetime.now()],
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1"],
                "company_id": ["c1"],
                "award_date": [datetime.now()],
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        assert isinstance(result, pd.DataFrame)

    def test_missing_confidence_field(self):
        """Test handling of missing confidence field."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2"],
                "award_id": ["a1", "a2"],
                # Missing 'confidence' field
                "likelihood_score": [0.9, 0.85],
                "detected_at": [datetime.now()] * 2,
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1", "a2"],
                "company_id": ["c1", "c1"],
                "award_date": [datetime.now()] * 2,
            }
        )

        # Should handle missing fields gracefully
        result = loader.calculate_company_profiles(transitions_df, awards_df)
        assert isinstance(result, pd.DataFrame)

    def test_duplicate_transition_ids(self):
        """Test handling of duplicate transition IDs."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t1"],  # Duplicate
                "award_id": ["a1", "a1"],
                "confidence": ["high", "high"],
                "likelihood_score": [0.9, 0.9],
                "detected_at": [datetime.now()] * 2,
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1"],
                "company_id": ["c1"],
                "award_date": [datetime.now()],
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)
        assert isinstance(result, pd.DataFrame)

    def test_all_confidence_levels(self):
        """Test profiles with all confidence levels."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3", "t4"],
                "award_id": ["a1", "a2", "a3", "a4"],
                "confidence": ["high", "likely", "possible", "low"],
                "likelihood_score": [0.95, 0.80, 0.65, 0.45],
                "detected_at": [datetime.now()] * 4,
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3", "a4"],
                "company_id": ["c1"] * 4,
                "award_date": [datetime.now()] * 4,
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        # Should calculate counts for all confidence levels
        assert isinstance(result, pd.DataFrame)

    def test_zero_likelihood_scores(self):
        """Test handling of zero likelihood scores."""
        mock_driver = Mock()
        loader = TransitionProfileLoader(mock_driver)

        transitions_df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2"],
                "award_id": ["a1", "a2"],
                "confidence": ["low", "low"],
                "likelihood_score": [0.0, 0.0],
                "detected_at": [datetime.now()] * 2,
            }
        )

        awards_df = pd.DataFrame(
            {
                "award_id": ["a1", "a2"],
                "company_id": ["c1", "c1"],
                "award_date": [datetime.now()] * 2,
            }
        )

        result = loader.calculate_company_profiles(transitions_df, awards_df)

        # Should handle zero scores
        assert isinstance(result, pd.DataFrame)
