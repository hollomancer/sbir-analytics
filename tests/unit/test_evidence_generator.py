"""
Unit tests for evidence bundle generation.

Tests the EvidenceGenerator's ability to create comprehensive,
auditable evidence trails for transition detections.
"""

import json
from datetime import date

import pytest


pytestmark = pytest.mark.fast

from src.models.transition_models import (
    AgencySignal,
    CETSignal,
    CompetitionSignal,
    CompetitionType,
    EvidenceBundle,
    FederalContract,
    PatentSignal,
    TimingSignal,
    TransitionSignals,
    VendorMatch,
)
from src.transition.detection.evidence import EvidenceGenerator


@pytest.fixture
def generator():
    """Create evidence generator instance."""
    return EvidenceGenerator()


@pytest.fixture
def sample_signals():
    """Create sample transition signals for testing."""
    return TransitionSignals(
        agency=AgencySignal(
            same_agency=True,
            same_department=True,
            agency_score=0.0625,
        ),
        timing=TimingSignal(
            days_between_award_and_contract=180,
            months_between_award_and_contract=6.0,
            timing_score=0.15,
        ),
        competition=CompetitionSignal(
            competition_type=CompetitionType.SOLE_SOURCE,
            competition_score=0.04,
        ),
        patent=PatentSignal(
            patent_count=3,
            patents_pre_contract=2,
            patent_topic_similarity=0.85,
            patent_score=0.015,
        ),
        cet=CETSignal(
            award_cet="AI/ML",
            contract_cet="AI/ML",
            cet_alignment_score=0.005,
        ),
        text_similarity_score=0.72,
    )


@pytest.fixture
def sample_award_data() -> dict:
    """Sample award data for testing."""
    return {
        "award_id": "AWARD-123",
        "agency": "DOD",
        "department": "Air Force",
        "completion_date": date(2024, 1, 15),
        "vendor_id": "VENDOR-001",
    }


@pytest.fixture
def sample_contract_data() -> dict:
    """Sample contract data for testing."""
    return {
        "contract_id": "CONTRACT-456",
        "agency": "DOD",
        "department": "Air Force",
        "start_date": date(2024, 7, 15),
        "competition_type": CompetitionType.SOLE_SOURCE,
    }


@pytest.fixture
def sample_vendor_match():
    """Sample vendor match for testing."""
    return VendorMatch(
        vendor_id="VENDOR-001",
        method="uei",
        score=1.0,
        matched_name="Acme Corp",
        metadata={"uei": "ABC123XYZ"},
    )


@pytest.fixture
def sample_contract():
    """Sample federal contract for testing."""
    return FederalContract(
        contract_id="CONTRACT-456",
        agency="DOD",
        sub_agency="Air Force",
        vendor_name="Acme Corp",
        vendor_uei="ABC123XYZ",
        start_date=date(2024, 7, 15),
        obligation_amount=500000.0,
        competition_type=CompetitionType.SOLE_SOURCE,
        description="Advanced AI system development",
    )


class TestAgencyEvidence:
    """Test agency continuity evidence generation."""

    def test_same_agency_evidence(self, generator):
        """Test evidence for same agency."""
        signal = AgencySignal(same_agency=True, agency_score=0.0625)

        evidence = generator.generate_agency_evidence(
            signal=signal,
            award_agency="DOD",
            contract_agency="DOD",
        )

        assert evidence.source == "sbir_award_data"
        assert evidence.signal == "agency"
        assert evidence.score == 0.0625
        assert "both from DOD" in evidence.snippet
        assert evidence.metadata["same_agency"] is True

    def test_different_agency_evidence(self, generator):
        """Test evidence for different agencies."""
        signal = AgencySignal(same_agency=False, agency_score=0.0125)

        evidence = generator.generate_agency_evidence(
            signal=signal,
            award_agency="DOD",
            contract_agency="NASA",
        )

        assert evidence.signal == "agency"
        assert "differs from" in evidence.snippet
        assert evidence.metadata["same_agency"] is False

    def test_same_department_evidence(self, generator):
        """Test evidence for same department, different agency."""
        signal = AgencySignal(
            same_agency=False,
            same_department=True,
            agency_score=0.03125,
        )

        evidence = generator.generate_agency_evidence(
            signal=signal,
            award_agency="Army",
            contract_agency="Navy",
            award_department="DOD",
            contract_department="DOD",
        )

        assert "within same department" in evidence.snippet
        assert evidence.metadata["same_department"] is True


