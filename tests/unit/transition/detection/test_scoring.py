"""Tests for transition scoring algorithm."""

from datetime import date

import pytest

from src.models.transition_models import (
    AgencySignal,
    CETSignal,
    CompetitionSignal,
    CompetitionType,
    ConfidenceLevel,
    FederalContract,
    PatentSignal,
    TimingSignal,
    TransitionSignals,
)
from src.transition.detection.scoring import TransitionScorer


@pytest.fixture
def default_config():
    """Default scoring configuration for tests."""
    return {
        "base_score": 0.15,
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
                    {"range": [0, 90], "score": 1.0},
                    {"range": [91, 180], "score": 0.7},
                    {"range": [181, 365], "score": 0.4},
                ],
                "beyond_window_penalty": 0.1,
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
            },
            "text_similarity": {
                "enabled": False,
                "weight": 0.10,
            },
        },
        "confidence_thresholds": {
            "high": 0.85,
            "likely": 0.65,
        },
    }


class TestTransitionScorerInitialization:
    """Tests for TransitionScorer initialization."""

    def test_initialization_with_config(self, default_config):
        """Test TransitionScorer initialization with config."""
        scorer = TransitionScorer(default_config)

        assert scorer.base_score == 0.15
        assert scorer.high_threshold == 0.85
        assert scorer.likely_threshold == 0.65
        assert scorer.agency_config["weight"] == 0.25

    def test_initialization_with_minimal_config(self):
        """Test initialization with minimal config."""
        minimal_config = {}
        scorer = TransitionScorer(minimal_config)

        assert scorer.base_score == 0.15  # Default
        assert scorer.high_threshold == 0.85  # Default

    def test_initialization_custom_thresholds(self):
        """Test initialization with custom confidence thresholds."""
        config = {
            "base_score": 0.20,
            "confidence_thresholds": {
                "high": 0.90,
                "likely": 0.70,
            },
        }
        scorer = TransitionScorer(config)

        assert scorer.base_score == 0.20
        assert scorer.high_threshold == 0.90
        assert scorer.likely_threshold == 0.70


class TestScoreAgencyContinuity:
    """Tests for score_agency_continuity method."""

    def test_score_agency_same_agency(self, default_config):
        """Test scoring with same agency."""
        scorer = TransitionScorer(default_config)

        award_data = {"agency": "DOD"}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_agency_continuity(award_data, contract)

        assert signal.same_agency is True
        assert signal.agency_score > 0
        # 0.25 (bonus) * 0.25 (weight) = 0.0625
        assert signal.agency_score == pytest.approx(0.0625)

    def test_score_agency_same_department(self, default_config):
        """Test scoring with same department but different agency."""
        scorer = TransitionScorer(default_config)

        award_data = {"agency": "DOD-ARMY", "department": "DOD"}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD-NAVY",
            sub_agency="DOD",
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_agency_continuity(award_data, contract)

        assert signal.same_agency is False
        assert signal.same_department is True
        # 0.125 (cross_service_bonus) * 0.25 (weight) = 0.03125
        assert signal.agency_score == pytest.approx(0.03125)

    def test_score_agency_different_agencies(self, default_config):
        """Test scoring with different agencies."""
        scorer = TransitionScorer(default_config)

        award_data = {"agency": "DOD"}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="NASA",
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_agency_continuity(award_data, contract)

        assert signal.same_agency is False
        # 0.05 (different_dept_bonus) * 0.25 (weight) = 0.0125
        assert signal.agency_score == pytest.approx(0.0125)

    def test_score_agency_missing_data(self, default_config):
        """Test scoring with missing agency data."""
        scorer = TransitionScorer(default_config)

        award_data = {}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency=None,
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_agency_continuity(award_data, contract)

        assert signal.same_agency is False
        assert signal.agency_score == 0.0

    def test_score_agency_case_insensitive(self, default_config):
        """Test scoring is case-insensitive."""
        scorer = TransitionScorer(default_config)

        award_data = {"agency": "dod"}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_agency_continuity(award_data, contract)

        assert signal.same_agency is True


