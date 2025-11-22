"""Tests for transition detection Pydantic models."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError


pytestmark = pytest.mark.fast

from src.models.transition_models import (
    AgencySignal,
    CETSignal,
    CompetitionSignal,
    CompetitionType,
    ConfidenceLevel,
    EvidenceBundle,
    EvidenceItem,
    FederalContract,
    PatentSignal,
    TimingSignal,
    Transition,
    TransitionProfile,
    TransitionSignals,
    VendorMatch,
)


pytestmark = pytest.mark.fast


class TestEnums:
    """Tests for enum types."""

    def test_confidence_level_values(self):
        """Test ConfidenceLevel enum values."""
        assert ConfidenceLevel.HIGH == "high"
        assert ConfidenceLevel.LIKELY == "likely"
        assert ConfidenceLevel.POSSIBLE == "possible"

    def test_competition_type_values(self):
        """Test CompetitionType enum values."""
        assert CompetitionType.SOLE_SOURCE == "sole_source"
        assert CompetitionType.LIMITED == "limited"
        assert CompetitionType.FULL_AND_OPEN == "full_and_open"
        assert CompetitionType.OTHER == "other"


class TestAgencySignal:
    """Tests for AgencySignal model."""

    def test_valid_agency_signal(self):
        """Test creating a valid agency signal."""
        signal = AgencySignal(
            same_agency=True,
            same_department=True,
            agency_score=0.95,
        )
        assert signal.same_agency is True
        assert signal.same_department is True
        assert signal.agency_score == 0.95

    def test_agency_signal_minimal(self):
        """Test agency signal with only required field."""
        signal = AgencySignal(same_agency=False)
        assert signal.same_agency is False
        assert signal.same_department is None
        assert signal.agency_score == 0.0  # Default

    def test_agency_score_constraints(self):
        """Test agency_score must be between 0 and 1."""
        with pytest.raises(ValidationError):
            AgencySignal(same_agency=True, agency_score=1.5)


class TestTimingSignal:
    """Tests for TimingSignal model."""

    def test_valid_timing_signal(self):
        """Test creating a valid timing signal."""
        signal = TimingSignal(
            days_between_award_and_contract=180,
            months_between_award_and_contract=6.0,
            timing_score=0.85,
        )
        assert signal.days_between_award_and_contract == 180
        assert signal.months_between_award_and_contract == 6.0
        assert signal.timing_score == 0.85

    def test_timing_signal_defaults(self):
        """Test timing signal with default values."""
        signal = TimingSignal()
        assert signal.days_between_award_and_contract is None
        assert signal.months_between_award_and_contract is None
        assert signal.timing_score == 0.0

    def test_timing_score_constraints(self):
        """Test timing_score must be between 0 and 1."""
        with pytest.raises(ValidationError):
            TimingSignal(timing_score=-0.1)


class TestCompetitionSignal:
    """Tests for CompetitionSignal model."""

    def test_valid_competition_signal(self):
        """Test creating a valid competition signal."""
        signal = CompetitionSignal(
            competition_type=CompetitionType.SOLE_SOURCE,
            competition_score=0.90,
        )
        assert signal.competition_type == CompetitionType.SOLE_SOURCE
        assert signal.competition_score == 0.90

    def test_competition_signal_defaults(self):
        """Test competition signal with default values."""
        signal = CompetitionSignal()
        assert signal.competition_type == CompetitionType.OTHER
        assert signal.competition_score == 0.0

    def test_competition_score_constraints(self):
        """Test competition_score must be between 0 and 1."""
        with pytest.raises(ValidationError):
            CompetitionSignal(competition_score=2.0)


class TestPatentSignal:
    """Tests for PatentSignal model."""

    def test_valid_patent_signal(self):
        """Test creating a valid patent signal."""
        signal = PatentSignal(
            patent_count=5,
            patents_pre_contract=3,
            patent_topic_similarity=0.75,
            avg_filing_lag_days=120.5,
            patent_score=0.80,
        )
        assert signal.patent_count == 5
        assert signal.patents_pre_contract == 3
        assert signal.patent_topic_similarity == 0.75
        assert signal.avg_filing_lag_days == 120.5
        assert signal.patent_score == 0.80

    def test_patent_signal_defaults(self):
        """Test patent signal with default values."""
        signal = PatentSignal()
        assert signal.patent_count == 0
        assert signal.patents_pre_contract == 0
        assert signal.patent_topic_similarity is None
        assert signal.avg_filing_lag_days is None
        assert signal.patent_score == 0.0

    def test_patent_count_negative_rejected(self):
        """Test patent_count rejects negative values."""
        with pytest.raises(ValidationError):
            PatentSignal(patent_count=-1)

    def test_patent_topic_similarity_constraints(self):
        """Test patent_topic_similarity must be between 0 and 1."""
        with pytest.raises(ValidationError):
            PatentSignal(patent_topic_similarity=1.5)


class TestCETSignal:
    """Tests for CETSignal model."""

    def test_valid_cet_signal(self):
        """Test creating a valid CET signal."""
        signal = CETSignal(
            award_cet="AI-001",
            contract_cet="AI-001",
            cet_alignment_score=1.0,
        )
        assert signal.award_cet == "AI-001"
        assert signal.contract_cet == "AI-001"
        assert signal.cet_alignment_score == 1.0

    def test_cet_signal_defaults(self):
        """Test CET signal with default values."""
        signal = CETSignal()
        assert signal.award_cet is None
        assert signal.contract_cet is None
        assert signal.cet_alignment_score == 0.0

    def test_cet_alignment_score_constraints(self):
        """Test cet_alignment_score must be between 0 and 1."""
        with pytest.raises(ValidationError):
            CETSignal(cet_alignment_score=-0.5)


class TestTransitionSignals:
    """Tests for TransitionSignals aggregate container."""

    def test_valid_transition_signals(self):
        """Test creating transition signals with all components."""
        signals = TransitionSignals(
            agency=AgencySignal(same_agency=True, agency_score=0.95),
            timing=TimingSignal(days_between_award_and_contract=90, timing_score=0.90),
            competition=CompetitionSignal(
                competition_type=CompetitionType.SOLE_SOURCE, competition_score=0.85
            ),
            patent=PatentSignal(patent_count=3, patent_score=0.75),
            cet=CETSignal(award_cet="AI-001", cet_alignment_score=1.0),
            text_similarity_score=0.82,
        )
        assert signals.agency.same_agency is True
        assert signals.timing.days_between_award_and_contract == 90
        assert signals.text_similarity_score == 0.82

    def test_transition_signals_all_none(self):
        """Test transition signals can be created with all None."""
        signals = TransitionSignals()
        assert signals.agency is None
        assert signals.timing is None
        assert signals.competition is None
        assert signals.patent is None
        assert signals.cet is None
        assert signals.text_similarity_score is None

    def test_text_similarity_score_validator_accepts_valid(self):
        """Test text_similarity_score validator accepts 0-1 range."""
        signals = TransitionSignals(text_similarity_score=0.5)
        assert signals.text_similarity_score == 0.5

    def test_text_similarity_score_validator_rejects_negative(self):
        """Test text_similarity_score validator rejects negative."""
        with pytest.raises(ValidationError) as exc_info:
            TransitionSignals(text_similarity_score=-0.1)
        assert "text_similarity_score must be between 0.0 and 1.0" in str(exc_info.value)

    def test_text_similarity_score_validator_rejects_too_high(self):
        """Test text_similarity_score validator rejects > 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            TransitionSignals(text_similarity_score=1.5)
        assert "text_similarity_score must be between 0.0 and 1.0" in str(exc_info.value)

    def test_text_similarity_score_validator_coerces_int(self):
        """Test text_similarity_score validator coerces int to float."""
        signals = TransitionSignals(text_similarity_score=1)
        assert signals.text_similarity_score == 1.0
        assert isinstance(signals.text_similarity_score, float)


