"""Tests for CET and USPTO patent models."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError


pytestmark = pytest.mark.fast

from src.models.cet_models import (
    CETArea,
    CETAssessment,
    CETClassification,
    ClassificationLevel,
    CompanyCETProfile,
    EvidenceStatement,
    TrainingExample,
)
from src.models.uspto_models import (
    ConveyanceType,
    PatentAssignee,
    PatentAssignor,
    PatentConveyance,
    PatentDocument,
)


# ============================================================================
# CET Models Tests
# ============================================================================


pytestmark = pytest.mark.fast


class TestClassificationLevel:
    """Tests for ClassificationLevel enum."""

    def test_classification_level_values(self):
        """Test ClassificationLevel enum has correct values."""
        assert ClassificationLevel.HIGH == "High"
        assert ClassificationLevel.MEDIUM == "Medium"
        assert ClassificationLevel.LOW == "Low"


class TestCETArea:
    """Tests for CETArea model."""

    def test_valid_cet_area(self):
        """Test creating a valid CET area."""
        area = CETArea(
            cet_id="artificial_intelligence",
            name="Artificial Intelligence",
            definition="AI systems and machine learning technologies",
            keywords=["AI", "machine learning", "neural networks"],
            parent_cet_id=None,
            taxonomy_version="NSTC-2025Q1",
        )
        assert area.cet_id == "artificial_intelligence"
        assert len(area.keywords) == 3

    def test_cet_id_validator_normalizes_lowercase(self):
        """Test cet_id validator normalizes to lowercase."""
        area = CETArea(
            cet_id="Quantum_Computing",
            name="Quantum Computing",
            definition="Quantum information science",
            taxonomy_version="NSTC-2025Q1",
        )
        assert area.cet_id == "quantum_computing"

    def test_cet_id_validator_rejects_invalid_chars(self):
        """Test cet_id validator rejects non-alphanumeric characters."""
        with pytest.raises(ValidationError) as exc_info:
            CETArea(
                cet_id="artificial-intelligence!",  # Invalid: hyphen and !
                name="AI",
                definition="AI tech",
                taxonomy_version="NSTC-2025Q1",
            )
        assert "must contain only alphanumeric characters and underscores" in str(exc_info.value)

    def test_cet_area_hierarchical(self):
        """Test CET area with parent relationship."""
        area = CETArea(
            cet_id="deep_learning",
            name="Deep Learning",
            definition="Subset of machine learning using neural networks",
            parent_cet_id="artificial_intelligence",
            taxonomy_version="NSTC-2025Q1",
        )
        assert area.parent_cet_id == "artificial_intelligence"


class TestEvidenceStatement:
    """Tests for EvidenceStatement model."""

    def test_valid_evidence_statement(self):
        """Test creating a valid evidence statement."""
        statement = EvidenceStatement(
            excerpt="Development of novel quantum algorithms for cryptography",
            source_location="abstract",
            rationale_tag="Contains: quantum, algorithms, cryptography",
        )
        assert statement.source_location == "abstract"
        assert "quantum" in statement.excerpt

    def test_excerpt_length_validator_accepts_valid(self):
        """Test excerpt validator accepts text under 60 words."""
        words = " ".join(["word"] * 50)
        statement = EvidenceStatement(
            excerpt=words,
            source_location="keywords",
            rationale_tag="test",
        )
        assert len(statement.excerpt.split()) == 50

    def test_excerpt_length_validator_rejects_too_long(self):
        """Test excerpt validator rejects text over 60 words."""
        words = " ".join(["word"] * 70)
        with pytest.raises(ValidationError) as exc_info:
            EvidenceStatement(
                excerpt=words,
                source_location="abstract",
                rationale_tag="test",
            )
        assert "approximately 50 words or less" in str(exc_info.value)

    def test_source_location_validator_accepts_valid(self):
        """Test source_location validator accepts valid locations."""
        valid_locations = ["abstract", "keywords", "solicitation", "title", "description"]
        for location in valid_locations:
            statement = EvidenceStatement(
                excerpt="Test excerpt",
                source_location=location,
                rationale_tag="test",
            )
            assert statement.source_location == location

    def test_source_location_validator_rejects_invalid(self):
        """Test source_location validator rejects invalid locations."""
        with pytest.raises(ValidationError) as exc_info:
            EvidenceStatement(
                excerpt="Test",
                source_location="invalid_location",
                rationale_tag="test",
            )
        assert "Source location must be one of" in str(exc_info.value)


class TestCETClassification:
    """Tests for CETClassification model."""

    def test_valid_cet_classification_high(self):
        """Test creating a valid high-confidence classification."""
        classification = CETClassification(
            cet_id="artificial_intelligence",
            cet_name="Artificial Intelligence",
            score=85.5,
            classification=ClassificationLevel.HIGH,
            primary=True,
            evidence=[
                EvidenceStatement(
                    excerpt="AI and machine learning",
                    source_location="abstract",
                    rationale_tag="AI keywords",
                )
            ],
            classified_at="2023-06-15T10:00:00Z",
            taxonomy_version="NSTC-2025Q1",
        )
        assert classification.score == 85.5
        assert classification.classification == ClassificationLevel.HIGH
        assert classification.primary is True

    def test_score_constraints(self):
        """Test score field has 0-100 constraints."""
        # Valid bounds
        CETClassification(
            cet_id="test",
            score=0.0,
            classification=ClassificationLevel.LOW,
            primary=True,
        )
        CETClassification(
            cet_id="test",
            score=100.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
        )

        # Invalid bounds
        with pytest.raises(ValidationError):
            CETClassification(
                cet_id="test",
                score=-1.0,
                classification=ClassificationLevel.LOW,
                primary=True,
            )
        with pytest.raises(ValidationError):
            CETClassification(
                cet_id="test",
                score=105.0,
                classification=ClassificationLevel.HIGH,
                primary=True,
            )

    def test_evidence_count_validator_accepts_valid(self):
        """Test evidence validator accepts up to 3 statements."""
        evidence = [
            EvidenceStatement(
                excerpt=f"Evidence {i}", source_location="abstract", rationale_tag="test"
            )
            for i in range(3)
        ]
        classification = CETClassification(
            cet_id="test",
            score=75.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
            evidence=evidence,
        )
        assert len(classification.evidence) == 3

    def test_evidence_count_validator_rejects_too_many(self):
        """Test evidence validator rejects more than 3 statements."""
        evidence = [
            EvidenceStatement(
                excerpt=f"Evidence {i}", source_location="abstract", rationale_tag="test"
            )
            for i in range(4)
        ]
        with pytest.raises(ValidationError) as exc_info:
            CETClassification(
                cet_id="test",
                score=75.0,
                classification=ClassificationLevel.HIGH,
                primary=True,
                evidence=evidence,
            )
        assert "Maximum 3 evidence statements" in str(exc_info.value)

    def test_classification_validator_high_score(self):
        """Test classification validator for HIGH (score >= 70)."""
        CETClassification(
            cet_id="test",
            score=70.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
        )
        CETClassification(
            cet_id="test",
            score=95.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
        )

    def test_classification_validator_medium_score(self):
        """Test classification validator for MEDIUM (40 <= score < 70)."""
        CETClassification(
            cet_id="test",
            score=40.0,
            classification=ClassificationLevel.MEDIUM,
            primary=True,
        )
        CETClassification(
            cet_id="test",
            score=69.9,
            classification=ClassificationLevel.MEDIUM,
            primary=True,
        )

    def test_classification_validator_low_score(self):
        """Test classification validator for LOW (score < 40)."""
        CETClassification(
            cet_id="test",
            score=0.0,
            classification=ClassificationLevel.LOW,
            primary=True,
        )
        CETClassification(
            cet_id="test",
            score=39.9,
            classification=ClassificationLevel.LOW,
            primary=True,
        )

    def test_classification_validator_rejects_mismatch(self):
        """Test classification validator rejects score/level mismatch."""
        with pytest.raises(ValidationError) as exc_info:
            CETClassification(
                cet_id="test",
                score=85.0,  # Should be HIGH
                classification=ClassificationLevel.MEDIUM,  # Wrong!
                primary=True,
            )
        assert "does not match score" in str(exc_info.value)


class TestCETAssessment:
    """Tests for CETAssessment model."""

    def test_valid_cet_assessment(self):
        """Test creating a valid CET assessment."""
        primary = CETClassification(
            cet_id="ai",
            score=85.0,
            classification=ClassificationLevel.HIGH,
            primary=True,
        )
        supporting = [
            CETClassification(
                cet_id="quantum",
                score=55.0,
                classification=ClassificationLevel.MEDIUM,
                primary=False,
            )
        ]
        assessment = CETAssessment(
            entity_id="AWARD-001",
            entity_type="award",
            primary_cet=primary,
            supporting_cets=supporting,
            taxonomy_version="NSTC-2025Q1",
            model_version="v1.0.0",
        )
        assert assessment.entity_type == "award"
        assert len(assessment.supporting_cets) == 1

    def test_entity_type_validator_accepts_valid(self):
        """Test entity_type validator accepts valid types."""
        valid_types = ["award", "company", "patent"]
        for entity_type in valid_types:
            primary = CETClassification(
                cet_id="test", score=70.0, classification=ClassificationLevel.HIGH, primary=True
            )
            assessment = CETAssessment(
                entity_id="TEST-001",
                entity_type=entity_type,
                primary_cet=primary,
                taxonomy_version="NSTC-2025Q1",
                model_version="v1.0.0",
            )
            assert assessment.entity_type == entity_type

    def test_entity_type_validator_rejects_invalid(self):
        """Test entity_type validator rejects invalid types."""
        primary = CETClassification(
            cet_id="test", score=70.0, classification=ClassificationLevel.HIGH, primary=True
        )
        with pytest.raises(ValidationError) as exc_info:
            CETAssessment(
                entity_id="TEST-002",
                entity_type="invalid_type",
                primary_cet=primary,
                taxonomy_version="NSTC-2025Q1",
                model_version="v1.0.0",
            )
        assert "Entity type must be one of" in str(exc_info.value)

    def test_supporting_cets_count_validator(self):
        """Test supporting_cets validator limits to 3."""
        primary = CETClassification(
            cet_id="primary", score=80.0, classification=ClassificationLevel.HIGH, primary=True
        )
        supporting = [
            CETClassification(
                cet_id=f"sup{i}",
                score=50.0,
                classification=ClassificationLevel.MEDIUM,
                primary=False,
            )
            for i in range(4)
        ]
        with pytest.raises(ValidationError) as exc_info:
            CETAssessment(
                entity_id="TEST-003",
                entity_type="award",
                primary_cet=primary,
                supporting_cets=supporting,
                taxonomy_version="NSTC-2025Q1",
                model_version="v1.0.0",
            )
        assert "Maximum 3 supporting CET areas" in str(exc_info.value)

    def test_supporting_cets_primary_flag_validator(self):
        """Test supporting_cets validator rejects primary=True."""
        primary = CETClassification(
            cet_id="primary", score=80.0, classification=ClassificationLevel.HIGH, primary=True
        )
        supporting = [
            CETClassification(
                cet_id="bad",
                score=50.0,
                classification=ClassificationLevel.MEDIUM,
                primary=True,  # Wrong!
            )
        ]
        with pytest.raises(ValidationError) as exc_info:
            CETAssessment(
                entity_id="TEST-004",
                entity_type="award",
                primary_cet=primary,
                supporting_cets=supporting,
                taxonomy_version="NSTC-2025Q1",
                model_version="v1.0.0",
            )
        assert "Supporting CETs must have primary=False" in str(exc_info.value)

    def test_primary_cet_validator(self):
        """Test primary_cet validator requires primary=True."""
        primary_wrong = CETClassification(
            cet_id="primary",
            score=80.0,
            classification=ClassificationLevel.HIGH,
            primary=False,  # Wrong!
        )
        with pytest.raises(ValidationError) as exc_info:
            CETAssessment(
                entity_id="TEST-005",
                entity_type="award",
                primary_cet=primary_wrong,
                taxonomy_version="NSTC-2025Q1",
                model_version="v1.0.0",
            )
        assert "Primary CET must have primary=True" in str(exc_info.value)


class TestCompanyCETProfile:
    """Tests for CompanyCETProfile model."""

    def test_valid_company_cet_profile(self):
        """Test creating a valid company CET profile."""
        profile = CompanyCETProfile(
            company_id="COMPANY-001",
            dominant_cet_id="artificial_intelligence",
            award_count=25,
            total_funding=5000000.0,
            avg_score=82.5,
            specialization_score=0.75,
            dominant_phase="II",
            first_award_date=datetime(2018, 1, 1),
            last_award_date=datetime(2023, 12, 31),
            cet_areas=["artificial_intelligence", "quantum_computing", "biotechnology"],
        )
        assert profile.award_count == 25
        assert profile.specialization_score == 0.75
        assert len(profile.cet_areas) == 3

    def test_award_count_constraints(self):
        """Test award_count must be >= 1."""
        with pytest.raises(ValidationError):
            CompanyCETProfile(
                company_id="COMPANY-002",
                dominant_cet_id="ai",
                award_count=0,  # Invalid
                total_funding=100000.0,
                avg_score=75.0,
                specialization_score=0.5,
            )

    def test_total_funding_constraints(self):
        """Test total_funding must be >= 0."""
        with pytest.raises(ValidationError):
            CompanyCETProfile(
                company_id="COMPANY-003",
                dominant_cet_id="ai",
                award_count=5,
                total_funding=-1000.0,  # Invalid
                avg_score=75.0,
                specialization_score=0.5,
            )

    def test_avg_score_constraints(self):
        """Test avg_score must be 0-100."""
        with pytest.raises(ValidationError):
            CompanyCETProfile(
                company_id="COMPANY-004",
                dominant_cet_id="ai",
                award_count=5,
                total_funding=100000.0,
                avg_score=105.0,  # Invalid
                specialization_score=0.5,
            )

    def test_specialization_score_constraints(self):
        """Test specialization_score must be 0-1."""
        with pytest.raises(ValidationError):
            CompanyCETProfile(
                company_id="COMPANY-005",
                dominant_cet_id="ai",
                award_count=5,
                total_funding=100000.0,
                avg_score=75.0,
                specialization_score=1.5,  # Invalid
            )


class TestTrainingExample:
    """Tests for TrainingExample model."""

    def test_valid_training_example(self):
        """Test creating a valid training example."""
        example = TrainingExample(
            example_id="TRAIN-001",
            text="Development of AI-powered diagnostic tools",
            title="AI Medical Diagnostics",
            keywords="artificial intelligence, healthcare, diagnostics",
            solicitation="AI in Healthcare",
            labels=["artificial_intelligence", "biotechnology"],
            label_confidence=0.95,
            source="test",  # Required field
        )
        assert example.example_id == "TRAIN-001"
        assert len(example.labels) == 2
        assert example.label_confidence == 0.95

    def test_training_example_minimal(self):
        """Test training example with only required fields."""
        example = TrainingExample(
            example_id="TRAIN-002",
            text="Quantum computing research",
            labels=["quantum_computing"],
            source="test",  # Required field
        )
        assert example.title is None
        assert example.keywords is None
        assert example.label_confidence is None


# ============================================================================
# USPTO Models Tests
# ============================================================================


class TestConveyanceType:
    """Tests for ConveyanceType enum."""

    def test_conveyance_type_values(self):
        """Test ConveyanceType enum has correct values."""
        assert ConveyanceType.ASSIGNMENT == "assignment"
        assert ConveyanceType.LICENSE == "license"
        assert ConveyanceType.SECURITY_INTEREST == "security_interest"
        assert ConveyanceType.MERGER == "merger"
        assert ConveyanceType.OTHER == "other"


class TestPatentDocument:
    """Tests for PatentDocument model."""

    def test_valid_patent_document(self):
        """Test creating a valid patent document."""
        doc = PatentDocument(
            rf_id="DOC-001",
            application_number="16/123456",
            publication_number="US-2021-0123456-A1",
            grant_number="US10123456B2",
            filing_date=date(2020, 1, 15),
            publication_date=date(2021, 4, 20),
            grant_date=date(2022, 6, 10),
            language="EN",
            title="Innovative Technology",
            abstract="This invention describes...",
            raw={"source": "uspto"},
        )
        assert doc.grant_number == "US10123456B2"
        assert doc.filing_date == date(2020, 1, 15)

    def test_patent_document_minimal(self):
        """Test patent document with no fields."""
        doc = PatentDocument()
        assert doc.rf_id is None
        assert doc.application_number is None
        assert doc.raw == {}

    def test_identifier_normalization(self):
        """Test patent number normalization."""
        doc = PatentDocument(
            application_number="16 / 123,456",  # Will be normalized
            publication_number="US 2021 0123456 A1",
            grant_number="us-10,123,456-b2",
        )
        # Normalizer removes spaces, slashes, commas and uppercases
        assert doc.application_number == "16123456"
        assert doc.publication_number == "US20210123456A1"
        assert doc.grant_number == "US-10123456-B2"  # Hyphens preserved

    def test_date_parsing_iso_format(self):
        """Test date parsing from ISO format strings."""
        doc = PatentDocument(
            filing_date="2020-01-15",
            publication_date="2021-04-20",
            grant_date="2022-06-10",
        )
        assert doc.filing_date == date(2020, 1, 15)
        assert doc.publication_date == date(2021, 4, 20)
        assert doc.grant_date == date(2022, 6, 10)

    def test_date_parsing_us_format(self):
        """Test date parsing from US format strings."""
        doc = PatentDocument(
            filing_date="01/15/2020",
        )
        assert doc.filing_date == date(2020, 1, 15)

    def test_date_parsing_datetime_objects(self):
        """Test date parsing from datetime objects."""
        doc = PatentDocument(
            filing_date=datetime(2020, 1, 15, 10, 30),
        )
        assert doc.filing_date == date(2020, 1, 15)


class TestPatentAssignee:
    """Tests for PatentAssignee model."""

    def test_valid_patent_assignee(self):
        """Test creating a valid patent assignee."""
        assignee = PatentAssignee(
            rf_id="ASSIGNEE-001",
            name="Acme Corporation",
            street="123 Main St",
            city="Boston",
            state="MA",
            postal_code="02101",
            country="US",
            uei="ABC123DEF456",  # pragma: allowlist secret
            cage="1A2B3",
            duns="123456789",
            metadata={"source": "uspto"},
        )
        assert assignee.name == "Acme Corporation"
        assert assignee.city == "Boston"

    def test_assignee_name_validator_rejects_empty(self):
        """Test assignee name validator rejects empty names."""
        with pytest.raises(ValidationError) as exc_info:
            PatentAssignee(name="")
        assert "Assignee name must be non-empty" in str(exc_info.value)

    def test_assignee_name_validator_normalizes_whitespace(self):
        """Test assignee name validator normalizes whitespace."""
        assignee = PatentAssignee(name="Acme    Corporation   Inc")
        assert assignee.name == "Acme Corporation Inc"

    def test_postal_code_coercion(self):
        """Test postal_code coerces numeric values to strings."""
        assignee = PatentAssignee(
            name="Test Corp",
            postal_code=2101,  # Numeric
        )
        assert assignee.postal_code == "2101"

    def test_identifier_normalization(self):
        """Test UEI, CAGE, DUNS normalization."""
        assignee = PatentAssignee(
            name="Test Corp",
            uei="abc-123-def-456",
            cage="1a2b3",
            duns="12-345-6789",
        )
        # UEI normalization now preserves hyphens, only uppercases
        assert assignee.uei == "ABC-123-DEF-456"  # pragma: allowlist secret
        assert assignee.cage == "1A2B3"
        assert assignee.duns == "123456789"


class TestPatentAssignor:
    """Tests for PatentAssignor model."""

    def test_valid_patent_assignor(self):
        """Test creating a valid patent assignor."""
        assignor = PatentAssignor(
            rf_id="ASSIGNOR-001",
            name="John Doe",
            execution_date=date(2023, 1, 15),
            acknowledgment_date=date(2023, 1, 20),
            metadata={"type": "individual"},
        )
        assert assignor.name == "John Doe"
        assert assignor.execution_date == date(2023, 1, 15)

    def test_assignor_minimal(self):
        """Test assignor with minimal fields."""
        assignor = PatentAssignor()
        assert assignor.rf_id is None
        assert assignor.name is None
        assert assignor.metadata == {}

    def test_assignor_name_normalization(self):
        """Test assignor name normalization."""
        assignor = PatentAssignor(name="John  /  Doe  &  Associates")
        # Normalize removes commas, slashes, ampersands
        assert "John" in assignor.name
        assert "Doe" in assignor.name

    def test_assignor_date_parsing(self):
        """Test assignor date parsing."""
        assignor = PatentAssignor(
            execution_date="2023-01-15",
            acknowledgment_date="01/20/2023",
        )
        assert assignor.execution_date == date(2023, 1, 15)
        assert assignor.acknowledgment_date == date(2023, 1, 20)


class TestPatentConveyance:
    """Tests for PatentConveyance model."""

    def test_valid_patent_conveyance(self):
        """Test creating a valid patent conveyance."""
        conveyance = PatentConveyance(rf_id="CONV-001")
        assert conveyance.rf_id == "CONV-001"

    def test_conveyance_minimal(self):
        """Test conveyance with no fields."""
        conveyance = PatentConveyance()
        assert conveyance.rf_id is None