class TestScoreTimingProximity:
    """Tests for score_timing_proximity method."""

    def test_score_timing_high_proximity(self, default_config):
        """Test scoring with high temporal proximity (< 90 days)."""
        scorer = TransitionScorer(default_config)

        award_data = {"completion_date": date(2023, 1, 1)}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            start_date=date(2023, 2, 15),  # 45 days later
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_timing_proximity(award_data, contract)

        assert signal.days_between_award_and_contract == 45
        assert signal.months_between_award_and_contract == pytest.approx(1.5)
        # 1.0 (window score) * 0.20 (weight) = 0.20
        assert signal.timing_score == pytest.approx(0.20)

    def test_score_timing_moderate_proximity(self, default_config):
        """Test scoring with moderate proximity (91-180 days)."""
        scorer = TransitionScorer(default_config)

        award_data = {"completion_date": date(2023, 1, 1)}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            start_date=date(2023, 5, 1),  # 120 days later
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_timing_proximity(award_data, contract)

        assert signal.days_between_award_and_contract == 120
        # 0.7 (window score) * 0.20 (weight) = 0.14
        assert signal.timing_score == pytest.approx(0.14)

    def test_score_timing_beyond_windows(self, default_config):
        """Test scoring beyond configured windows."""
        scorer = TransitionScorer(default_config)

        award_data = {"completion_date": date(2023, 1, 1)}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            start_date=date(2024, 6, 1),  # 517 days later
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_timing_proximity(award_data, contract)

        assert signal.days_between_award_and_contract == 517
        # Uses beyond_window_penalty = 0.1
        assert signal.timing_score == 0.1

    def test_score_timing_negative_days(self, default_config):
        """Test scoring with contract before award (anomaly)."""
        scorer = TransitionScorer(default_config)

        award_data = {"completion_date": date(2023, 2, 1)}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            start_date=date(2023, 1, 1),  # 31 days before
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_timing_proximity(award_data, contract)

        assert signal.days_between_award_and_contract == -31
        assert signal.timing_score == 0.0

    def test_score_timing_missing_dates(self, default_config):
        """Test scoring with missing dates."""
        scorer = TransitionScorer(default_config)

        award_data = {}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            start_date=None,
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_timing_proximity(award_data, contract)

        assert signal.timing_score == 0.0


class TestScoreCompetitionType:
    """Tests for score_competition_type method."""

    def test_score_competition_sole_source(self, default_config):
        """Test scoring with sole source competition."""
        scorer = TransitionScorer(default_config)

        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_competition_type(contract)

        assert signal.competition_type == CompetitionType.SOLE_SOURCE
        # 0.20 (bonus) * 0.20 (weight) = 0.04
        assert signal.competition_score == pytest.approx(0.04)

    def test_score_competition_limited(self, default_config):
        """Test scoring with limited competition."""
        scorer = TransitionScorer(default_config)

        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            competition_type=CompetitionType.LIMITED,
        )

        signal = scorer.score_competition_type(contract)

        assert signal.competition_type == CompetitionType.LIMITED
        # 0.10 (bonus) * 0.20 (weight) = 0.02
        assert signal.competition_score == pytest.approx(0.02)

    def test_score_competition_full_and_open(self, default_config):
        """Test scoring with full and open competition."""
        scorer = TransitionScorer(default_config)

        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            competition_type=CompetitionType.FULL_AND_OPEN,
        )

        signal = scorer.score_competition_type(contract)

        assert signal.competition_type == CompetitionType.FULL_AND_OPEN
        assert signal.competition_score == 0.0

    def test_score_competition_other(self, default_config):
        """Test scoring with OTHER competition type."""
        scorer = TransitionScorer(default_config)

        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            competition_type=CompetitionType.OTHER,
        )

        signal = scorer.score_competition_type(contract)

        assert signal.competition_type == CompetitionType.OTHER
        assert signal.competition_score == 0.0

    def test_score_competition_none(self, default_config):
        """Test scoring with None competition type."""
        scorer = TransitionScorer(default_config)

        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            competition_type=None,
        )

        signal = scorer.score_competition_type(contract)

        assert signal.competition_type == CompetitionType.OTHER
        assert signal.competition_score == 0.0


