"""Unit tests for data models."""

from datetime import date

import pytest

from src.models import (
    Award,
    Company,
    EnrichmentResult,
    Patent,
    QualityIssue,
    QualityReport,
    QualitySeverity,
    Researcher,
)


class TestAwardModel:
    """Test Award model validation."""

    def test_valid_award(self):
        """Test creating a valid award."""
        award = Award(
            award_id="12345",
            company_name="Test Company",
            award_amount=100000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
        )
        assert award.award_id == "12345"
        assert award.program == "SBIR"  # Should be uppercased

    def test_invalid_award_amount(self):
        """Test invalid award amount."""
        with pytest.raises(ValueError, match="Award amount must be positive"):
            Award(
                award_id="12345",
                company_name="Test Company",
                award_amount=-1000.0,
                award_date=date(2023, 1, 1),
                program="SBIR",
            )

    def test_invalid_program(self):
        """Test invalid program."""
        with pytest.raises(ValueError, match="Program must be SBIR or STTR"):
            Award(
                award_id="12345",
                company_name="Test Company",
                award_amount=100000.0,
                award_date=date(2023, 1, 1),
                program="INVALID",
            )

    def test_program_normalization(self):
        """Test program name normalization."""
        award = Award(
            award_id="12345",
            company_name="Test Company",
            award_amount=100000.0,
            award_date=date(2023, 1, 1),
            program="sbir",
        )
        assert award.program == "SBIR"

    def test_invalid_phase(self):
        """Test invalid phase."""
        with pytest.raises(ValueError, match="Phase must be I, II, or III"):
            Award(
                award_id="12345",
                company_name="Test Company",
                award_amount=100000.0,
                award_date=date(2023, 1, 1),
                program="SBIR",
                phase="IV",
            )

    def test_phase_normalization(self):
        """Test phase normalization."""
        award = Award(
            award_id="12345",
            company_name="Test Company",
            award_amount=100000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
            phase="i",
        )
        assert award.phase == "I"


class TestCompanyModel:
    """Test Company model validation."""

    def test_valid_company(self):
        """Test creating a valid company."""
        company = Company(name="Test Company Inc.", duns="123456789", cage="ABC12")
        assert company.name == "Test Company Inc."
        assert company.duns == "123456789"
        assert company.cage == "ABC12"

    def test_invalid_duns(self):
        """Test invalid DUNS number."""
        with pytest.raises(ValueError, match="DUNS must be 9 digits"):
            Company(name="Test Company", duns="12345678")  # Too short

    def test_duns_normalization(self):
        """Test DUNS number normalization."""
        company = Company(name="Test Company", duns="123-456-789")  # With hyphens
        assert company.duns == "123456789"

    def test_invalid_cage(self):
        """Test invalid CAGE code."""
        with pytest.raises(ValueError, match="CAGE code must be 5 characters"):
            Company(name="Test Company", cage="ABCD")  # Too short

    def test_cage_normalization(self):
        """Test CAGE code normalization."""
        company = Company(name="Test Company", cage="abc12")  # Lowercase
        assert company.cage == "ABC12"


class TestResearcherModel:
    """Test Researcher model validation."""

    def test_valid_researcher(self):
        """Test creating a valid researcher."""
        researcher = Researcher(
            name="Dr. Jane Smith",
            email="jane.smith@university.edu",
            institution="Test University",
            department="Computer Science",
        )
        assert researcher.name == "Dr. Jane Smith"
        assert researcher.email == "jane.smith@university.edu"


class TestPatentModel:
    """Test Patent model validation."""

    def test_valid_patent(self):
        """Test creating a valid patent."""
        patent = Patent(
            patent_number="US12345678",
            title="Test Patent",
            inventors=["Inventor One", "Inventor Two"],
        )
        assert patent.patent_number == "US12345678"
        assert len(patent.inventors) == 2

    def test_invalid_patent_number(self):
        """Test invalid patent number."""
        with pytest.raises(ValueError, match="Patent number too short"):
            Patent(patent_number="US123", title="Test Patent", inventors=["Inventor One"])

    def test_empty_inventors_list(self):
        """Test empty inventors list."""
        with pytest.raises(ValueError, match="Inventors list cannot be empty"):
            Patent(patent_number="US12345678", title="Test Patent", inventors=[])


class TestQualityModels:
    """Test quality-related models."""

    def test_quality_issue_creation(self):
        """Test creating a quality issue."""
        issue = QualityIssue(
            field="company_name",
            value=None,
            expected="string",
            message="Company name is required",
            severity=QualitySeverity.HIGH,
            rule="completeness_check",
        )
        assert issue.field == "company_name"
        assert issue.severity == "high"  # Enum value

    def test_quality_report_creation(self):
        """Test creating a quality report."""
        report = QualityReport(
            record_id="award_123",
            stage="validation",
            timestamp="2023-01-01T00:00:00Z",
            total_fields=10,
            valid_fields=8,
            invalid_fields=2,
            completeness_score=0.8,
            validity_score=0.9,
            overall_score=0.85,
            passed=True,
        )
        assert report.record_id == "award_123"
        assert report.passed is True

    def test_enrichment_result_creation(self):
        """Test creating an enrichment result."""
        result = EnrichmentResult(
            record_id="company_123",
            source="sam_gov",
            timestamp="2023-01-01T00:00:00Z",
            fields_enriched=["duns", "cage"],
            enrichment_success=True,
            enriched_data={"duns": "123456789"},
            confidence_score=0.95,
        )
        assert result.record_id == "company_123"
        assert result.enrichment_success is True
        assert result.confidence_score == 0.95
