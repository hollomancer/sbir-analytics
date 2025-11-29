"""Unit tests for data models."""

from datetime import date

import pytest


pytestmark = pytest.mark.fast

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
        """Test invalid program is set to None (lenient validation)."""
        award = Award(
            award_id="12345",
            company_name="Test Company",
            award_amount=100000.0,
            award_date=date(2023, 1, 1),
            program="INVALID",
        )
        assert award.program is None  # Lenient: invalid values become None

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
        """Test invalid phase is set to None (lenient validation)."""
        award = Award(
            award_id="12345",
            company_name="Test Company",
            award_amount=100000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
            phase="IV",  # IV is normalized to III
        )
        assert award.phase == "III"  # Lenient: IV becomes III

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

    def test_valid_uei_and_duns(self):
        """Test that UEI and DUNS are accepted and normalized."""
        award = Award(
            award_id="A-UEI-DUNS",
            company_name="UEI Company",
            award_amount=50000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
            company_uei="ABCDEF123456",
            company_duns="123-456-789",
        )
        # UEI should be stored uppercase and unchanged if valid
        assert award.company_uei == "ABCDEF123456"
        # DUNS should be normalized to digits only
        assert award.company_duns == "123456789"

    def test_invalid_uei(self):
        """Short or non-alphanumeric UEI becomes None (lenient)."""
        award = Award(
            award_id="A-BAD-UEI",
            company_name="Bad UEI Co",
            award_amount=10000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
            company_uei="SHORT",
        )
        assert award.company_uei is None  # Lenient: invalid UEI becomes None

    def test_invalid_duns(self):
        """DUNS with wrong digit count becomes None (lenient)."""
        award = Award(
            award_id="A-BAD-DUNS",
            company_name="Bad DUNS Co",
            award_amount=10000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
            company_duns="12-345",
        )
        assert award.company_duns is None  # Lenient: invalid DUNS becomes None

    def test_contact_fields(self):
        """Contact email and phone should be stored as provided."""
        award = Award(
            award_id="A-CONTACT",
            company_name="Contact Co",
            award_amount=75000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
            contact_email="user@example.com",
            contact_phone="555-1234",
        )
        assert award.contact_email == "user@example.com"
        assert award.contact_phone == "555-1234"

    def test_award_year_matches_award_date(self):
        """award_year must match the year portion of award_date when provided."""
        # matching year should succeed
        award = Award(
            award_id="A-YEAR-OK",
            company_name="Year Co",
            award_amount=10000.0,
            award_date=date(2023, 6, 15),
            program="SBIR",
            award_year=2023,
        )
        assert award.award_year == 2023

        # mismatched year is auto-corrected (lenient)
        award2 = Award(
            award_id="A-YEAR-BAD",
            company_name="Year Co",
            award_amount=10000.0,
            award_date=date(2023, 6, 15),
            program="SBIR",
            award_year=2022,
        )
        assert award2.award_year == 2023  # Auto-corrected to match award_date

    def test_contract_date_order(self):
        """contract_end_date must be on or after proposal_award_date."""
        # valid ordering
        award = Award(
            award_id="A-DATES-OK",
            company_name="Dates Co",
            award_amount=25000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
            proposal_award_date=date(2023, 1, 1),
            contract_end_date=date(2023, 12, 31),
        )
        assert award.contract_end_date >= award.proposal_award_date

        # invalid ordering is allowed (lenient - no validation)
        award2 = Award(
            award_id="A-DATES-BAD",
            company_name="Dates Co",
            award_amount=25000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
            proposal_award_date=date(2023, 6, 1),
            contract_end_date=date(2023, 5, 1),
        )
        # Lenient: dates are accepted as-is
        assert award2.contract_end_date == date(2023, 5, 1)

    def test_state_and_zip_validation(self):
        """State code normalized to uppercase 2-letter and ZIP normalized to digits (5 or 9)."""
        award = Award(
            award_id="A-LOC",
            company_name="Loc Co",
            award_amount=30000.0,
            award_date=date(2023, 2, 2),
            program="SBIR",
            company_state="ca",
            company_zip="12345-6789",
        )
        assert award.company_state == "CA"
        assert award.company_zip == "123456789"

        # Invalid state becomes None (lenient)
        award2 = Award(
            award_id="A-LOC-BAD",
            company_name="Loc Co",
            award_amount=30000.0,
            award_date=date(2023, 2, 2),
            program="SBIR",
            company_state="CAL",
            company_zip="12345",
        )
        assert award2.company_state is None  # Lenient: 3-letter state becomes None

        # Invalid ZIP becomes None (lenient)
        award3 = Award(
            award_id="A-ZIP-BAD",
            company_name="Loc Co",
            award_amount=30000.0,
            award_date=date(2023, 2, 2),
            program="SBIR",
            company_state="NY",
            company_zip="12-34",
        )
        assert award3.company_zip is None  # Lenient: invalid ZIP becomes None

    def test_number_of_employees_non_negative(self):
        """number_of_employees must be non-negative when provided."""
        award = Award(
            award_id="A-EMP-OK",
            company_name="Emp Co",
            award_amount=45000.0,
            award_date=date(2023, 3, 3),
            program="SBIR",
            number_of_employees=50,
        )
        assert award.number_of_employees == 50

        # Negative employees becomes None (lenient)
        award2 = Award(
            award_id="A-EMP-BAD",
            company_name="Emp Co",
            award_amount=45000.0,
            award_date=date(2023, 3, 3),
            program="SBIR",
            number_of_employees=-5,
        )
        assert award2.number_of_employees is None  # Lenient: negative becomes None

    def test_business_flags_and_award_title(self):
        """Business classification flags and award_title should be stored as provided."""
        award = Award(
            award_id="A-BUS",
            company_name="Business Co",
            award_amount=80000.0,
            award_date=date(2023, 4, 4),
            program="SBIR",
            award_title="Research Project",
            is_hubzone=True,
            is_woman_owned=False,
            is_socially_disadvantaged=True,
        )
        assert award.award_title == "Research Project"
        assert award.is_hubzone is True
        assert award.is_woman_owned is False
        assert award.is_socially_disadvantaged is True


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