class TestEvidenceItem:
    """Tests for EvidenceItem model."""

    def test_valid_evidence_item(self):
        """Test creating a valid evidence item."""
        item = EvidenceItem(
            source="usaspending",
            signal="agency",
            snippet="Same agency: Department of Defense",
            citation="https://usaspending.gov/award/123",
            score=0.95,
            metadata={"agency_code": "DOD"},
        )
        assert item.source == "usaspending"
        assert item.signal == "agency"
        assert item.score == 0.95

    def test_evidence_item_minimal(self):
        """Test evidence item with only required fields."""
        item = EvidenceItem(source="patentsview", signal="patent")
        assert item.source == "patentsview"
        assert item.signal == "patent"
        assert item.snippet is None
        assert item.citation is None
        assert item.score is None
        assert item.metadata == {}

    def test_evidence_item_score_constraints(self):
        """Test evidence item score must be between 0 and 1."""
        with pytest.raises(ValidationError):
            EvidenceItem(source="test", signal="test", score=1.5)


class TestEvidenceBundle:
    """Tests for EvidenceBundle model."""

    def test_valid_evidence_bundle(self):
        """Test creating a valid evidence bundle."""
        bundle = EvidenceBundle(
            items=[
                EvidenceItem(source="usaspending", signal="agency", score=0.95),
                EvidenceItem(source="patentsview", signal="patent", score=0.80),
            ],
            summary="Strong evidence of transition based on agency and patent signals.",
        )
        assert len(bundle.items) == 2
        assert bundle.summary is not None

    def test_evidence_bundle_defaults(self):
        """Test evidence bundle with default values."""
        bundle = EvidenceBundle()
        assert bundle.items == []
        assert bundle.summary is None
        assert isinstance(bundle.created_at, datetime)

    def test_add_item_method(self):
        """Test add_item method."""
        bundle = EvidenceBundle()
        item = EvidenceItem(source="usaspending", signal="timing", score=0.85)
        bundle.add_item(item)
        assert len(bundle.items) == 1
        assert bundle.items[0].source == "usaspending"

    def test_total_score_with_scores(self):
        """Test total_score calculates mean of item scores."""
        bundle = EvidenceBundle(
            items=[
                EvidenceItem(source="src1", signal="sig1", score=0.8),
                EvidenceItem(source="src2", signal="sig2", score=0.6),
                EvidenceItem(source="src3", signal="sig3", score=1.0),
            ]
        )
        assert bundle.total_score() == 0.8  # (0.8 + 0.6 + 1.0) / 3

    def test_total_score_with_none_scores(self):
        """Test total_score ignores None scores."""
        bundle = EvidenceBundle(
            items=[
                EvidenceItem(source="src1", signal="sig1", score=0.9),
                EvidenceItem(source="src2", signal="sig2", score=None),
                EvidenceItem(source="src3", signal="sig3", score=0.7),
            ]
        )
        assert bundle.total_score() == 0.8  # (0.9 + 0.7) / 2

    def test_total_score_empty(self):
        """Test total_score returns 0.0 for empty bundle."""
        bundle = EvidenceBundle()
        assert bundle.total_score() == 0.0

    def test_total_score_all_none(self):
        """Test total_score returns 0.0 when all scores are None."""
        bundle = EvidenceBundle(
            items=[
                EvidenceItem(source="src1", signal="sig1", score=None),
                EvidenceItem(source="src2", signal="sig2", score=None),
            ]
        )
        assert bundle.total_score() == 0.0


