"""
Unit tests for CET Pydantic models.

Tests validation logic, constraints, and business rules for CET data models.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.cet_models import (
    CETArea,
    CETAssessment,
    CETClassification,
    ClassificationLevel,
    CompanyCETProfile,
    EvidenceStatement,
)
from tests.factories import (
    CETAssessmentFactory,
    CETClassificationFactory,
    CompanyCETProfileFactory,
    EvidenceStatementFactory,
)

pytestmark = pytest.mark.fast


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
        evidence = EvidenceStatementFactory.create(
            excerpt="This project uses machine learning for pattern recognition",
            source_location="abstract",
        )

        assert "machine learning" in evidence.excerpt
        assert evidence.source_location == "abstract"

    def test_excerpt_too_long(self) -> None:
        """Test that very long excerpts are rejected."""
        long_text = " ".join(["word"] * 100)  # 100 words
        with pytest.raises(ValidationError, match="50 words"):
            EvidenceStatementFactory.create(excerpt=long_text)

    def test_invalid_source_location(self) -> None:
        """Test that invalid source locations are rejected."""
        with pytest.raises(ValidationError, match="Source location"):
            EvidenceStatementFactory.create(source_location="invalid_location")

    @pytest.mark.parametrize(
        "location", ["abstract", "keywords", "solicitation", "title", "description"]
    )
    def test_valid_source_locations(self, location: str) -> None:
        """Test all valid source locations."""
        evidence = EvidenceStatementFactory.create(source_location=location)
        assert evidence.source_location == location


class TestCETClassification:
    """Tests for CETClassification model."""

    def test_high_confidence_classification(self) -> None:
        """Test high confidence classification (score >= 70)."""
        classification = CETClassificationFactory.create(
            score=85.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
        )

        assert classification.score == 85.0
        assert classification.classification == ClassificationLevel.HIGH
        assert classification.primary is True

    def test_medium_confidence_classification(self) -> None:
        """Test medium confidence classification (40 <= score < 70)."""
        classification = CETClassificationFactory.create(
            score=55.0,
            classification=ClassificationLevel.MEDIUM,
            primary=False,
        )

        assert classification.classification == ClassificationLevel.MEDIUM

    def test_low_confidence_classification(self) -> None:
        """Test low confidence classification (score < 40)."""
        classification = CETClassificationFactory.create(
            score=25.0,
            classification=ClassificationLevel.LOW,
            primary=False,
        )

        assert classification.classification == ClassificationLevel.LOW

    @pytest.mark.parametrize("score", [150.0, -10.0])
    def test_score_out_of_range(self, score: float) -> None:
        """Test that scores outside 0-100 are rejected."""
        with pytest.raises(ValidationError):
            CETClassificationFactory.create(score=score)

    @pytest.mark.parametrize(
        "score,classification",
        [
            (85.0, ClassificationLevel.MEDIUM),
            (30.0, ClassificationLevel.HIGH),
        ],
    )
    def test_classification_mismatch_with_score(
        self, score: float, classification: ClassificationLevel
    ) -> None:
        """Test that classification level must match score thresholds."""
        with pytest.raises(ValidationError, match="does not match score"):
            CETClassificationFactory.create(
                score=score,
                classification=classification,
            )

    def test_too_many_evidence_statements(self) -> None:
        """Test that more than 3 evidence statements are rejected."""
        evidence = [
            EvidenceStatementFactory.create(excerpt=f"Evidence {i}") for i in range(5)
        ]

        with pytest.raises(ValidationError, match="Maximum 3 evidence"):
            CETClassificationFactory.create(evidence=evidence)


class TestCETAssessment:
    """Tests for CETAssessment model."""

    def test_valid_assessment(self) -> None:
        """Test creating a valid CET assessment."""
        primary = CETClassificationFactory.create(primary=True)
        supporting = [CETClassificationFactory.create(primary=False)]

        assessment = CETAssessmentFactory.create(
            entity_id="award_123",
            primary_cet=primary,
            supporting_cets=supporting,
        )

        assert assessment.entity_id == "award_123"
        assert assessment.primary_cet.primary is True
        assert len(assessment.supporting_cets) == 1

    def test_invalid_entity_type(self) -> None:
        """Test that invalid entity types are rejected."""
        with pytest.raises(ValidationError, match="Entity type"):
            CETAssessmentFactory.create(entity_type="invalid_type")

    def test_too_many_supporting_cets(self) -> None:
        """Test that more than 3 supporting CETs are rejected."""
        supporting = [
            CETClassificationFactory.create(primary=False, cet_id=f"cet_{i}")
            for i in range(5)
        ]

        with pytest.raises(ValidationError, match="Maximum 3 supporting"):
            CETAssessmentFactory.create(supporting_cets=supporting)

    def test_primary_cet_must_have_primary_true(self) -> None:
        """Test that primary CET must have primary=True."""
        not_primary = CETClassificationFactory.create(primary=False)

        with pytest.raises(ValidationError, match="Primary CET must have primary=True"):
            CETAssessmentFactory.create(primary_cet=not_primary)

    def test_supporting_cets_must_have_primary_false(self) -> None:
        """Test that supporting CETs must have primary=False."""
        supporting = [CETClassificationFactory.create(primary=True)]

        with pytest.raises(ValidationError, match="Supporting CETs must have primary=False"):
            CETAssessmentFactory.create(supporting_cets=supporting)


class TestCompanyCETProfile:
    """Tests for CompanyCETProfile model."""

    def test_valid_company_profile(self) -> None:
        """Test creating a valid company CET profile."""
        profile = CompanyCETProfileFactory.create(
            company_id="company_123",
            award_count=15,
        )

        assert profile.company_id == "company_123"
        assert profile.award_count == 15
        assert 0 <= profile.specialization_score <= 1

    def test_specialization_score_bounds(self) -> None:
        """Test that specialization score is between 0 and 1."""
        with pytest.raises(ValidationError):
            CompanyCETProfileFactory.create(specialization_score=1.5)

    def test_minimum_award_count(self) -> None:
        """Test that award count must be >= 1."""
        with pytest.raises(ValidationError):
            CompanyCETProfileFactory.create(award_count=0)

    def test_negative_funding(self) -> None:
        """Test that negative funding is rejected."""
        with pytest.raises(ValidationError):
            CompanyCETProfileFactory.create(total_funding=-100.0)