class TestTimingEvidence:
    """Test timing proximity evidence generation."""

    def test_high_proximity_evidence(self, generator):
        """Test evidence for contract shortly after award."""
        signal = TimingSignal(
            days_between_award_and_contract=45,
            months_between_award_and_contract=1.5,
            timing_score=0.2,
        )

        evidence = generator.generate_timing_evidence(
            signal=signal,
            award_completion_date=date(2024, 1, 1),
            contract_start_date=date(2024, 2, 15),
        )

        assert evidence.signal == "timing"
        assert "high proximity" in evidence.snippet
        assert evidence.metadata["days_between"] == 45

    def test_moderate_proximity_evidence(self, generator):
        """Test evidence for moderate timing gap."""
        signal = TimingSignal(
            days_between_award_and_contract=180,
            months_between_award_and_contract=6.0,
            timing_score=0.15,
        )

        evidence = generator.generate_timing_evidence(
            signal=signal,
            award_completion_date=date(2024, 1, 1),
            contract_start_date=date(2024, 7, 1),
        )

        assert "moderate proximity" in evidence.snippet

    def test_negative_timing_evidence(self, generator):
        """Test evidence for contract before award completion (anomaly)."""
        signal = TimingSignal(
            days_between_award_and_contract=-30,
            months_between_award_and_contract=-1.0,
            timing_score=0.0,
        )

        evidence = generator.generate_timing_evidence(
            signal=signal,
            award_completion_date=date(2024, 2, 1),
            contract_start_date=date(2024, 1, 1),
        )

        assert "before award completion" in evidence.snippet
        assert "anomaly" in evidence.snippet


class TestCompetitionEvidence:
    """Test competition type evidence generation."""

    def test_sole_source_evidence(self, generator):
        """Test evidence for sole source contract."""
        signal = CompetitionSignal(
            competition_type=CompetitionType.SOLE_SOURCE,
            competition_score=0.04,
        )

        evidence = generator.generate_competition_evidence(signal=signal)

        assert evidence.source == "usaspending"
        assert evidence.signal == "competition"
        assert "Sole source" in evidence.snippet
        assert "specifically targeted" in evidence.snippet

    def test_limited_competition_evidence(self, generator):
        """Test evidence for limited competition."""
        signal = CompetitionSignal(
            competition_type=CompetitionType.LIMITED,
            competition_score=0.02,
        )

        evidence = generator.generate_competition_evidence(signal=signal)

        assert "Limited competition" in evidence.snippet

    def test_full_open_evidence(self, generator):
        """Test evidence for full and open competition."""
        signal = CompetitionSignal(
            competition_type=CompetitionType.FULL_AND_OPEN,
            competition_score=0.0,
        )

        evidence = generator.generate_competition_evidence(signal=signal)

        assert "Full and open" in evidence.snippet


class TestPatentEvidence:
    """Test patent signal evidence generation."""

    def test_patents_with_similarity(self, generator):
        """Test evidence for patents with topic similarity."""
        signal = PatentSignal(
            patent_count=5,
            patents_pre_contract=3,
            patent_topic_similarity=0.85,
            patent_score=0.015,
        )

        evidence = generator.generate_patent_evidence(
            signal=signal,
            vendor_id="VENDOR-001",
        )

        assert evidence.source == "patentsview"
        assert evidence.signal == "patent"
        assert "5 patent(s)" in evidence.snippet
        assert "3 filed before contract" in evidence.snippet
        assert "similarity: 0.85" in evidence.snippet

    def test_no_patents_evidence(self, generator):
        """Test evidence when no patents found."""
        signal = PatentSignal(
            patent_count=0,
            patents_pre_contract=0,
            patent_score=0.0,
        )

        evidence = generator.generate_patent_evidence(signal=signal)

        assert "No patents found" in evidence.snippet


class TestCETEvidence:
    """Test CET area alignment evidence generation."""

    def test_cet_alignment_evidence(self, generator):
        """Test evidence for CET area match."""
        signal = CETSignal(
            award_cet="AI/ML",
            contract_cet="AI/ML",
            cet_alignment_score=0.005,
        )

        evidence = generator.generate_cet_evidence(signal=signal)

        assert evidence.signal == "cet"
        assert "both in CET area: AI/ML" in evidence.snippet

    def test_cet_mismatch_evidence(self, generator):
        """Test evidence for CET area mismatch."""
        signal = CETSignal(
            award_cet="AI/ML",
            contract_cet="Quantum",
            cet_alignment_score=0.0,
        )

        evidence = generator.generate_cet_evidence(signal=signal)

        assert "differs from" in evidence.snippet


class TestVendorMatchEvidence:
    """Test vendor matching evidence generation."""

    def test_uei_match_evidence(self, generator, sample_vendor_match):
        """Test evidence for UEI-based match."""
        evidence = generator.generate_vendor_match_evidence(sample_vendor_match)

        assert evidence.source == "vendor_crosswalk"
        assert evidence.signal == "vendor_match"
        assert "exact UEI match" in evidence.snippet
        assert "Acme Corp" in evidence.snippet

    def test_fuzzy_match_evidence(self, generator):
        """Test evidence for fuzzy name match."""
        match = VendorMatch(
            vendor_id="VENDOR-002",
            method="name_fuzzy",
            score=0.87,
            matched_name="Acme Corporation",
        )

        evidence = generator.generate_vendor_match_evidence(match)

        assert "fuzzy name match" in evidence.snippet
        assert "0.87" in evidence.snippet