class TestVendorMatch:
    """Tests for VendorMatch model."""

    def test_valid_vendor_match(self):
        """Test creating a valid vendor match."""
        match = VendorMatch(
            vendor_id="VENDOR-123",
            method="uei",
            score=1.0,
            matched_name="Acme Corporation",
            metadata={"uei": "ABC123DEF456"},  # pragma: allowlist secret
        )
        assert match.vendor_id == "VENDOR-123"
        assert match.method == "uei"
        assert match.score == 1.0

    def test_vendor_match_minimal(self):
        """Test vendor match with only required fields."""
        match = VendorMatch(method="name_fuzzy")
        assert match.vendor_id is None
        assert match.method == "name_fuzzy"
        assert match.score == 0.0
        assert match.matched_name is None
        assert match.metadata == {}

    def test_vendor_match_score_constraints(self):
        """Test vendor match score must be between 0 and 1."""
        with pytest.raises(ValidationError):
            VendorMatch(method="cage", score=-0.1)


class TestFederalContract:
    """Tests for FederalContract model."""

    def test_valid_federal_contract(self):
        """Test creating a valid federal contract."""
        contract = FederalContract(
            contract_id="CONTRACT-001",
            agency="DOD",
            sub_agency="Air Force",
            vendor_name="Acme Corp",
            vendor_uei="ABC123DEF456",  # pragma: allowlist secret
            start_date=date(2023, 1, 1),
            end_date=date(2024, 1, 1),
            obligation_amount=500000.0,
            competition_type=CompetitionType.SOLE_SOURCE,
            description="Advanced R&D",
        )
        assert contract.contract_id == "CONTRACT-001"
        assert contract.obligation_amount == 500000.0
        assert contract.is_deobligation is False

    def test_federal_contract_negative_obligation(self):
        """Test federal contract accepts negative obligation (deobligation)."""
        contract = FederalContract(
            contract_id="CONTRACT-002",
            obligation_amount=-10000.0,
            is_deobligation=True,
        )
        assert contract.obligation_amount == -10000.0
        assert contract.is_deobligation is True

    def test_date_validator_parses_iso_string(self):
        """Test date validator parses ISO format strings."""
        contract = FederalContract(
            contract_id="CONTRACT-003",
            start_date="2023-06-15",
            end_date="2024-06-14",
        )
        assert contract.start_date == date(2023, 6, 15)
        assert contract.end_date == date(2024, 6, 14)

    def test_date_validator_accepts_date_objects(self):
        """Test date validator accepts date objects."""
        contract = FederalContract(
            contract_id="CONTRACT-004",
            start_date=date(2023, 1, 1),
            end_date=date(2024, 1, 1),
        )
        assert contract.start_date == date(2023, 1, 1)
        assert contract.end_date == date(2024, 1, 1)

    def test_date_validator_accepts_datetime_objects(self):
        """Test date validator converts datetime to date."""
        contract = FederalContract(
            contract_id="CONTRACT-005",
            start_date=datetime(2023, 1, 1, 10, 30),
        )
        assert contract.start_date == date(2023, 1, 1)

    def test_date_validator_rejects_invalid_format(self):
        """Test date validator rejects invalid date formats."""
        with pytest.raises(ValidationError) as exc_info:
            FederalContract(
                contract_id="CONTRACT-006",
                start_date="invalid-date",
            )
        assert "Dates must be ISO-formatted strings or date objects" in str(exc_info.value)

    def test_date_logic_validator_rejects_end_before_start(self):
        """Test model validator rejects end_date before start_date."""
        with pytest.raises(ValidationError) as exc_info:
            FederalContract(
                contract_id="CONTRACT-007",
                start_date=date(2024, 1, 1),
                end_date=date(2023, 1, 1),
            )
        assert "end_date must be after start_date" in str(exc_info.value)

    def test_date_logic_validator_accepts_same_date(self):
        """Test model validator allows end_date same as start_date."""
        contract = FederalContract(
            contract_id="CONTRACT-008",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 1),
        )
        # Should not raise - same date is technically after (>=)
        # But the validator checks < not <=, so this passes
        assert contract.start_date == contract.end_date

    def test_federal_contract_with_parent(self):
        """Test federal contract with parent contract fields."""
        contract = FederalContract(
            contract_id="TASK-001",
            parent_contract_id="IDV-PARENT-001",
            parent_contract_agency="DOD",
            contract_award_type="B",
        )
        assert contract.parent_contract_id == "IDV-PARENT-001"
        assert contract.parent_contract_agency == "DOD"
        assert contract.contract_award_type == "B"


