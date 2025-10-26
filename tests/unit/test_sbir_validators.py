"""Unit tests for SBIR award validation functions."""

from datetime import date

import pandas as pd

from src.models.quality import QualitySeverity
from src.validators.sbir_awards import (
    validate_award_amount,
    validate_award_year,
    validate_award_year_date_consistency,
    validate_date_consistency,
    validate_duns_format,
    validate_email_format,
    validate_phase,
    validate_phase_program_consistency,
    validate_phone_format,
    validate_program,
    validate_required_field,
    validate_sbir_award_record,
    validate_sbir_awards,
    validate_state_code,
    validate_uei_format,
    validate_zip_code,
)


class TestValidateRequiredField:
    """Test required field validation."""

    def test_valid_required_field(self):
        """Test valid required field."""
        result = validate_required_field("Test Company", "Company", 0)
        assert result is None

    def test_missing_required_field(self):
        """Test missing required field."""
        result = validate_required_field("", "Company", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR
        assert "required" in result.message.lower()

    def test_none_required_field(self):
        """Test None required field."""
        result = validate_required_field(None, "Company", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidatePhase:
    """Test phase validation."""

    def test_valid_phase(self):
        """Test valid phase."""
        result = validate_phase("Phase I", 0)
        assert result is None

    def test_invalid_phase(self):
        """Test invalid phase."""
        result = validate_phase("Phase IV", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR
        assert "invalid phase" in result.message.lower()

    def test_missing_phase(self):
        """Test missing phase."""
        result = validate_phase(None, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateProgram:
    """Test program validation."""

    def test_valid_program_sbir(self):
        """Test valid SBIR program."""
        result = validate_program("SBIR", 0)
        assert result is None

    def test_valid_program_sttr(self):
        """Test valid STTR program."""
        result = validate_program("STTR", 0)
        assert result is None

    def test_invalid_program(self):
        """Test invalid program."""
        result = validate_program("OTHER", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR

    def test_missing_program(self):
        """Test missing program."""
        result = validate_program(None, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateAwardYear:
    """Test award year validation."""

    def test_valid_year(self):
        """Test valid award year."""
        result = validate_award_year(2020, 0)
        assert result is None

    def test_year_too_early(self):
        """Test year before 1983."""
        result = validate_award_year(1980, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR

    def test_year_too_late(self):
        """Test year after 2026."""
        result = validate_award_year(2030, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR

    def test_missing_year(self):
        """Test missing award year."""
        result = validate_award_year(None, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateAwardAmount:
    """Test award amount validation."""

    def test_valid_amount(self):
        """Test valid award amount."""
        result = validate_award_amount(100000, 0)
        assert result is None

    def test_amount_zero(self):
        """Test zero amount."""
        result = validate_award_amount(0, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR

    def test_amount_negative(self):
        """Test negative amount."""
        result = validate_award_amount(-1000, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR

    def test_amount_too_large(self):
        """Test amount exceeding maximum."""
        result = validate_award_amount(15000000, 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_amount_string_with_commas(self):
        """Test string amount with commas."""
        result = validate_award_amount("1,000,000", 0)
        assert result is None

    def test_invalid_amount_string(self):
        """Test invalid string amount."""
        result = validate_award_amount("invalid", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateUeiFormat:
    """Test UEI format validation."""

    def test_valid_uei(self):
        """Test valid UEI."""
        result = validate_uei_format("ABC123DEF456", 0)
        assert result is None

    def test_uei_too_short(self):
        """Test UEI too short."""
        result = validate_uei_format("ABC123", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_uei_with_special_chars(self):
        """Test UEI with special characters."""
        result = validate_uei_format("ABC-123-DEF", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_empty_uei(self):
        """Test empty UEI (optional)."""
        result = validate_uei_format("", 0)
        assert result is None


class TestValidateDunsFormat:
    """Test DUNS format validation."""

    def test_valid_duns(self):
        """Test valid DUNS."""
        result = validate_duns_format("123456789", 0)
        assert result is None

    def test_duns_too_short(self):
        """Test DUNS too short."""
        result = validate_duns_format("12345678", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_duns_with_letters(self):
        """Test DUNS with letters."""
        result = validate_duns_format("12345678A", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_empty_duns(self):
        """Test empty DUNS (optional)."""
        result = validate_duns_format("", 0)
        assert result is None


class TestValidateEmailFormat:
    """Test email format validation."""

    def test_valid_email(self):
        """Test valid email."""
        result = validate_email_format("test@example.com", "Contact Email", 0)
        assert result is None

    def test_invalid_email(self):
        """Test invalid email."""
        result = validate_email_format("invalid-email", "Contact Email", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_empty_email(self):
        """Test empty email (optional)."""
        result = validate_email_format("", "Contact Email", 0)
        assert result is None


class TestValidateStateCode:
    """Test state code validation."""

    def test_valid_state(self):
        """Test valid state code."""
        result = validate_state_code("CA", 0)
        assert result is None

    def test_invalid_state(self):
        """Test invalid state code."""
        result = validate_state_code("XX", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_state_too_long(self):
        """Test state code too long."""
        result = validate_state_code("CAL", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_empty_state(self):
        """Test empty state (optional)."""
        result = validate_state_code("", 0)
        assert result is None


class TestValidateZipCode:
    """Test ZIP code validation."""

    def test_valid_zip_5(self):
        """Test valid 5-digit ZIP."""
        result = validate_zip_code("12345", 0)
        assert result is None

    def test_valid_zip_9(self):
        """Test valid 9-digit ZIP."""
        result = validate_zip_code("123456789", 0)
        assert result is None

    def test_valid_zip_with_hyphen(self):
        """Test valid ZIP with hyphen."""
        result = validate_zip_code("12345-6789", 0)
        assert result is None

    def test_invalid_zip_length(self):
        """Test invalid ZIP length."""
        result = validate_zip_code("1234", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_zip_with_letters(self):
        """Test ZIP with letters."""
        result = validate_zip_code("1234A", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_empty_zip(self):
        """Test empty ZIP (optional)."""
        result = validate_zip_code("", 0)
        assert result is None


class TestValidateDateConsistency:
    """Test date consistency validation."""

    def test_valid_dates(self):
        """Test valid date order."""
        start = date(2020, 1, 1)
        end = date(2021, 1, 1)
        result = validate_date_consistency(start, end, 0)
        assert result is None

    def test_end_before_start(self):
        """Test end date before start date."""
        start = date(2021, 1, 1)
        end = date(2020, 1, 1)
        result = validate_date_consistency(start, end, 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_missing_dates(self):
        """Test missing dates."""
        result = validate_date_consistency(None, date(2021, 1, 1), 0)
        assert result is None


class TestValidatePhoneFormat:
    """Test phone format validation."""

    def test_valid_phone_with_parens(self):
        """Test valid phone with parentheses."""
        result = validate_phone_format("(123) 456-7890", "Contact Phone", 0)
        assert result is None

    def test_valid_phone_with_dashes(self):
        """Test valid phone with dashes."""
        result = validate_phone_format("123-456-7890", "Contact Phone", 0)
        assert result is None

    def test_valid_phone_with_dots(self):
        """Test valid phone with dots."""
        result = validate_phone_format("123.456.7890", "Contact Phone", 0)
        assert result is None

    def test_invalid_phone(self):
        """Test invalid phone format."""
        result = validate_phone_format("123-45-67890", "Contact Phone", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_empty_phone(self):
        """Test empty phone (optional)."""
        result = validate_phone_format("", "Contact Phone", 0)
        assert result is None


class TestValidateAwardYearDateConsistency:
    """Test award year and date consistency."""

    def test_matching_year(self):
        """Test matching year."""
        result = validate_award_year_date_consistency(2020, date(2020, 6, 1), 0)
        assert result is None

    def test_mismatched_year(self):
        """Test mismatched year."""
        result = validate_award_year_date_consistency(2020, date(2021, 6, 1), 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_missing_date(self):
        """Test missing date."""
        result = validate_award_year_date_consistency(2020, None, 0)
        assert result is None

    def test_missing_year(self):
        """Test missing year."""
        result = validate_award_year_date_consistency(None, date(2020, 6, 1), 0)
        assert result is None


class TestValidatePhaseProgramConsistency:
    """Test phase and program consistency."""

    def test_valid_sbir_phase(self):
        """Test valid SBIR phase."""
        result = validate_phase_program_consistency("Phase I", "SBIR", 0)
        assert result is None

    def test_valid_sttr_phase(self):
        """Test valid STTR phase."""
        result = validate_phase_program_consistency("Phase II", "STTR", 0)
        assert result is None

    def test_invalid_phase_for_program(self):
        """Test invalid phase for program."""
        result = validate_phase_program_consistency("Phase IV", "SBIR", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_missing_phase(self):
        """Test missing phase."""
        result = validate_phase_program_consistency(None, "SBIR", 0)
        assert result is None

    def test_missing_program(self):
        """Test missing program."""
        result = validate_phase_program_consistency("Phase I", None, 0)
        assert result is None


class TestValidateSbirAwardRecord:
    """Test validation of a single SBIR award record."""

    def test_valid_record(self):
        """Test valid record."""
        row = pd.Series(
            {
                "Company": "Test Company",
                "Award Title": "Test Award",
                "Agency": "NSF",
                "Phase": "Phase I",
                "Program": "SBIR",
                "Award Year": 2020,
                "Award Amount": 100000,
                "Proposal Award Date": date(2020, 1, 1),
                "Contract End Date": date(2021, 1, 1),
            }
        )
        issues = validate_sbir_award_record(row, 0)
        assert len(issues) == 0

    def test_record_with_issues(self):
        """Test record with validation issues."""
        row = pd.Series(
            {
                "Company": "",  # Missing
                "Award Title": "Test Award",
                "Agency": "NSF",
                "Phase": "Phase IV",  # Invalid
                "Program": "SBIR",
                "Award Year": 2020,
                "Award Amount": -1000,  # Invalid
                "Proposal Award Date": date(2021, 1, 1),  # Year mismatch
                "Contract End Date": date(2020, 1, 1),  # End before start
            }
        )
        issues = validate_sbir_award_record(row, 0)
        assert len(issues) > 0


class TestValidateSbirAwards:
    """Test validation of SBIR awards DataFrame."""

    def test_validate_empty_dataframe(self):
        """Test validation of empty DataFrame."""
        df = pd.DataFrame()
        report = validate_sbir_awards(df)
        assert report.total_records == 0
        assert report.passed_records == 0
        assert report.failed_records == 0

        assert report.passed is True  # Assuming default threshold

    def test_validate_with_custom_threshold(self):
        """Test validation with custom pass rate threshold."""
        df = pd.DataFrame(
            {
                "Company": ["", "Company B"],  # One invalid
                "Award Title": ["Award A", "Award B"],
                "Agency": ["NSF", "NIH"],
                "Phase": ["Phase I", "Phase II"],
                "Program": ["SBIR", "STTR"],
                "Award Year": [2020, 2021],
                "Award Amount": [100000, 200000],
            }
        )
        report = validate_sbir_awards(df, pass_rate_threshold=0.8)
        assert report.threshold == 0.8
        assert report.passed is False  # 50% pass rate < 80% threshold
