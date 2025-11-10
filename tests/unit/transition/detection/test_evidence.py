"""Tests for transition evidence generation."""

import pytest

from datetime import date

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

    def test_generate_agency_evidence_same_agency(self):
        """Test agency evidence with same agency."""
        generator = EvidenceGenerator()

        signal = AgencySignal(
            same_agency=True,
            same_department=False,
            agency_score=1.0,
        )

        evidence = generator.generate_agency_evidence(
            signal=signal,
            award_agency="DOD",
            contract_agency="DOD",
        )

        assert evidence.source == "sbir_award_data"
        assert evidence.signal == "agency"
        assert evidence.score == 1.0
        assert "both from DOD" in evidence.snippet
        assert evidence.metadata["same_agency"] is True

    def test_generate_agency_evidence_same_department(self):
        """Test agency evidence with same department but different agencies."""
        generator = EvidenceGenerator()

        signal = AgencySignal(
            same_agency=False,
            same_department=True,
            agency_score=0.8,
        )

        evidence = generator.generate_agency_evidence(
            signal=signal,
            award_agency="DOD-ARMY",
            contract_agency="DOD-NAVY",
            award_department="DOD",
            contract_department="DOD",
        )

        assert evidence.score == 0.8
        assert "same department" in evidence.snippet
        assert "DOD" in evidence.snippet
        assert evidence.metadata["same_department"] is True

    def test_generate_agency_evidence_different_agencies(self):
        """Test agency evidence with different agencies."""
        generator = EvidenceGenerator()

        signal = AgencySignal(
            same_agency=False,
            same_department=False,
            agency_score=0.2,
        )

        evidence = generator.generate_agency_evidence(
            signal=signal,
            award_agency="DOD",
            contract_agency="NASA",
        )

        assert evidence.score == 0.2
        assert "differs" in evidence.snippet
        assert "DOD" in evidence.snippet
        assert "NASA" in evidence.snippet


class TestGenerateTimingEvidence:
    """Tests for generate_timing_evidence method."""

    def test_generate_timing_evidence_high_proximity(self):
        """Test timing evidence with high temporal proximity (< 90 days)."""
        generator = EvidenceGenerator()

        signal = TimingSignal(
            days_between_award_and_contract=45,
            months_between_award_and_contract=1.5,
            timing_score=0.9,
        )

        evidence = generator.generate_timing_evidence(
            signal=signal,
            award_completion_date=date(2023, 1, 1),
            contract_start_date=date(2023, 2, 15),
            award_id="AWARD-123",
            contract_id="CONTRACT-456",
        )

        assert evidence.signal == "timing"
        assert evidence.score == 0.9
        assert "45 days" in evidence.snippet
        assert "high proximity" in evidence.snippet
        assert evidence.metadata["days_between"] == 45

    def test_generate_timing_evidence_moderate_proximity(self):
        """Test timing evidence with moderate proximity (90-365 days)."""
        generator = EvidenceGenerator()

        signal = TimingSignal(
            days_between_award_and_contract=180,
            months_between_award_and_contract=6.0,
            timing_score=0.6,
        )

        evidence = generator.generate_timing_evidence(
            signal=signal,
            award_completion_date=date(2023, 1, 1),
            contract_start_date=date(2023, 7, 1),
        )

        assert "180 days" in evidence.snippet
        assert "moderate proximity" in evidence.snippet

    def test_generate_timing_evidence_negative_days(self):
        """Test timing evidence with contract before award (anomaly)."""
        generator = EvidenceGenerator()

        signal = TimingSignal(
            days_between_award_and_contract=-30,
            months_between_award_and_contract=-1.0,
            timing_score=0.1,
        )

        evidence = generator.generate_timing_evidence(
            signal=signal,
            award_completion_date=date(2023, 2, 1),
            contract_start_date=date(2023, 1, 1),
        )

        assert "30 days before" in evidence.snippet
        assert "anomaly" in evidence.snippet

    def test_generate_timing_evidence_incomplete_data(self):
        """Test timing evidence with incomplete timing data."""
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

        assert "incomplete" in evidence.snippet


class TestGenerateCompetitionEvidence:
    """Tests for generate_competition_evidence method."""

    def test_generate_competition_evidence_sole_source(self):
        """Test competition evidence for sole source."""
        generator = EvidenceGenerator()

        signal = CompetitionSignal(
            competition_type=CompetitionType.SOLE_SOURCE,
            competition_score=1.0,
        )

        evidence = generator.generate_competition_evidence(
            signal=signal,
            contract_id="CONTRACT-123",
        )

        assert evidence.signal == "competition"
        assert evidence.score == 1.0
        assert "Sole source" in evidence.snippet
        assert "specifically targeted" in evidence.snippet

    def test_generate_competition_evidence_limited(self):
        """Test competition evidence for limited competition."""
        generator = EvidenceGenerator()

        signal = CompetitionSignal(
            competition_type=CompetitionType.LIMITED,
            competition_score=0.7,
        )

        evidence = generator.generate_competition_evidence(signal=signal)

        assert "Limited competition" in evidence.snippet
        assert "restricted vendor pool" in evidence.snippet

    def test_generate_competition_evidence_full_open(self):
        """Test competition evidence for full and open."""
        generator = EvidenceGenerator()

        signal = CompetitionSignal(
            competition_type=CompetitionType.FULL_AND_OPEN,
            competition_score=0.3,
        )

        evidence = generator.generate_competition_evidence(signal=signal)

        assert "Full and open" in evidence.snippet


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
        generator = EvidenceGenerator()

        bundle = EvidenceBundle()
        bundle.items = [
            EvidenceItem(
                source="test",
                signal="test_signal",
                snippet="Test",
                score=1.5,  # Out of range
                metadata={},
            )
        ]

        assert generator.validate_bundle(bundle) is False

    def test_validate_bundle_negative_score(self):
        """Test validating bundle with negative score."""
        generator = EvidenceGenerator()

        bundle = EvidenceBundle()
        bundle.items = [
            EvidenceItem(
                source="test",
                signal="test_signal",
                snippet="Test",
                score=-0.1,  # Negative
                metadata={},
            )
        ]

        assert generator.validate_bundle(bundle) is False

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