class TestScorePatentSignal:
    """Tests for score_patent_signal method."""

    def test_score_patent_with_patents(self, default_config):
        """Test scoring with patents found."""
        scorer = TransitionScorer(default_config)

        patent_data = {
            "patent_count": 5,
            "patents_pre_contract": 3,
            "patent_topic_similarity": 0.85,
        }

        signal = scorer.score_patent_signal(patent_data)

        assert signal.patent_count == 5
        assert signal.patents_pre_contract == 3
        # has_patent_bonus (0.05) + pre_contract_bonus (0.03) + topic_bonus (0.02) = 0.10
        # 0.10 * 0.15 (weight) = 0.015
        assert signal.patent_score == pytest.approx(0.015)

    def test_score_patent_no_patents(self, default_config):
        """Test scoring with no patents."""
        scorer = TransitionScorer(default_config)

        patent_data = {"patent_count": 0}

        signal = scorer.score_patent_signal(patent_data)

        assert signal.patent_count == 0
        assert signal.patent_score == 0.0

    def test_score_patent_none_data(self, default_config):
        """Test scoring with None patent data."""
        scorer = TransitionScorer(default_config)

        signal = scorer.score_patent_signal(None)

        assert signal.patent_score == 0.0

    def test_score_patent_low_topic_similarity(self, default_config):
        """Test scoring with low topic similarity (below threshold)."""
        scorer = TransitionScorer(default_config)

        patent_data = {
            "patent_count": 3,
            "patents_pre_contract": 0,
            "patent_topic_similarity": 0.6,  # Below 0.7 threshold
        }

        signal = scorer.score_patent_signal(patent_data)

        # Only has_patent_bonus (0.05), no topic bonus
        # 0.05 * 0.15 (weight) = 0.0075
        assert signal.patent_score == pytest.approx(0.0075)

    def test_score_patent_high_topic_similarity(self, default_config):
        """Test scoring with high topic similarity (above threshold)."""
        scorer = TransitionScorer(default_config)

        patent_data = {
            "patent_count": 2,
            "patents_pre_contract": 0,
            "patent_topic_similarity": 0.95,
        }

        signal = scorer.score_patent_signal(patent_data)

        # has_patent_bonus (0.05) + topic_bonus (0.02) = 0.07
        # 0.07 * 0.15 = 0.0105
        assert signal.patent_score == pytest.approx(0.0105)


class TestScoreCETAlignment:
    """Tests for score_cet_alignment method."""

    def test_score_cet_same_area(self, default_config):
        """Test scoring with same CET area."""
        scorer = TransitionScorer(default_config)

        cet_data = {
            "award_cet": "artificial_intelligence",
            "contract_cet": "artificial_intelligence",
        }

        signal = scorer.score_cet_alignment(cet_data)

        assert signal.award_cet == "artificial_intelligence"
        assert signal.contract_cet == "artificial_intelligence"
        # 0.05 (bonus) * 0.10 (weight) = 0.005
        assert signal.cet_alignment_score == pytest.approx(0.005)

    def test_score_cet_different_areas(self, default_config):
        """Test scoring with different CET areas."""
        scorer = TransitionScorer(default_config)

        cet_data = {
            "award_cet": "artificial_intelligence",
            "contract_cet": "biotechnology",
        }

        signal = scorer.score_cet_alignment(cet_data)

        assert signal.cet_alignment_score == 0.0

    def test_score_cet_missing_data(self, default_config):
        """Test scoring with missing CET data."""
        scorer = TransitionScorer(default_config)

        cet_data = {"award_cet": "ai", "contract_cet": None}

        signal = scorer.score_cet_alignment(cet_data)

        assert signal.cet_alignment_score == 0.0

    def test_score_cet_none_data(self, default_config):
        """Test scoring with None CET data."""
        scorer = TransitionScorer(default_config)

        signal = scorer.score_cet_alignment(None)

        assert signal.cet_alignment_score == 0.0

    def test_score_cet_case_insensitive(self, default_config):
        """Test scoring is case-insensitive."""
        scorer = TransitionScorer(default_config)

        cet_data = {
            "award_cet": "Artificial_Intelligence",
            "contract_cet": "artificial_intelligence",
        }

        signal = scorer.score_cet_alignment(cet_data)

        assert signal.cet_alignment_score > 0


