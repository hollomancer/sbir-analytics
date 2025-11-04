"""
Unit tests for TransitionScorer - transition likelihood scoring algorithm.

Tests all individual scoring methods and composite score computation.
"""

from datetime import date

import pytest


pytestmark = pytest.mark.fast

from src.models.transition_models import CompetitionType, ConfidenceLevel, FederalContract
from src.transition.detection.scoring import TransitionScorer


@pytest.fixture
def default_config() -> dict:
    """Default configuration for TransitionScorer tests."""
    return {
        "base_score": 0.15,
        "confidence_thresholds": {"high": 0.85, "likely": 0.65, "possible": 0.00},
        "scoring": {
            "agency_continuity": {
                "enabled": True,
                "weight": 0.25,
                "same_agency_bonus": 0.25,
                "cross_service_bonus": 0.125,
                "different_dept_bonus": 0.05,
            },
            "timing_proximity": {
                "enabled": True,
                "weight": 0.20,
                "windows": [
                    {"range": [0, 90], "score": 1.0},  # 0-3 months
                    {"range": [91, 365], "score": 0.75},  # 3-12 months
                    {"range": [366, 730], "score": 0.5},  # 12-24 months
                ],
                "beyond_window_penalty": 0.0,
            },
            "competition_type": {
                "enabled": True,
                "weight": 0.20,
                "sole_source_bonus": 0.20,
                "limited_competition_bonus": 0.10,
                "full_and_open_bonus": 0.0,
            },
            "patent_signal": {
                "enabled": True,
                "weight": 0.15,
                "has_patent_bonus": 0.05,
                "patent_pre_contract_bonus": 0.03,
                "patent_topic_match_bonus": 0.02,
                "patent_similarity_threshold": 0.7,
            },
            "cet_alignment": {
                "enabled": True,
                "weight": 0.10,
                "same_cet_area_bonus": 0.05,
                "related_cet_area_bonus": 0.02,
            },
            "text_similarity": {"enabled": False, "weight": 0.0},
        },
    }


@pytest.fixture
def scorer(default_config) -> TransitionScorer:
    """Create TransitionScorer with default configuration."""
    return TransitionScorer(default_config)


class TestAgencyScoring:
    """Tests for agency continuity scoring."""

    def test_same_agency_bonus(self, scorer):
        """Same agency should provide maximum agency bonus."""
        award_data = {"agency": "DOD"}
        contract = FederalContract(contract_id="TEST-001", agency="DOD")
        signal = scorer.score_agency_continuity(award_data=award_data, contract=contract)

        assert signal.same_agency is True
        # same_agency_bonus (0.25) * weight (0.25) = 0.0625
        assert signal.agency_score == pytest.approx(0.0625, abs=0.001)

    def test_different_agency_same_department(self, scorer):
        """Different agency, same department should provide cross-service bonus."""
        award_data = {"agency": "Army", "department": "DOD"}
        contract = FederalContract(contract_id="TEST-002", agency="Navy", sub_agency="DOD")
        signal = scorer.score_agency_continuity(award_data=award_data, contract=contract)

        assert signal.same_agency is False
        assert signal.same_department is True
        # cross_service_bonus (0.125) * weight (0.25) = 0.03125
        assert signal.agency_score == pytest.approx(0.03125, abs=0.001)

    def test_different_department(self, scorer):
        """Different department should provide minimal bonus."""
        award_data = {"agency": "DOD", "department": "DOD"}
        contract = FederalContract(contract_id="TEST-003", agency="NASA", sub_agency="NASA")
        signal = scorer.score_agency_continuity(award_data=award_data, contract=contract)

        assert signal.same_agency is False
        assert signal.same_department is False
        # different_dept_bonus (0.05) * weight (0.25) = 0.0125
        assert signal.agency_score == pytest.approx(0.0125, abs=0.001)

    def test_case_insensitive_matching(self, scorer):
        """Agency matching should be case-insensitive."""
        award_data = {"agency": "dod"}
        contract = FederalContract(contract_id="TEST-004", agency="DOD")
        signal = scorer.score_agency_continuity(award_data=award_data, contract=contract)

        assert signal.same_agency is True

    def test_missing_agency_data(self, scorer):
        """Missing agency data should return zero score."""
        award_data = {}
        contract = FederalContract(contract_id="TEST-005", agency="DOD")
        signal = scorer.score_agency_continuity(award_data=award_data, contract=contract)

        assert signal.same_agency is False
        assert signal.agency_score == 0.0