class TestTransition:
    """Tests for Transition model."""

    def test_valid_transition(self):
        """Test creating a valid transition."""
        transition = Transition(
            transition_id="TRANS-001",
            award_id="AWARD-001",
            likelihood_score=0.92,
            confidence=ConfidenceLevel.HIGH,
            primary_contract=FederalContract(contract_id="CONTRACT-001"),
            signals=TransitionSignals(agency=AgencySignal(same_agency=True, agency_score=0.95)),
        )
        assert transition.transition_id == "TRANS-001"
        assert transition.likelihood_score == 0.92
        assert transition.confidence == ConfidenceLevel.HIGH

    def test_transition_minimal(self):
        """Test transition with only required fields."""
        transition = Transition(
            transition_id="TRANS-002",
            likelihood_score=0.65,
            confidence=ConfidenceLevel.POSSIBLE,
        )
        assert transition.transition_id == "TRANS-002"
        assert transition.award_id is None
        assert transition.primary_contract is None
        assert transition.signals is None
        assert transition.evidence is None
        assert isinstance(transition.detected_at, datetime)

    def test_likelihood_score_validator_accepts_valid(self):
        """Test likelihood_score validator accepts 0-1 range."""
        transition = Transition(
            transition_id="TRANS-003",
            likelihood_score=0.5,
            confidence=ConfidenceLevel.POSSIBLE,
        )
        assert transition.likelihood_score == 0.5

    def test_likelihood_score_validator_rejects_negative(self):
        """Test likelihood_score validator rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            Transition(
                transition_id="TRANS-004",
                likelihood_score=-0.1,
                confidence=ConfidenceLevel.POSSIBLE,
            )
        assert "likelihood_score must be between 0.0 and 1.0" in str(exc_info.value)

    def test_likelihood_score_validator_rejects_too_high(self):
        """Test likelihood_score validator rejects values > 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            Transition(
                transition_id="TRANS-005",
                likelihood_score=1.5,
                confidence=ConfidenceLevel.HIGH,
            )
        assert "likelihood_score must be between 0.0 and 1.0" in str(exc_info.value)

    def test_likelihood_score_validator_coerces_to_float(self):
        """Test likelihood_score validator coerces to float."""
        transition = Transition(
            transition_id="TRANS-006",
            likelihood_score=1,
            confidence=ConfidenceLevel.HIGH,
        )
        assert transition.likelihood_score == 1.0
        assert isinstance(transition.likelihood_score, float)

    def test_transition_with_evidence(self):
        """Test transition with evidence bundle."""
        evidence = EvidenceBundle(
            items=[EvidenceItem(source="usaspending", signal="agency", score=0.95)]
        )
        transition = Transition(
            transition_id="TRANS-007",
            likelihood_score=0.95,
            confidence=ConfidenceLevel.HIGH,
            evidence=evidence,
        )
        assert transition.evidence is not None
        assert len(transition.evidence.items) == 1

    def test_transition_with_metadata(self):
        """Test transition with custom metadata."""
        transition = Transition(
            transition_id="TRANS-008",
            likelihood_score=0.80,
            confidence=ConfidenceLevel.LIKELY,
            metadata={"model_version": "v2.1", "custom_field": "value"},
        )
        assert transition.metadata["model_version"] == "v2.1"
        assert transition.metadata["custom_field"] == "value"


