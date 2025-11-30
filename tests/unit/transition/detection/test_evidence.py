"""Tests for transition evidence generation."""

from datetime import date

import pytest

from src.models.transition_models import (
    AgencySignal,
    CETSignal,
    CompetitionSignal,
    CompetitionType,
    EvidenceBundle,
    EvidenceItem,
    FederalContract,
    PatentSignal,
    TimingSignal,
    TransitionSignals,
    VendorMatch,
)
from src.transition.detection.evidence import EvidenceGenerator


pytestmark = pytest.mark.fast


class TestEvidenceGeneratorInitialization:
    """Tests for EvidenceGenerator initialization."""

    def test_initialization(self):
        """Test EvidenceGenerator initialization."""
        generator = EvidenceGenerator()

        assert generator is not None


class TestGenerateAgencyEvidence:
    """Tests for generate_agency_evidence method."""

    @pytest.mark.parametrize(
        "same_agency,same_dept,score,expected_text",
        [
            (True, False, 1.0, "both from"),
            (False, True, 0.8, "same department"),
            (False, False, 0.2, "differs"),
        ],
        ids=["same_agency", "same_department", "different"],
    )
    def test_agency_evidence_scenarios(self, same_agency, same_dept, score, expected_text):
        """Test agency evidence generation with various scenarios."""
        from tests.assertions import assert_valid_evidence_item, assert_evidence_contains_text

        generator = EvidenceGenerator()
        signal = AgencySignal(
            same_agency=same_agency,
            same_department=same_dept,
            agency_score=score,
        )

        evidence = generator.generate_agency_evidence(
            signal=signal,
            award_agency="DOD",
            contract_agency="DOD" if same_agency else "NASA",
            award_department="DOD" if same_dept else None,
            contract_department="DOD" if same_dept else None,
        )

        assert_valid_evidence_item(evidence, expected_signal="agency")
        assert evidence.score == score
        assert_evidence_contains_text(evidence, expected_text)


class TestGenerateTimingEvidence:
    """Tests for generate_timing_evidence method."""

    @pytest.mark.parametrize(
        "days,score,expected_text",
        [
            (45, 0.9, "high proximity"),
            (180, 0.6, "moderate proximity"),
            (-30, 0.1, "before"),
        ],
        ids=["high_proximity", "moderate_proximity", "negative_days"],
    )
    def test_timing_evidence_scenarios(self, days, score, expected_text):
        """Test timing evidence with various temporal scenarios."""
        from tests.assertions import assert_valid_evidence_item, assert_evidence_contains_text

        generator = EvidenceGenerator()
        signal = TimingSignal(
            days_between_award_and_contract=days,
            months_between_award_and_contract=days / 30.0,
            timing_score=score,
        )

        evidence = generator.generate_timing_evidence(
            signal=signal,
            award_completion_date=date(2023, 1, 1),
            contract_start_date=date(2023, 1, 1),
        )

        assert_valid_evidence_item(evidence, expected_signal="timing")
        assert evidence.score == score
        assert_evidence_contains_text(evidence, expected_text)

    def test_generate_timing_evidence_incomplete_data(self):
        """Test timing evidence with incomplete timing data."""
        from tests.assertions import assert_evidence_contains_text

        generator = EvidenceGenerator()
        signal = TimingSignal(
            days_between_award_and_contract=None,
            months_between_award_and_contract=None,
            timing_score=0.0,
        )

        evidence = generator.generate_timing_evidence(
            signal=signal,
            award_completion_date=None,
            contract_start_date=None,
        )

        assert_evidence_contains_text(evidence, "incomplete")


class TestGenerateCompetitionEvidence:
    """Tests for generate_competition_evidence method."""

    @pytest.mark.parametrize(
        "comp_type,score,expected_text",
        [
            (CompetitionType.SOLE_SOURCE, 1.0, "Sole source"),
            (CompetitionType.LIMITED, 0.7, "Limited competition"),
            (CompetitionType.FULL_AND_OPEN, 0.3, "Full and open"),
        ],
        ids=["sole_source", "limited", "full_open"],
    )
    def test_competition_evidence_scenarios(self, comp_type, score, expected_text):
        """Test competition evidence with various competition types."""
        from tests.assertions import assert_valid_evidence_item, assert_evidence_contains_text

        generator = EvidenceGenerator()
        signal = CompetitionSignal(
            competition_type=comp_type,
            competition_score=score,
        )

        evidence = generator.generate_competition_evidence(
            signal=signal,
            contract_id="CONTRACT-123",
        )

        assert_valid_evidence_item(evidence, expected_signal="competition")
        assert evidence.score == score
        assert_evidence_contains_text(evidence, expected_text)