class TestTimingScoring:
    """Tests for timing proximity scoring."""

    def test_immediate_timing(self, scorer):
        """Contract within 0-3 months should get maximum timing score."""
        award_data = {"completion_date": date(2023, 1, 1)}
        contract = FederalContract(contract_id="TEST-006", start_date=date(2023, 2, 1))  # 31 days later

        signal = scorer.score_timing_proximity(award_data=award_data, contract=contract)

        assert signal.days_between_award_and_contract == 31
        assert signal.months_between_award_and_contract == pytest.approx(1.0, abs=0.1)
        # window score (1.0) * weight (0.20) = 0.20
        assert signal.timing_score == pytest.approx(0.20, abs=0.001)

    def test_medium_timing(self, scorer):
        """Contract within 3-12 months should get reduced score."""
        award_data = {"completion_date": date(2023, 1, 1)}
        contract = FederalContract(contract_id="TEST-007", start_date=date(2023, 7, 1))  # ~180 days later

        signal = scorer.score_timing_proximity(award_data=award_data, contract=contract)

        assert 180 <= signal.days_between_award_and_contract <= 182
        # window score (0.75) * weight (0.20) = 0.15
        assert signal.timing_score == pytest.approx(0.15, abs=0.001)

    def test_long_timing(self, scorer):
        """Contract within 12-24 months should get low score."""
        award_data = {"completion_date": date(2023, 1, 1)}
        contract = FederalContract(contract_id="TEST-008", start_date=date(2024, 1, 1))  # 365 days later

        signal = scorer.score_timing_proximity(award_data=award_data, contract=contract)

        # Should be in second window (91-365 days)
        assert signal.timing_score == pytest.approx(0.15, abs=0.001)

    def test_contract_before_award(self, scorer):
        """Contract before award completion should return zero score."""
        award_data = {"completion_date": date(2023, 6, 1)}
        contract = FederalContract(contract_id="TEST-009", start_date=date(2023, 1, 1))  # Before award

        signal = scorer.score_timing_proximity(award_data=award_data, contract=contract)

        assert signal.days_between_award_and_contract < 0
        assert signal.timing_score == 0.0

    def test_missing_dates(self, scorer):
        """Missing date data should return zero score."""
        award_data = {}
        contract = FederalContract(contract_id="TEST-010", start_date=date(2023, 1, 1))
        signal = scorer.score_timing_proximity(award_data=award_data, contract=contract)

        assert signal.timing_score == 0.0


class TestCompetitionScoring:
    """Tests for competition type scoring."""

    def test_sole_source_bonus(self, scorer):
        """Sole source should provide maximum competition bonus."""
        contract = FederalContract(contract_id="TEST-011", competition_type=CompetitionType.SOLE_SOURCE)
        signal = scorer.score_competition_type(contract)

        assert signal.competition_type == CompetitionType.SOLE_SOURCE
        # sole_source_bonus (0.20) * weight (0.20) = 0.04
        assert signal.competition_score == pytest.approx(0.04, abs=0.001)

    def test_limited_competition_bonus(self, scorer):
        """Limited competition should provide medium bonus."""
        contract = FederalContract(contract_id="TEST-012", competition_type=CompetitionType.LIMITED)
        signal = scorer.score_competition_type(contract)

        assert signal.competition_type == CompetitionType.LIMITED
        # limited_competition_bonus (0.10) * weight (0.20) = 0.02
        assert signal.competition_score == pytest.approx(0.02, abs=0.001)

    def test_full_and_open_no_bonus(self, scorer):
        """Full and open should provide no bonus."""
        contract = FederalContract(contract_id="TEST-013", competition_type=CompetitionType.FULL_AND_OPEN)
        signal = scorer.score_competition_type(contract)

        assert signal.competition_type == CompetitionType.FULL_AND_OPEN
        assert signal.competition_score == 0.0

    def test_missing_competition_type(self, scorer):
        """Missing competition type should default to OTHER with zero score."""
        contract = FederalContract(contract_id="TEST-014")
        signal = scorer.score_competition_type(contract)

        assert signal.competition_type == CompetitionType.OTHER
        assert signal.competition_score == 0.0