class TestTransitionProfile:
    """Tests for TransitionProfile model."""

    def test_valid_transition_profile(self):
        """Test creating a valid transition profile."""
        profile = TransitionProfile(
            company_id="COMPANY-001",
            total_awards=100,
            total_transitions=75,
            success_rate=0.75,
            avg_likelihood_score=0.82,
            avg_time_to_transition_days=180.5,
        )
        assert profile.company_id == "COMPANY-001"
        assert profile.total_awards == 100
        assert profile.total_transitions == 75
        assert profile.success_rate == 0.75

    def test_transition_profile_defaults(self):
        """Test transition profile with default values."""
        profile = TransitionProfile(company_id="COMPANY-002")
        assert profile.company_id == "COMPANY-002"
        assert profile.total_awards == 0
        assert profile.total_transitions == 0
        assert profile.success_rate == 0.0
        assert profile.avg_likelihood_score == 0.0
        assert profile.avg_time_to_transition_days is None
        assert isinstance(profile.last_updated, datetime)

    def test_total_awards_negative_rejected(self):
        """Test total_awards rejects negative values."""
        with pytest.raises(ValidationError):
            TransitionProfile(company_id="COMPANY-003", total_awards=-1)

    def test_total_transitions_negative_rejected(self):
        """Test total_transitions rejects negative values."""
        with pytest.raises(ValidationError):
            TransitionProfile(company_id="COMPANY-004", total_transitions=-5)

    def test_success_rate_validator_accepts_valid(self):
        """Test success_rate validator accepts 0-1 range."""
        profile = TransitionProfile(company_id="COMPANY-005", success_rate=0.5)
        assert profile.success_rate == 0.5

    def test_success_rate_validator_rejects_negative(self):
        """Test success_rate validator rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            TransitionProfile(company_id="COMPANY-006", success_rate=-0.1)
        assert "ratio fields must be between 0.0 and 1.0" in str(exc_info.value)

    def test_success_rate_validator_rejects_too_high(self):
        """Test success_rate validator rejects values > 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            TransitionProfile(company_id="COMPANY-007", success_rate=1.5)
        assert "ratio fields must be between 0.0 and 1.0" in str(exc_info.value)

    def test_avg_likelihood_score_validator_accepts_valid(self):
        """Test avg_likelihood_score validator accepts 0-1 range."""
        profile = TransitionProfile(company_id="COMPANY-008", avg_likelihood_score=0.88)
        assert profile.avg_likelihood_score == 0.88

    def test_avg_likelihood_score_validator_rejects_invalid(self):
        """Test avg_likelihood_score validator rejects invalid values."""
        with pytest.raises(ValidationError):
            TransitionProfile(company_id="COMPANY-009", avg_likelihood_score=2.0)

    def test_avg_time_to_transition_days_negative_rejected(self):
        """Test avg_time_to_transition_days rejects negative values."""
        with pytest.raises(ValidationError):
            TransitionProfile(
                company_id="COMPANY-010",
                avg_time_to_transition_days=-100.0,
            )

    def test_to_summary_property(self):
        """Test to_summary property method."""
        profile = TransitionProfile(
            company_id="COMPANY-011",
            total_awards=50,
            total_transitions=30,
            success_rate=0.60,
            avg_likelihood_score=0.75,
            avg_time_to_transition_days=200.5,
        )
        summary = profile.to_summary
        assert summary["company_id"] == "COMPANY-011"
        assert summary["total_awards"] == 50
        assert summary["total_transitions"] == 30
        assert summary["success_rate"] == 0.6
        assert summary["avg_likelihood_score"] == 0.75
        assert summary["avg_time_to_transition_days"] == 200.5
        assert "last_updated" in summary

    def test_to_summary_with_none_avg_score(self):
        """Test to_summary handles None avg_likelihood_score."""
        profile = TransitionProfile(
            company_id="COMPANY-012",
            total_awards=10,
            avg_likelihood_score=0.0,
        )
        summary = profile.to_summary
        assert summary["avg_likelihood_score"] == 0.0