class TestContractDetailsEvidence:
    """Test contract details evidence generation."""

    def test_contract_details_evidence(self, generator, sample_contract):
        """Test evidence for contract details."""
        evidence = generator.generate_contract_details_evidence(sample_contract)

        assert evidence.source == "usaspending"
        assert evidence.signal == "contract_details"
        assert "CONTRACT-456" in evidence.snippet
        assert "DOD" in evidence.snippet
        assert "$500,000" in evidence.snippet
        assert "2024-07-15" in evidence.snippet


class TestBundleGeneration:
    """Test complete evidence bundle generation."""

    def test_generate_full_bundle(
        self,
        generator,
        sample_signals,
        sample_award_data,
        sample_contract_data,
        sample_vendor_match,
        sample_contract,
    ):
        """Test generation of complete evidence bundle."""
        bundle = generator.generate_bundle(
            signals=sample_signals,
            award_data=sample_award_data,
            contract=sample_contract,
            vendor_match=sample_vendor_match,
        )

        # Check bundle has expected items
        assert isinstance(bundle, EvidenceBundle)
        assert len(bundle.items) >= 6  # agency, timing, competition, patent, cet, vendor

        # Check summary generated
        assert bundle.summary is not None
        assert "evidence items" in bundle.summary

        # Check each signal type present
        signals_found = {item.signal for item in bundle.items}
        assert "agency" in signals_found
        assert "timing" in signals_found
        assert "competition" in signals_found
        assert "patent" in signals_found
        assert "cet" in signals_found
        assert "vendor_match" in signals_found

    def test_bundle_serialization(
        self,
        generator,
        sample_signals,
        sample_award_data,
        sample_contract_data,
        sample_contract,
    ):
        """Test evidence bundle JSON serialization."""
        bundle = generator.generate_bundle(
            signals=sample_signals,
            award_data=sample_award_data,
            contract=sample_contract,
        )

        # Serialize to JSON
        json_str = generator.serialize_bundle(bundle)
        assert json_str
        assert isinstance(json_str, str)

        # Check valid JSON
        parsed = json.loads(json_str)
        assert "items" in parsed
        assert "created_at" in parsed

    def test_bundle_deserialization(
        self,
        generator,
        sample_signals,
        sample_award_data,
        sample_contract_data,
    ):
        """Test evidence bundle JSON deserialization."""
        # Create and serialize bundle
        original_bundle = generator.generate_bundle(
            signals=sample_signals,
            award_data=sample_award_data,
            contract_data=sample_contract_data,
        )
        json_str = generator.serialize_bundle(original_bundle)

        # Deserialize
        restored_bundle = generator.deserialize_bundle(json_str)

        assert isinstance(restored_bundle, EvidenceBundle)
        assert len(restored_bundle.items) == len(original_bundle.items)

    def test_bundle_validation_valid(
        self,
        generator,
        sample_signals,
        sample_award_data,
        sample_contract_data,
    ):
        """Test validation of valid evidence bundle."""
        bundle = generator.generate_bundle(
            signals=sample_signals,
            award_data=sample_award_data,
            contract_data=sample_contract_data,
        )

        assert generator.validate_bundle(bundle) is True

    def test_bundle_validation_empty(self, generator):
        """Test validation rejects empty bundle."""
        empty_bundle = EvidenceBundle(items=[])

        assert generator.validate_bundle(empty_bundle) is False

    def test_bundle_total_score(
        self,
        generator,
        sample_signals,
        sample_award_data,
        sample_contract_data,
    ):
        """Test bundle total score calculation."""
        bundle = generator.generate_bundle(
            signals=sample_signals,
            award_data=sample_award_data,
            contract_data=sample_contract_data,
        )

        total_score = bundle.total_score()
        assert 0.0 <= total_score <= 1.0
        assert total_score > 0.0  # Should have some score


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_minimal_signals(self, generator):
        """Test bundle generation with minimal signals."""
        minimal_signals = TransitionSignals(
            agency=AgencySignal(same_agency=False, agency_score=0.0),
        )

        bundle = generator.generate_bundle(
            signals=minimal_signals,
            award_data={"award_id": "TEST"},
            contract_data={"contract_id": "TEST"},
        )

        assert len(bundle.items) >= 1
        assert any(item.signal == "agency" for item in bundle.items)

    def test_none_optional_fields(self, generator):
        """Test handling of None values in optional fields."""
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

        assert evidence.signal == "timing"
        assert "incomplete" in evidence.snippet.lower()