class TestScoreTextSimilarity:
    """Tests for score_text_similarity method."""

    def test_score_text_similarity_disabled(self, default_config):
        """Test text similarity when disabled."""
        scorer = TransitionScorer(default_config)

        score = scorer.score_text_similarity(0.85)

        # Text similarity is disabled in default_config
        assert score == 0.0

    def test_score_text_similarity_enabled(self):
        """Test text similarity when enabled."""
        config = {
            "scoring": {
                "text_similarity": {
                    "enabled": True,
                    "weight": 0.10,
                }
            }
        }
        scorer = TransitionScorer(config)

        score = scorer.score_text_similarity(0.85)

        # 0.85 * 0.10 = 0.085
        assert score == pytest.approx(0.085)

    def test_score_text_similarity_none(self, default_config):
        """Test text similarity with None input."""
        scorer = TransitionScorer(default_config)

        score = scorer.score_text_similarity(None)

        assert score == 0.0


class TestComputeFinalScore:
    """Tests for compute_final_score method."""

    def test_compute_final_score_all_signals(self, default_config):
        """Test computing final score with all signals."""
        scorer = TransitionScorer(default_config)

        signals = TransitionSignals(
            agency=AgencySignal(same_agency=True, same_department=False, agency_score=0.10),
            timing=TimingSignal(
                days_between_award_and_contract=45,
                months_between_award_and_contract=1.5,
                timing_score=0.15,
            ),
            competition=CompetitionSignal(
                competition_type=CompetitionType.SOLE_SOURCE,
                competition_score=0.08,
            ),
            patent=PatentSignal(
                patent_count=3,
                patents_pre_contract=2,
                patent_topic_similarity=0.8,
                patent_score=0.05,
            ),
            cet=CETSignal(
                award_cet="ai",
                contract_cet="ai",
                cet_alignment_score=0.02,
            ),
        )

        final_score = scorer.compute_final_score(signals)

        # base (0.15) + agency (0.10) + timing (0.15) + competition (0.08) + patent (0.05) + cet (0.02) = 0.55
        assert final_score == pytest.approx(0.55)

    def test_compute_final_score_minimal_signals(self, default_config):
        """Test computing final score with minimal signals."""
        scorer = TransitionScorer(default_config)

        signals = TransitionSignals(
            agency=AgencySignal(same_agency=False, same_department=False, agency_score=0.01),
        )

        final_score = scorer.compute_final_score(signals)

        # base (0.15) + agency (0.01) = 0.16
        assert final_score == pytest.approx(0.16)

    def test_compute_final_score_caps_at_one(self, default_config):
        """Test final score is capped at 1.0."""
        scorer = TransitionScorer(default_config)

        signals = TransitionSignals(
            agency=AgencySignal(same_agency=True, same_department=False, agency_score=0.9),
            timing=TimingSignal(
                days_between_award_and_contract=10,
                months_between_award_and_contract=0.3,
                timing_score=0.8,
            ),
        )

        final_score = scorer.compute_final_score(signals)

        # Would be > 1.0, but capped
        assert final_score == 1.0

    def test_compute_final_score_with_disabled_signals(self):
        """Test computing score with some signals disabled."""
        config = {
            "base_score": 0.15,
            "scoring": {
                "agency_continuity": {"enabled": True},
                "timing_proximity": {"enabled": False},  # Disabled
                "competition_type": {"enabled": True},
            },
        }
        scorer = TransitionScorer(config)

        signals = TransitionSignals(
            agency=AgencySignal(same_agency=True, same_department=False, agency_score=0.10),
            timing=TimingSignal(
                days_between_award_and_contract=45,
                months_between_award_and_contract=1.5,
                timing_score=0.15,
            ),  # Should be ignored
            competition=CompetitionSignal(
                competition_type=CompetitionType.SOLE_SOURCE,
                competition_score=0.08,
            ),
        )

        final_score = scorer.compute_final_score(signals)

        # base (0.15) + agency (0.10) + competition (0.08) = 0.33, timing ignored
        assert final_score == pytest.approx(0.33)