class TestPatentScoring:
    """Tests for patent signal scoring."""

    def test_has_patents_bonus(self, scorer):
        """Having patents should provide base bonus."""
        patent_data = {"patent_count": 3}
        signal = scorer.score_patent_signal(patent_data=patent_data)

        assert signal.patent_count == 3
        # has_patent_bonus (0.05) * weight (0.15) = 0.0075
        assert signal.patent_score == pytest.approx(0.0075, abs=0.0001)

    def test_pre_contract_patents_bonus(self, scorer):
        """Patents filed before contract should provide additional bonus."""
        patent_data = {"patent_count": 3, "patents_pre_contract": 2}
        signal = scorer.score_patent_signal(patent_data=patent_data)

        # has_patent (0.05) + pre_contract (0.03) = 0.08, times weight (0.15) = 0.012
        assert signal.patent_score == pytest.approx(0.012, abs=0.0001)

    def test_patent_topic_match_bonus(self, scorer):
        """High patent topic similarity should provide additional bonus."""
        patent_data = {
            "patent_count": 3,
            "patents_pre_contract": 2,
            "patent_topic_similarity": 0.8,
        }
        signal = scorer.score_patent_signal(patent_data=patent_data)

        # has_patent (0.05) + pre_contract (0.03) + topic_match (0.02) = 0.10
        # times weight (0.15) = 0.015
        assert signal.patent_score == pytest.approx(0.015, abs=0.0001)

    def test_low_topic_similarity_no_bonus(self, scorer):
        """Low patent topic similarity should not provide bonus."""
        patent_data = {
            "patent_count": 3,
            "patents_pre_contract": 2,
            "patent_topic_similarity": 0.5,
        }
        signal = scorer.score_patent_signal(patent_data=patent_data)

        # Should not include topic_match bonus (threshold is 0.7)
        assert signal.patent_score == pytest.approx(0.012, abs=0.0001)

    def test_no_patents(self, scorer):
        """No patents should return zero score."""
        patent_data = {"patent_count": 0}
        signal = scorer.score_patent_signal(patent_data=patent_data)

        assert signal.patent_count == 0
        assert signal.patent_score == 0.0


class TestCETScoring:
    """Tests for CET area alignment scoring."""

    def test_same_cet_area_bonus(self, scorer):
        """Same CET area should provide alignment bonus."""
        cet_data = {"award_cet": "AI/Machine Learning", "contract_cet": "AI/Machine Learning"}
        signal = scorer.score_cet_alignment(cet_data=cet_data)

        assert signal.award_cet == "AI/Machine Learning"
        assert signal.contract_cet == "AI/Machine Learning"
        # same_cet_area_bonus (0.05) * weight (0.10) = 0.005
        assert signal.cet_alignment_score == pytest.approx(0.005, abs=0.0001)

    def test_different_cet_area_no_bonus(self, scorer):
        """Different CET areas should provide no bonus."""
        cet_data = {"award_cet": "AI/Machine Learning", "contract_cet": "Quantum Computing"}
        signal = scorer.score_cet_alignment(cet_data=cet_data)

        assert signal.cet_alignment_score == 0.0

    def test_case_insensitive_cet_matching(self, scorer):
        """CET matching should be case-insensitive."""
        cet_data = {"award_cet": "ai/machine learning", "contract_cet": "AI/MACHINE LEARNING"}
        signal = scorer.score_cet_alignment(cet_data=cet_data)

        assert signal.cet_alignment_score > 0.0

    def test_missing_cet_data(self, scorer):
        """Missing CET data should return zero score."""
        cet_data = {"award_cet": None, "contract_cet": "AI/ML"}
        signal = scorer.score_cet_alignment(cet_data=cet_data)

        assert signal.cet_alignment_score == 0.0