class TestGeneratePatentEvidence:
    """Tests for generate_patent_evidence method."""

    def test_generate_patent_evidence_with_patents(self):
        """Test patent evidence with patents found."""
        generator = EvidenceGenerator()

        signal = PatentSignal(
            patent_count=5,
            patents_pre_contract=3,
            patent_topic_similarity=0.85,
            patent_score=0.8,
        )

        evidence = generator.generate_patent_evidence(
            signal=signal,
            vendor_id="VENDOR-123",
            contract_start_date=date(2023, 6, 1),
        )

        assert evidence.signal == "patent"
        assert evidence.score == 0.8
        assert "5 patent(s)" in evidence.snippet
        assert "3 filed before contract" in evidence.snippet
        assert "0.85" in evidence.snippet
        assert evidence.metadata["patent_count"] == 5

    def test_generate_patent_evidence_no_patents(self):
        """Test patent evidence with no patents."""
        generator = EvidenceGenerator()

        signal = PatentSignal(
            patent_count=0,
            patents_pre_contract=0,
            patent_topic_similarity=None,
            patent_score=0.0,
        )

        evidence = generator.generate_patent_evidence(signal=signal)

        assert "No patents found" in evidence.snippet

    def test_generate_patent_evidence_with_topic_similarity(self):
        """Test patent evidence with topic similarity."""
        generator = EvidenceGenerator()

        signal = PatentSignal(
            patent_count=2,
            patents_pre_contract=2,
            patent_topic_similarity=0.92,
            patent_score=0.9,
        )

        evidence = generator.generate_patent_evidence(signal=signal)

        assert "topic similarity: 0.92" in evidence.snippet


class TestGenerateCETEvidence:
    """Tests for generate_cet_evidence method."""

    def test_generate_cet_evidence_same_area(self):
        """Test CET evidence with same CET area."""
        generator = EvidenceGenerator()

        signal = CETSignal(
            award_cet="artificial_intelligence",
            contract_cet="artificial_intelligence",
            cet_alignment_score=1.0,
        )

        evidence = generator.generate_cet_evidence(signal=signal)

        assert evidence.signal == "cet"
        assert evidence.score == 1.0
        assert "both in CET area" in evidence.snippet
        assert "artificial_intelligence" in evidence.snippet

    def test_generate_cet_evidence_different_areas(self):
        """Test CET evidence with different CET areas."""
        generator = EvidenceGenerator()

        signal = CETSignal(
            award_cet="artificial_intelligence",
            contract_cet="biotechnology",
            cet_alignment_score=0.3,
        )

        evidence = generator.generate_cet_evidence(signal=signal)

        assert "differs" in evidence.snippet
        assert "artificial_intelligence" in evidence.snippet
        assert "biotechnology" in evidence.snippet

    def test_generate_cet_evidence_partial_data(self):
        """Test CET evidence with only award CET."""
        generator = EvidenceGenerator()

        signal = CETSignal(
            award_cet="robotics",
            contract_cet=None,
            cet_alignment_score=0.5,
        )

        evidence = generator.generate_cet_evidence(signal=signal)

        assert "contract CET unknown" in evidence.snippet
        assert "robotics" in evidence.snippet

    def test_generate_cet_evidence_no_data(self):
        """Test CET evidence with no CET data."""
        generator = EvidenceGenerator()

        signal = CETSignal(
            award_cet=None,
            contract_cet=None,
            cet_alignment_score=0.0,
        )

        evidence = generator.generate_cet_evidence(signal=signal)

        assert "not available" in evidence.snippet


