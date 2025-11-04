"""
Unit tests for CET Pydantic models.

Tests validation logic, constraints, and business rules for CET data models.
"""

from datetime import datetime

import pytest

pytestmark = pytest.mark.fast
from pydantic import ValidationError

from src.models.cet_models import (
    CETArea,
    CETAssessment,
    CETClassification,
    ClassificationLevel,
    CompanyCETProfile,
    EvidenceStatement,
)


class TestCETArea:
    """Tests for CETArea model."""

    def test_valid_cet_area(self) -> None:
        """Test creating a valid CET area."""
        area = CETArea(
            cet_id="artificial_intelligence",
            name="Artificial Intelligence",
            definition="AI and ML technologies",
            keywords=["machine learning", "deep learning", "ai"],
            taxonomy_version="NSTC-2025Q1",
        )

        assert area.cet_id == "artificial_intelligence"
        assert area.name == "Artificial Intelligence"
        assert len(area.keywords) == 3
        assert area.parent_cet_id is None

    def test_cet_id_lowercase_normalization(self) -> None:
        """Test that CET ID is normalized to lowercase."""
        area = CETArea(
            cet_id="Artificial_Intelligence",
            name="AI",
            definition="AI tech",
            taxonomy_version="NSTC-2025Q1",
        )

        assert area.cet_id == "artificial_intelligence"

    def test_invalid_cet_id_characters(self) -> None:
        """Test that invalid characters in CET ID are rejected."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            CETArea(
                cet_id="artificial-intelligence!",
                name="AI",
                definition="AI tech",
                taxonomy_version="NSTC-2025Q1",
            )


class TestEvidenceStatement:
    """Tests for EvidenceStatement model."""

    def test_valid_evidence(self) -> None:
        """Test creating valid evidence."""
        evidence = EvidenceStatement(
            excerpt="This project uses machine learning for pattern recognition",
            source_location="abstract",
            rationale_tag="Contains: machine learning",
        )

        assert "machine learning" in evidence.excerpt
        assert evidence.source_location == "abstract"

    def test_excerpt_too_long(self) -> None:
        """Test that very long excerpts are rejected."""
        long_text = " ".join(["word"] * 100)  # 100 words
        with pytest.raises(ValidationError, match="50 words"):
            EvidenceStatement(
                excerpt=long_text,
                source_location="abstract",
                rationale_tag="test",
            )

    def test_invalid_source_location(self) -> None:
        """Test that invalid source locations are rejected."""
        with pytest.raises(ValidationError, match="Source location"):
            EvidenceStatement(
                excerpt="test",
                source_location="invalid_location",
                rationale_tag="test",
            )

    def test_valid_source_locations(self) -> None:
        """Test all valid source locations."""
        valid_locations = ["abstract", "keywords", "solicitation", "title", "description"]

        for location in valid_locations:
            evidence = EvidenceStatement(
                excerpt="test excerpt",
                source_location=location,
                rationale_tag="test",
            )
            assert evidence.source_location == location


class TestCETClassification:
    """Tests for CETClassification model."""

    def test_high_confidence_classification(self) -> None:
        """Test high confidence classification (score >= 70)."""
        classification = CETClassification(
            cet_id="artificial_intelligence",
            score=85.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
            evidence=[],
        )

        assert classification.score == 85.0
        assert classification.classification == ClassificationLevel.HIGH
        assert classification.primary is True

    def test_medium_confidence_classification(self) -> None:
        """Test medium confidence classification (40 <= score < 70)."""
        classification = CETClassification(
            cet_id="biotechnologies",
            score=55.0,
            classification=ClassificationLevel.MEDIUM,
            primary=False,
        )

        assert classification.classification == ClassificationLevel.MEDIUM

    def test_low_confidence_classification(self) -> None:
        """Test low confidence classification (score < 40)."""
        classification = CETClassification(
            cet_id="hypersonics",
            score=25.0,
            classification=ClassificationLevel.LOW,
            primary=False,
        )

        assert classification.classification == ClassificationLevel.LOW

    def test_score_out_of_range(self) -> None:
        """Test that scores outside 0-100 are rejected."""
        with pytest.raises(ValidationError):
            CETClassification(
                cet_id="ai",
                score=150.0,
                classification=ClassificationLevel.HIGH,
                primary=True,
            )

        with pytest.raises(ValidationError):
            CETClassification(
                cet_id="ai",
                score=-10.0,
                classification=ClassificationLevel.LOW,
                primary=True,
            )

    def test_classification_mismatch_with_score(self) -> None:
        """Test that classification level must match score thresholds."""
        # Score 85 should be HIGH, not MEDIUM
        with pytest.raises(ValidationError, match="does not match score"):
            CETClassification(
                cet_id="ai",
                score=85.0,
                classification=ClassificationLevel.MEDIUM,
                primary=True,
            )

        # Score 30 should be LOW, not HIGH
        with pytest.raises(ValidationError, match="does not match score"):
            CETClassification(
                cet_id="ai",
                score=30.0,
                classification=ClassificationLevel.HIGH,
                primary=True,
            )

    def test_too_many_evidence_statements(self) -> None:
        """Test that more than 3 evidence statements are rejected."""
        evidence = [
            EvidenceStatement(
                excerpt=f"Evidence {i}", source_location="abstract", rationale_tag="test"
            )
            for i in range(5)
        ]

        with pytest.raises(ValidationError, match="Maximum 3 evidence"):
            CETClassification(
                cet_id="ai",
                score=75.0,
                classification=ClassificationLevel.HIGH,
                primary=True,
                evidence=evidence,
            )


class TestCETAssessment:
    """Tests for CETAssessment model."""

    def test_valid_assessment(self) -> None:
        """Test creating a valid CET assessment."""
        primary = CETClassification(
            cet_id="artificial_intelligence",
            score=85.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
        )

        supporting = [
            CETClassification(
                cet_id="autonomous_systems",
                score=65.0,
                classification=ClassificationLevel.MEDIUM,
                primary=False,
            )
        ]

        assessment = CETAssessment(
            entity_id="award_123",
            entity_type="award",
            primary_cet=primary,
            supporting_cets=supporting,
            taxonomy_version="NSTC-2025Q1",
            model_version="v1.0.0",
        )

        assert assessment.entity_id == "award_123"
        assert assessment.primary_cet.primary is True
        assert len(assessment.supporting_cets) == 1
        assert all(not cet.primary for cet in assessment.supporting_cets)

    def test_invalid_entity_type(self) -> None:
        """Test that invalid entity types are rejected."""
        primary = CETClassification(
            cet_id="ai",
            score=75.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
        )

        with pytest.raises(ValidationError, match="Entity type"):
            CETAssessment(
                entity_id="test",
                entity_type="invalid_type",
                primary_cet=primary,
                taxonomy_version="NSTC-2025Q1",
                model_version="v1.0.0",
            )

    def test_too_many_supporting_cets(self) -> None:
        """Test that more than 3 supporting CETs are rejected."""
        primary = CETClassification(
            cet_id="ai",
            score=85.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
        )

        supporting = [
            CETClassification(
                cet_id=f"cet_{i}",
                score=60.0,
                classification=ClassificationLevel.MEDIUM,
                primary=False,
            )
            for i in range(5)
        ]

        with pytest.raises(ValidationError, match="Maximum 3 supporting"):
            CETAssessment(
                entity_id="test",
                entity_type="award",
                primary_cet=primary,
                supporting_cets=supporting,
                taxonomy_version="NSTC-2025Q1",
                model_version="v1.0.0",
            )

    def test_primary_cet_must_have_primary_true(self) -> None:
        """Test that primary CET must have primary=True."""
        # Create a classification with primary=False
        not_primary = CETClassification(
            cet_id="ai",
            score=85.0,
            classification=ClassificationLevel.HIGH,
            primary=False,  # Wrong!
        )

        with pytest.raises(ValidationError, match="Primary CET must have primary=True"):
            CETAssessment(
                entity_id="test",
                entity_type="award",
                primary_cet=not_primary,
                taxonomy_version="NSTC-2025Q1",
                model_version="v1.0.0",
            )

    def test_supporting_cets_must_have_primary_false(self) -> None:
        """Test that supporting CETs must have primary=False."""
        primary = CETClassification(
            cet_id="ai",
            score=85.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
        )

        # Create supporting with primary=True (wrong!)
        supporting = [
            CETClassification(
                cet_id="quantum",
                score=60.0,
                classification=ClassificationLevel.MEDIUM,
                primary=True,  # Wrong!
            )
        ]

        with pytest.raises(ValidationError, match="Supporting CETs must have primary=False"):
            CETAssessment(
                entity_id="test",
                entity_type="award",
                primary_cet=primary,
                supporting_cets=supporting,
                taxonomy_version="NSTC-2025Q1",
                model_version="v1.0.0",
            )


class TestCompanyCETProfile:
    """Tests for CompanyCETProfile model."""

    def test_valid_company_profile(self) -> None:
        """Test creating a valid company CET profile."""
        profile = CompanyCETProfile(
            company_id="company_123",
            dominant_cet_id="artificial_intelligence",
            award_count=15,
            total_funding=5000000.0,
            avg_score=78.5,
            specialization_score=0.65,
            dominant_phase="II",
            first_award_date=datetime(2020, 1, 1),
            last_award_date=datetime(2024, 12, 31),
            cet_areas=["artificial_intelligence", "autonomous_systems", "biotechnologies"],
        )

        assert profile.company_id == "company_123"
        assert profile.dominant_cet_id == "artificial_intelligence"
        assert profile.award_count == 15
        assert 0 <= profile.specialization_score <= 1

    def test_specialization_score_bounds(self) -> None:
        """Test that specialization score is between 0 and 1."""
        with pytest.raises(ValidationError):
            CompanyCETProfile(
                company_id="test",
                dominant_cet_id="ai",
                award_count=5,
                total_funding=1000000.0,
                avg_score=75.0,
                specialization_score=1.5,  # Invalid: > 1
            )

    def test_minimum_award_count(self) -> None:
        """Test that award count must be >= 1."""
        with pytest.raises(ValidationError):
            CompanyCETProfile(
                company_id="test",
                dominant_cet_id="ai",
                award_count=0,  # Invalid: must be >= 1
                total_funding=0.0,
                avg_score=50.0,
                specialization_score=0.5,
            )

    def test_negative_funding(self) -> None:
        """Test that negative funding is rejected."""
        with pytest.raises(ValidationError):
            CompanyCETProfile(
                company_id="test",
                dominant_cet_id="ai",
                award_count=1,
                total_funding=-100.0,  # Invalid: negative
                avg_score=50.0,
                specialization_score=0.5,
            )