class TestCompositeScoring:
    """Tests for composite score computation and confidence classification."""

    def test_base_score_only(self, scorer):
        """With no signals, should return only base score."""
        from src.models.transition_models import TransitionSignals

        signals = TransitionSignals()
        final_score = scorer.compute_final_score(signals)

        assert final_score == 0.15  # base_score

    def test_all_signals_high_score(self, scorer):
        """All strong signals should produce high composite score."""
        # Strong signals across the board
        award_data = {
            "agency": "DOD",
            "completion_date": date(2023, 1, 1),
            "cet": "AI/Machine Learning",
        }
        contract = FederalContract(
            contract_id="TEST-015",
            agency="DOD",
            start_date=date(2023, 2, 1),  # 1 month later
            competition_type=CompetitionType.SOLE_SOURCE,
        )
        patent_data = {
            "patent_count": 5,
            "patents_pre_contract": 3,
            "patent_topic_similarity": 0.9,
        }
        cet_data = {"award_cet": "AI/Machine Learning", "contract_cet": "AI/Machine Learning"}

        signals, final_score, confidence = scorer.score_and_classify(
            award_data, contract, patent_data, cet_data
        )

        # Should be high score with all strong signals
        assert final_score > 0.30  # Significantly above base
        # Exact score depends on config weights

    def test_confidence_high(self, scorer):
        """Score ≥0.85 should classify as HIGH confidence."""
        confidence = scorer.classify_confidence(0.90)
        assert confidence == ConfidenceLevel.HIGH

    def test_confidence_likely(self, scorer):
        """Score ≥0.65 but <0.85 should classify as LIKELY."""
        confidence = scorer.classify_confidence(0.70)
        assert confidence == ConfidenceLevel.LIKELY

    def test_confidence_possible(self, scorer):
        """Score <0.65 should classify as POSSIBLE."""
        confidence = scorer.classify_confidence(0.50)
        assert confidence == ConfidenceLevel.POSSIBLE

    def test_score_and_classify_integration(self, scorer):
        """End-to-end test of score_and_classify method."""
        award_data = {
            "agency": "DOD",
            "completion_date": date(2023, 1, 1),
        }
        contract = FederalContract(
            contract_id="TEST-016",
            agency="DOD",
            start_date=date(2023, 3, 1),  # 2 months later
            competition_type=CompetitionType.LIMITED,
        )

        signals, final_score, confidence = scorer.score_and_classify(award_data, contract)

        # Verify signals computed
        assert signals.agency is not None
        assert signals.timing is not None
        assert signals.competition is not None

        # Verify score in valid range
        assert 0.0 <= final_score <= 1.0

        # Verify confidence is valid enum
        assert isinstance(confidence, ConfidenceLevel)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_score_capping(self, default_config):
        """Scores should be capped at 1.0 even if bonuses exceed limit."""
        # Create config with artificially high bonuses to test capping
        config = default_config.copy()
        config["scoring"]["agency_continuity"]["same_agency_bonus"] = 5.0  # Way too high
        config["scoring"]["agency_continuity"]["weight"] = 1.0

        scorer = TransitionScorer(config)

        # Score with same agency (would be 5.0 * 1.0 = 5.0 without capping)
        award_data = {"agency": "DOD"}
        contract = FederalContract(contract_id="TEST-017", agency="DOD")
        signal = scorer.score_agency_continuity(award_data=award_data, contract=contract)

        # Should be capped at 1.0
        assert signal.agency_score <= 1.0

    def test_negative_score_floor(self, default_config):
        """Scores should not go below 0.0."""
        # Create config with negative base score (invalid but test floor)
        config = default_config.copy()
        config["base_score"] = -0.1

        scorer = TransitionScorer(config)
        from src.models.transition_models import TransitionSignals

        signals = TransitionSignals()
        final_score = scorer.compute_final_score(signals)

        # Should be floored at 0.0
        assert final_score >= 0.0

    def test_disabled_signals_not_counted(self, default_config):
        """Disabled signals should not contribute to final score."""
        # Disable agency scoring
        config = default_config.copy()
        config["scoring"]["agency_continuity"]["enabled"] = False

        scorer = TransitionScorer(config)

        award_data = {"agency": "DOD"}
        contract = FederalContract(contract_id="TEST-018", agency="DOD")

        signals, final_score, _ = scorer.score_and_classify(award_data, contract)

        # Agency signal should still be computed but not counted
        assert signals.agency is not None
        # Final score should only be base_score (0.15) since agency disabled
        assert final_score == pytest.approx(0.15, abs=0.01)