class TestGenerateVendorMatchEvidence:
    """Tests for generate_vendor_match_evidence method."""

    def test_generate_vendor_match_evidence_uei(self):
        """Test vendor match evidence with UEI match."""
        generator = EvidenceGenerator()

        vendor_match = VendorMatch(
            vendor_id="VENDOR-123",
            method="uei",
            score=1.0,
            matched_name="Acme Corporation",
            metadata={"uei": "ABC123XYZ"},
        )

        evidence = generator.generate_vendor_match_evidence(vendor_match)

        assert evidence.signal == "vendor_match"
        assert evidence.score == 1.0
        assert "exact UEI match" in evidence.snippet
        assert "Acme Corporation" in evidence.snippet

    def test_generate_vendor_match_evidence_fuzzy_name(self):
        """Test vendor match evidence with fuzzy name match."""
        generator = EvidenceGenerator()

        vendor_match = VendorMatch(
            vendor_id="VENDOR-456",
            method="name_fuzzy",
            score=0.85,
            matched_name="Acme Corp",
            metadata={"similarity": 0.85},
        )

        evidence = generator.generate_vendor_match_evidence(vendor_match)

        assert "fuzzy name match" in evidence.snippet
        assert "0.85" in evidence.snippet
        assert "Acme Corp" in evidence.snippet

    def test_generate_vendor_match_evidence_cage(self):
        """Test vendor match evidence with CAGE code match."""
        generator = EvidenceGenerator()

        vendor_match = VendorMatch(
            vendor_id="VENDOR-789",
            method="cage",
            score=1.0,
            matched_name="Defense Contractor Inc",
            metadata={"cage": "1A2B3"},
        )

        evidence = generator.generate_vendor_match_evidence(vendor_match)

        assert "exact CAGE code match" in evidence.snippet