class TestClassifyConfidence:
    """Tests for classify_confidence method."""

    def test_classify_confidence_high(self, default_config):
        """Test classifying high confidence."""
        scorer = TransitionScorer(default_config)

        confidence = scorer.classify_confidence(0.90)

        assert confidence == ConfidenceLevel.HIGH

    def test_classify_confidence_likely(self, default_config):
        """Test classifying likely confidence."""
        scorer = TransitionScorer(default_config)

        confidence = scorer.classify_confidence(0.70)

        assert confidence == ConfidenceLevel.LIKELY

    def test_classify_confidence_possible(self, default_config):
        """Test classifying possible confidence."""
        scorer = TransitionScorer(default_config)

        confidence = scorer.classify_confidence(0.50)

        assert confidence == ConfidenceLevel.POSSIBLE

    def test_classify_confidence_at_high_threshold(self, default_config):
        """Test classification exactly at high threshold."""
        scorer = TransitionScorer(default_config)

        confidence = scorer.classify_confidence(0.85)

        assert confidence == ConfidenceLevel.HIGH

    def test_classify_confidence_at_likely_threshold(self, default_config):
        """Test classification exactly at likely threshold."""
        scorer = TransitionScorer(default_config)

        confidence = scorer.classify_confidence(0.65)

        assert confidence == ConfidenceLevel.LIKELY


class TestScoreTransition:
    """Tests for score_transition convenience method."""

    def test_score_transition_complete(self, default_config):
        """Test score_transition with complete data."""
        scorer = TransitionScorer(default_config)

        award_data = {
            "agency": "DOD",
            "completion_date": date(2023, 1, 1),
        }

        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            start_date=date(2023, 2, 1),
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        patent_data = {"patent_count": 3}
        cet_data = {"award_cet": "ai", "contract_cet": "ai"}

        signals = scorer.score_transition(award_data, contract, patent_data, cet_data)

        assert isinstance(signals, TransitionSignals)
        assert signals.agency is not None
        assert signals.timing is not None
        assert signals.competition is not None
        assert signals.patent is not None
        assert signals.cet is not None


class TestScoreAndClassify:
    """Tests for score_and_classify end-to-end method."""

    def test_score_and_classify_high_confidence(self, default_config):
        """Test end-to-end scoring with high confidence."""
        scorer = TransitionScorer(default_config)

        award_data = {
            "agency": "DOD",
            "completion_date": date(2023, 1, 1),
        }

        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            start_date=date(2023, 2, 1),  # 31 days later
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        patent_data = {
            "patent_count": 5,
            "patents_pre_contract": 3,
            "patent_topic_similarity": 0.9,
        }
        cet_data = {"award_cet": "ai", "contract_cet": "ai"}

        signals, final_score, confidence = scorer.score_and_classify(
            award_data, contract, patent_data, cet_data
        )

        assert isinstance(signals, TransitionSignals)
        assert 0.0 <= final_score <= 1.0
        assert confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.LIKELY, ConfidenceLevel.POSSIBLE]

    def test_score_and_classify_returns_tuple(self, default_config):
        """Test score_and_classify returns correct tuple format."""
        scorer = TransitionScorer(default_config)

        award_data = {"agency": "DOD"}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        result = scorer.score_and_classify(award_data, contract)

        assert len(result) == 3
        assert isinstance(result[0], TransitionSignals)
        assert isinstance(result[1], float)
        assert isinstance(result[2], ConfidenceLevel)


class TestEdgeCases:
    """Tests for edge cases in scoring."""

    def test_scoring_with_empty_config(self):
        """Test scoring with empty configuration."""
        config = {}
        scorer = TransitionScorer(config)

        award_data = {"agency": "DOD"}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signals = scorer.score_transition(award_data, contract)

        # Should not raise, returns signals with zeros
        assert signals is not None

    def test_final_score_minimum_zero(self, default_config):
        """Test final score cannot go below 0.0."""
        scorer = TransitionScorer(default_config)
        scorer.base_score = -1.0  # Force negative

        signals = TransitionSignals(
            agency=AgencySignal(same_agency=False, same_department=False, agency_score=0.0),
        )

        final_score = scorer.compute_final_score(signals)

        assert final_score == 0.0

    def test_timing_exactly_at_window_boundary(self, default_config):
        """Test timing score at exact window boundary."""
        scorer = TransitionScorer(default_config)

        award_data = {"completion_date": date(2023, 1, 1)}
        contract = FederalContract(
            contract_id="C123",
            vendor_id="V123",
            vendor_name="Vendor",
            agency="DOD",
            start_date=date(2023, 4, 1),  # Exactly 90 days
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        signal = scorer.score_timing_proximity(award_data, contract)

        # 90 days should fall in first window [0, 90]
        assert signal.days_between_award_and_contract == 90
        assert signal.timing_score > 0