class TestGenerateContractDetailsEvidence:
    """Tests for generate_contract_details_evidence method."""

    def test_generate_contract_details_evidence_complete(self):
        """Test contract details evidence with complete data."""
        generator = EvidenceGenerator()

        contract = FederalContract(
            contract_id="CONTRACT-123",
            vendor_id="VENDOR-456",
            vendor_name="Acme Corporation",
            agency="DOD",
            sub_agency="Army",
            start_date=date(2023, 1, 1),
            end_date=date(2024, 12, 31),
            obligation_amount=1000000.0,
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        evidence = generator.generate_contract_details_evidence(contract)

        assert evidence.signal == "contract_details"
        assert "CONTRACT-123" in evidence.snippet
        assert "DOD" in evidence.snippet
        assert "$1,000,000" in evidence.snippet
        assert "2023-01-01" in evidence.snippet

    def test_generate_contract_details_evidence_minimal(self):
        """Test contract details evidence with minimal data."""
        generator = EvidenceGenerator()

        contract = FederalContract(
            contract_id="CONTRACT-789",
            vendor_id="VENDOR-123",
            vendor_name="Test Vendor",
            agency=None,
            sub_agency=None,
            start_date=None,
            end_date=None,
            obligation_amount=None,
            competition_type=CompetitionType.OTHER,
        )

        evidence = generator.generate_contract_details_evidence(contract)

        assert "CONTRACT-789" in evidence.snippet
        assert evidence.metadata["contract_id"] == "CONTRACT-789"


class TestGenerateBundle:
    """Tests for generate_bundle method."""

    def test_generate_bundle_all_signals(self):
        """Test generating complete bundle with all signals."""
        generator = EvidenceGenerator()

        signals = TransitionSignals(
            agency=AgencySignal(same_agency=True, same_department=False, agency_score=1.0),
            timing=TimingSignal(
                days_between_award_and_contract=45,
                months_between_award_and_contract=1.5,
                timing_score=0.9,
            ),
            competition=CompetitionSignal(
                competition_type=CompetitionType.SOLE_SOURCE,
                competition_score=1.0,
            ),
            patent=PatentSignal(
                patent_count=3,
                patents_pre_contract=2,
                patent_topic_similarity=0.8,
                patent_score=0.7,
            ),
            cet=CETSignal(
                award_cet="ai",
                contract_cet="ai",
                cet_alignment_score=1.0,
            ),
        )

        award_data = {
            "award_id": "AWARD-123",
            "agency": "DOD",
            "completion_date": date(2023, 1, 1),
        }

        contract = FederalContract(
            contract_id="CONTRACT-456",
            vendor_id="VENDOR-789",
            vendor_name="Test Corp",
            agency="DOD",
            sub_agency="Army",
            start_date=date(2023, 2, 15),
            end_date=date(2024, 2, 15),
            obligation_amount=500000.0,
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        vendor_match = VendorMatch(
            vendor_id="VENDOR-789",
            method="uei",
            score=1.0,
            matched_name="Test Corp",
            metadata={},
        )

        bundle = generator.generate_bundle(
            signals=signals,
            award_data=award_data,
            contract=contract,
            vendor_match=vendor_match,
        )

        assert isinstance(bundle, EvidenceBundle)
        # Should have: agency, timing, competition, patent, cet, vendor_match, contract_details = 7 items
        assert len(bundle.items) == 7
        assert bundle.summary is not None
        assert "7 evidence items" in bundle.summary

    def test_generate_bundle_minimal_signals(self):
        """Test generating bundle with minimal signals."""
        generator = EvidenceGenerator()

        signals = TransitionSignals(
            agency=AgencySignal(same_agency=True, same_department=False, agency_score=1.0),
            timing=None,
            competition=None,
            patent=None,
            cet=None,
        )

        award_data = {"award_id": "AWARD-123", "agency": "DOD"}

        contract = FederalContract(
            contract_id="CONTRACT-456",
            vendor_id="VENDOR-789",
            vendor_name="Test Corp",
            agency="DOD",
            sub_agency=None,
            start_date=None,
            end_date=None,
            obligation_amount=None,
            competition_type=CompetitionType.OTHER,
        )

        bundle = generator.generate_bundle(
            signals=signals,
            award_data=award_data,
            contract=contract,
        )

        # Should have: agency, contract_details = 2 items
        assert len(bundle.items) == 2


class TestSerializeDeserialize:
    """Tests for serialize_bundle and deserialize_bundle methods."""

    def test_serialize_bundle(self):
        """Test serializing evidence bundle to JSON."""
        generator = EvidenceGenerator()

        bundle = EvidenceBundle()
        bundle.add_item(
            EvidenceItem(
                source="test",
                signal="test_signal",
                snippet="Test snippet",
                score=0.8,
                metadata={"key": "value"},
            )
        )

        json_str = generator.serialize_bundle(bundle)

        assert isinstance(json_str, str)
        assert "test_signal" in json_str
        assert "Test snippet" in json_str

    def test_deserialize_bundle(self):
        """Test deserializing evidence bundle from JSON."""
        generator = EvidenceGenerator()

        # Create and serialize a bundle
        bundle = EvidenceBundle()
        bundle.add_item(
            EvidenceItem(
                source="test",
                signal="test_signal",
                snippet="Test snippet",
                score=0.8,
                metadata={},
            )
        )

        json_str = generator.serialize_bundle(bundle)

        # Deserialize
        deserialized = generator.deserialize_bundle(json_str)

        assert isinstance(deserialized, EvidenceBundle)
        assert len(deserialized.items) == 1
        assert deserialized.items[0].signal == "test_signal"

    def test_serialize_deserialize_roundtrip(self):
        """Test serialize-deserialize round trip."""
        generator = EvidenceGenerator()

        original = EvidenceBundle()
        original.add_item(
            EvidenceItem(
                source="test1",
                signal="signal1",
                snippet="Snippet 1",
                score=0.7,
                metadata={"a": 1},
            )
        )
        original.add_item(
            EvidenceItem(
                source="test2",
                signal="signal2",
                snippet="Snippet 2",
                score=0.9,
                metadata={"b": 2},
            )
        )

        json_str = generator.serialize_bundle(original)
        restored = generator.deserialize_bundle(json_str)

        assert len(restored.items) == 2
        assert restored.items[0].signal == "signal1"
        assert restored.items[1].signal == "signal2"


class TestValidateBundle:
    """Tests for validate_bundle method."""

    def test_validate_bundle_valid(self):
        """Test validating a valid bundle."""
        generator = EvidenceGenerator()

        bundle = EvidenceBundle()
        bundle.add_item(
            EvidenceItem(
                source="test",
                signal="test_signal",
                snippet="Test",
                score=0.8,
                metadata={},
            )
        )

        assert generator.validate_bundle(bundle) is True

    def test_validate_bundle_empty(self):
        """Test validating empty bundle returns False."""
        generator = EvidenceGenerator()

        bundle = EvidenceBundle()

        assert generator.validate_bundle(bundle) is False

    def test_validate_bundle_missing_source(self):
        """Test validating bundle with missing source."""
        generator = EvidenceGenerator()

        bundle = EvidenceBundle()
        bundle.items = [
            EvidenceItem(
                source="",  # Empty source
                signal="test_signal",
                snippet="Test",
                score=0.8,
                metadata={},
            )
        ]

        assert generator.validate_bundle(bundle) is False

    def test_validate_bundle_score_out_of_range(self):
        """Test validating bundle with score out of range."""
        from pydantic import ValidationError

        # Pydantic should prevent creating item with invalid score
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            EvidenceItem(
                source="test",
                signal="test_signal",
                snippet="Test",
                score=1.5,  # Out of range
                metadata={},
            )

    def test_validate_bundle_negative_score(self):
        """Test validating bundle with negative score."""
        from pydantic import ValidationError

        EvidenceGenerator()

        # Pydantic validates at creation time, so we need to catch the error
        with pytest.raises(ValidationError, match="score"):
            EvidenceItem(
                source="test",
                signal="test_signal",
                snippet="Test",
                score=-0.1,  # Negative
                metadata={},
            )

    def test_validate_bundle_none_score_accepted(self):
        """Test validating bundle with None score (allowed)."""
        generator = EvidenceGenerator()

        bundle = EvidenceBundle()
        bundle.add_item(
            EvidenceItem(
                source="test",
                signal="test_signal",
                snippet="Test",
                score=None,
                metadata={},
            )
        )

        assert generator.validate_bundle(bundle) is True


class TestEdgeCases:
    """Tests for edge cases in evidence generation."""

    def test_generate_bundle_with_none_vendor_match(self):
        """Test generating bundle with None vendor_match."""
        generator = EvidenceGenerator()

        signals = TransitionSignals(
            agency=AgencySignal(same_agency=True, same_department=False, agency_score=1.0),
        )

        award_data = {"award_id": "AWARD-123"}

        contract = FederalContract(
            contract_id="CONTRACT-456",
            vendor_id="VENDOR-789",
            vendor_name="Test",
            agency="DOD",
            competition_type=CompetitionType.OTHER,
        )

        bundle = generator.generate_bundle(
            signals=signals,
            award_data=award_data,
            contract=contract,
            vendor_match=None,  # Explicitly None
        )

        # Should not include vendor_match evidence
        vendor_signals = [item for item in bundle.items if item.signal == "vendor_match"]
        assert len(vendor_signals) == 0

    def test_timing_evidence_very_long_delay(self):
        """Test timing evidence with very long delay (> 1 year)."""
        generator = EvidenceGenerator()

        signal = TimingSignal(
            days_between_award_and_contract=730,  # 2 years
            months_between_award_and_contract=24.0,
            timing_score=0.1,
        )

        evidence = generator.generate_timing_evidence(
            signal=signal,
            award_completion_date=date(2021, 1, 1),
            contract_start_date=date(2023, 1, 1),
        )

        assert "730 days" in evidence.snippet
        # Should not have "high" or "moderate" proximity
        assert "high proximity" not in evidence.snippet
        assert "moderate proximity" not in evidence.snippet

    def test_cet_evidence_case_insensitive_match(self):
        """Test CET evidence handles case-insensitive matching."""
        generator = EvidenceGenerator()

        signal = CETSignal(
            award_cet="Artificial_Intelligence",
            contract_cet="artificial_intelligence",
            cet_alignment_score=1.0,
        )

        evidence = generator.generate_cet_evidence(signal=signal)

        # Should recognize as same area (case-insensitive)
        assert "both in CET area" in evidence.snippet
