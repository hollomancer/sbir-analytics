"""Tests for SBIR award validation rules."""

from datetime import date

import pandas as pd

from src.models.quality import QualitySeverity
from src.validators.sbir_awards import (
    EMAIL_REGEX,
    PHONE_REGEX,
    VALID_US_STATES,
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


class TestConstants:
    """Tests for module constants."""

    def test_valid_us_states_contains_all_states(self):
        """Test VALID_US_STATES contains 50 states + DC + territories."""
        assert "CA" in VALID_US_STATES
        assert "NY" in VALID_US_STATES
        assert "DC" in VALID_US_STATES
        assert "PR" in VALID_US_STATES  # Puerto Rico
        assert len(VALID_US_STATES) >= 50

    def test_email_regex_matches_valid_emails(self):
        """Test EMAIL_REGEX matches valid email addresses."""
        assert EMAIL_REGEX.match("test@example.com")
        assert EMAIL_REGEX.match("user.name@domain.org")
        assert EMAIL_REGEX.match("user+tag@test-domain.com")

    def test_email_regex_rejects_invalid_emails(self):
        """Test EMAIL_REGEX rejects invalid email addresses."""
        assert not EMAIL_REGEX.match("invalid")
        assert not EMAIL_REGEX.match("@example.com")
        assert not EMAIL_REGEX.match("user@")

    def test_phone_regex_matches_valid_phones(self):
        """Test PHONE_REGEX matches valid phone numbers."""
        assert PHONE_REGEX.match("555-123-4567")
        assert PHONE_REGEX.match("(555) 123-4567")
        assert PHONE_REGEX.match("555.123.4567")
        assert PHONE_REGEX.match("5551234567")

    def test_phone_regex_rejects_invalid_phones(self):
        """Test PHONE_REGEX rejects invalid phone numbers."""
        assert not PHONE_REGEX.match("123")
        assert not PHONE_REGEX.match("abc-def-ghij")


class TestValidateRequiredField:
    """Tests for validate_required_field function."""

    def test_valid_string_value(self):
        """Test validation passes for valid string value."""
        result = validate_required_field("Company Name", "Company", 0)
        assert result is None

    def test_missing_none_value(self):
        """Test validation fails for None value."""
        result = validate_required_field(None, "Company", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR
        assert "missing" in result.message.lower()

    def test_missing_empty_string(self):
        """Test validation fails for empty string."""
        result = validate_required_field("   ", "Company", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR

    def test_missing_pandas_na(self):
        """Test validation fails for pandas NA."""
        result = validate_required_field(pd.NA, "Company", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidatePhase:
    """Tests for validate_phase function."""

    def test_valid_phase_i(self):
        """Test validation passes for Phase I."""
        result = validate_phase("Phase I", 0)
        assert result is None

    def test_valid_phase_ii(self):
        """Test validation passes for Phase II."""
        result = validate_phase("Phase II", 0)
        assert result is None

    def test_valid_phase_iii(self):
        """Test validation passes for Phase III."""
        result = validate_phase("Phase III", 0)
        assert result is None

    def test_invalid_phase(self):
        """Test validation fails for invalid phase."""
        result = validate_phase("Phase IV", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR
        assert "Invalid phase" in result.message

    def test_missing_phase(self):
        """Test validation fails for missing phase."""
        result = validate_phase(pd.NA, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateProgram:
    """Tests for validate_program function."""

    def test_valid_sbir_uppercase(self):
        """Test validation passes for SBIR uppercase."""
        result = validate_program("SBIR", 0)
        assert result is None

    def test_valid_sbir_lowercase(self):
        """Test validation passes for SBIR lowercase."""
        result = validate_program("sbir", 0)
        assert result is None

    def test_valid_sttr_uppercase(self):
        """Test validation passes for STTR uppercase."""
        result = validate_program("STTR", 0)
        assert result is None

    def test_invalid_program(self):
        """Test validation fails for invalid program."""
        result = validate_program("INVALID", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR
        assert "Invalid program" in result.message

    def test_missing_program(self):
        """Test validation fails for missing program."""
        result = validate_program(pd.NA, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateAwardYear:
    """Tests for validate_award_year function."""

    def test_valid_year_in_range(self):
        """Test validation passes for year in valid range."""
        result = validate_award_year(2020, 0)
        assert result is None

    def test_valid_year_lower_bound(self):
        """Test validation passes for year at lower bound (1983)."""
        result = validate_award_year(1983, 0)
        assert result is None

    def test_valid_year_upper_bound(self):
        """Test validation passes for year at upper bound (2026)."""
        result = validate_award_year(2026, 0)
        assert result is None

    def test_invalid_year_too_early(self):
        """Test validation fails for year before 1983."""
        result = validate_award_year(1982, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR
        assert "out of valid range" in result.message

    def test_invalid_year_too_late(self):
        """Test validation fails for year after 2026."""
        result = validate_award_year(2027, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR

    def test_missing_year(self):
        """Test validation fails for missing year."""
        result = validate_award_year(pd.NA, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateAwardAmount:
    """Tests for validate_award_amount function."""

    def test_valid_numeric_amount(self):
        """Test validation passes for valid numeric amount."""
        result = validate_award_amount(100000.0, 0)
        assert result is None

    def test_valid_string_amount_with_commas(self):
        """Test validation passes for string amount with commas."""
        result = validate_award_amount("1,000,000.00", 0)
        assert result is None

    def test_zero_amount(self):
        """Test validation fails for zero amount."""
        result = validate_award_amount(0, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR
        assert "must be positive" in result.message

    def test_negative_amount(self):
        """Test validation fails for negative amount."""
        result = validate_award_amount(-1000, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR
        assert "must be positive" in result.message

    def test_excessive_amount_warning(self):
        """Test validation warns for amount over $10M."""
        result = validate_award_amount(15000000, 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING
        assert "exceeds typical maximum" in result.message

    def test_non_numeric_string(self):
        """Test validation fails for non-numeric string."""
        result = validate_award_amount("not a number", 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR
        assert "must be numeric" in result.message

    def test_missing_amount(self):
        """Test validation fails for missing amount."""
        result = validate_award_amount(pd.NA, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateUEIFormat:
    """Tests for validate_uei_format function."""

    def test_valid_uei(self):
        """Test validation passes for valid 12-character UEI."""
        result = validate_uei_format("ABC123DEF456", 0)
        assert result is None

    def test_missing_uei(self):
        """Test validation passes for missing UEI (optional field)."""
        result = validate_uei_format(pd.NA, 0)
        assert result is None

    def test_invalid_uei_wrong_length(self):
        """Test validation warns for UEI with wrong length."""
        result = validate_uei_format("ABC123", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING
        assert "should be 12 characters" in result.message

    def test_invalid_uei_non_alphanumeric(self):
        """Test validation warns for UEI with special characters."""
        result = validate_uei_format("ABC-123-DEF!", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING
        assert "should be alphanumeric" in result.message


class TestValidateDUNSFormat:
    """Tests for validate_duns_format function."""

    def test_valid_duns(self):
        """Test validation passes for valid 9-digit DUNS."""
        result = validate_duns_format("123456789", 0)
        assert result is None

    def test_missing_duns(self):
        """Test validation passes for missing DUNS (optional field)."""
        result = validate_duns_format(pd.NA, 0)
        assert result is None

    def test_invalid_duns_wrong_length(self):
        """Test validation warns for DUNS with wrong length."""
        result = validate_duns_format("12345", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_invalid_duns_non_digits(self):
        """Test validation warns for DUNS with non-digits."""
        result = validate_duns_format("ABC123DEF", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidateEmailFormat:
    """Tests for validate_email_format function."""

    def test_valid_email(self):
        """Test validation passes for valid email."""
        result = validate_email_format("user@example.com", "Email", 0)
        assert result is None

    def test_missing_email(self):
        """Test validation passes for missing email (optional field)."""
        result = validate_email_format(pd.NA, "Email", 0)
        assert result is None

    def test_invalid_email_no_at(self):
        """Test validation warns for email without @ symbol."""
        result = validate_email_format("invalid.email.com", "Email", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_invalid_email_no_domain(self):
        """Test validation warns for email without domain."""
        result = validate_email_format("user@", "Email", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidateStateCode:
    """Tests for validate_state_code function."""

    def test_valid_state_code(self):
        """Test validation passes for valid state code."""
        result = validate_state_code("CA", 0)
        assert result is None

    def test_missing_state(self):
        """Test validation passes for missing state (optional field)."""
        result = validate_state_code(pd.NA, 0)
        assert result is None

    def test_invalid_state_wrong_length(self):
        """Test validation warns for state code with wrong length."""
        result = validate_state_code("CAL", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_invalid_state_not_in_list(self):
        """Test validation warns for invalid state code."""
        result = validate_state_code("XX", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidateZIPCode:
    """Tests for validate_zip_code function."""

    def test_valid_5_digit_zip(self):
        """Test validation passes for valid 5-digit ZIP."""
        result = validate_zip_code("02101", 0)
        assert result is None

    def test_valid_9_digit_zip(self):
        """Test validation passes for valid 9-digit ZIP."""
        result = validate_zip_code("02101-1234", 0)
        assert result is None

    def test_missing_zip(self):
        """Test validation passes for missing ZIP (optional field)."""
        result = validate_zip_code(pd.NA, 0)
        assert result is None

    def test_invalid_zip_wrong_length(self):
        """Test validation warns for ZIP with wrong length."""
        result = validate_zip_code("123", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING

    def test_invalid_zip_non_digits(self):
        """Test validation warns for ZIP with non-digits."""
        result = validate_zip_code("ABCDE", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidatePhoneFormat:
    """Tests for validate_phone_format function."""

    def test_valid_phone_hyphenated(self):
        """Test validation passes for valid hyphenated phone."""
        result = validate_phone_format("555-123-4567", "Phone", 0)
        assert result is None

    def test_valid_phone_parentheses(self):
        """Test validation passes for valid phone with parentheses."""
        result = validate_phone_format("(555) 123-4567", "Phone", 0)
        assert result is None

    def test_missing_phone(self):
        """Test validation passes for missing phone (optional field)."""
        result = validate_phone_format(pd.NA, "Phone", 0)
        assert result is None

    def test_invalid_phone(self):
        """Test validation warns for invalid phone format."""
        result = validate_phone_format("123", "Phone", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidateAwardYearDateConsistency:
    """Tests for validate_award_year_date_consistency function."""

    def test_consistent_year_and_date(self):
        """Test validation passes when year matches date."""
        result = validate_award_year_date_consistency(2020, date(2020, 6, 15), 0)
        assert result is None

    def test_missing_year(self):
        """Test validation passes when year is missing."""
        result = validate_award_year_date_consistency(pd.NA, date(2020, 6, 15), 0)
        assert result is None

    def test_missing_date(self):
        """Test validation passes when date is missing."""
        result = validate_award_year_date_consistency(2020, pd.NA, 0)
        assert result is None

    def test_inconsistent_year_and_date(self):
        """Test validation warns when year doesn't match date."""
        result = validate_award_year_date_consistency(2019, date(2020, 6, 15), 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidatePhaseProgramConsistency:
    """Tests for validate_phase_program_consistency function."""

    def test_valid_sbir_phase_i(self):
        """Test validation passes for SBIR Phase I."""
        result = validate_phase_program_consistency("Phase I", "SBIR", 0)
        assert result is None

    def test_valid_sttr_phase_ii(self):
        """Test validation passes for STTR Phase II."""
        result = validate_phase_program_consistency("Phase II", "STTR", 0)
        assert result is None

    def test_missing_phase(self):
        """Test validation passes when phase is missing."""
        result = validate_phase_program_consistency(pd.NA, "SBIR", 0)
        assert result is None

    def test_missing_program(self):
        """Test validation passes when program is missing."""
        result = validate_phase_program_consistency("Phase I", pd.NA, 0)
        assert result is None


class TestValidateDateConsistency:
    """Tests for validate_date_consistency function."""

    def test_valid_date_order(self):
        """Test validation passes when end date is after award date."""
        result = validate_date_consistency(date(2020, 1, 1), date(2021, 1, 1), 0)
        assert result is None

    def test_missing_award_date(self):
        """Test validation passes when award date is missing."""
        result = validate_date_consistency(None, date(2021, 1, 1), 0)
        assert result is None

    def test_missing_end_date(self):
        """Test validation passes when end date is missing."""
        result = validate_date_consistency(date(2020, 1, 1), None, 0)
        assert result is None

    def test_invalid_date_order(self):
        """Test validation warns when end date is before award date."""
        result = validate_date_consistency(date(2021, 1, 1), date(2020, 1, 1), 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidateSBIRAwardRecord:
    """Tests for validate_sbir_award_record function."""

    def test_valid_complete_record(self):
        """Test validation passes for valid complete record."""
        row = pd.Series({
            "Company": "Acme Corp",
            "Award Title": "AI Research",
            "Agency": "DOD",
            "Phase": "Phase I",
            "Program": "SBIR",
            "Award Year": 2020,
            "Award Amount": 150000,
            "UEI": "ABC123DEF456",
            "Duns": "123456789",
            "Contact Email": "contact@acme.com",
            "PI Email": "pi@acme.com",
            "State": "CA",
            "Zip": "94105",
            "Contact Phone": "555-123-4567",
            "PI Phone": "555-987-6543",
            "Proposal Award Date": date(2020, 6, 15),
            "Contract End Date": date(2021, 6, 14),
        })
        issues = validate_sbir_award_record(row, 0)
        assert len(issues) == 0

    def test_missing_required_fields(self):
        """Test validation fails for missing required fields."""
        row = pd.Series({
            "Company": pd.NA,  # Missing
            "Award Title": "",  # Missing
            "Agency": "DOD",
            "Phase": "Phase I",
            "Program": "SBIR",
            "Award Year": 2020,
            "Award Amount": 150000,
        })
        issues = validate_sbir_award_record(row, 0)
        # Should have errors for missing Company and Award Title
        assert len(issues) >= 2
        assert any(i.field == "Company" for i in issues)
        assert any(i.field == "Award Title" for i in issues)

    def test_invalid_formats(self):
        """Test validation warns for invalid formats."""
        row = pd.Series({
            "Company": "Acme Corp",
            "Award Title": "Test",
            "Agency": "DOD",
            "Phase": "Phase I",
            "Program": "SBIR",
            "Award Year": 2020,
            "Award Amount": 150000,
            "UEI": "SHORT",  # Invalid: too short
            "Duns": "12345",  # Invalid: wrong length
            "Contact Email": "invalid-email",  # Invalid format
            "State": "CAL",  # Invalid: 3 letters
            "Zip": "123",  # Invalid: too short
        })
        issues = validate_sbir_award_record(row, 0)
        assert len(issues) >= 5  # All format validations should fail


class TestValidateSBIRAwards:
    """Tests for validate_sbir_awards function."""

    def test_empty_dataframe(self):
        """Test validation passes for empty DataFrame."""
        df = pd.DataFrame()
        report = validate_sbir_awards(df)
        assert report.passed is True
        assert report.total_records == 0

    def test_all_valid_records(self):
        """Test validation passes when all records are valid."""
        df = pd.DataFrame([
            {
                "Company": "Acme Corp",
                "Award Title": "AI Research",
                "Agency": "DOD",
                "Phase": "Phase I",
                "Program": "SBIR",
                "Award Year": 2020,
                "Award Amount": 150000,
            },
            {
                "Company": "Tech Inc",
                "Award Title": "Quantum Computing",
                "Agency": "NSF",
                "Phase": "Phase II",
                "Program": "STTR",
                "Award Year": 2021,
                "Award Amount": 750000,
            },
        ])
        report = validate_sbir_awards(df)
        assert report.total_records == 2
        assert report.passed_records == 2
        assert report.failed_records == 0
        assert report.passed is True

    def test_some_invalid_records(self):
        """Test validation fails when some records are invalid."""
        df = pd.DataFrame([
            {
                "Company": "Acme Corp",
                "Award Title": "Valid Record",
                "Agency": "DOD",
                "Phase": "Phase I",
                "Program": "SBIR",
                "Award Year": 2020,
                "Award Amount": 150000,
            },
            {
                "Company": pd.NA,  # Missing required field
                "Award Title": "Invalid Record",
                "Agency": "NSF",
                "Phase": "Phase IV",  # Invalid phase
                "Program": "INVALID",  # Invalid program
                "Award Year": 1900,  # Invalid year
                "Award Amount": -1000,  # Invalid amount
            },
        ])
        report = validate_sbir_awards(df)
        assert report.total_records == 2
        assert report.failed_records >= 1
        assert len(report.issues) >= 5  # Multiple errors in second record

    def test_pass_rate_threshold(self):
        """Test validation respects pass rate threshold."""
        df = pd.DataFrame([
            {
                "Company": "Valid Corp",
                "Award Title": "Valid",
                "Agency": "DOD",
                "Phase": "Phase I",
                "Program": "SBIR",
                "Award Year": 2020,
                "Award Amount": 150000,
            },
            {
                "Company": pd.NA,  # Invalid
                "Award Title": "",
                "Agency": "",
                "Phase": "Phase IV",
                "Program": "INVALID",
                "Award Year": 1900,
                "Award Amount": -1000,
            },
        ])
        # 50% pass rate with 95% threshold should fail
        report = validate_sbir_awards(df, pass_rate_threshold=0.95)
        assert report.passed is False

        # 50% pass rate with 40% threshold should pass
        report = validate_sbir_awards(df, pass_rate_threshold=0.40)
        assert report.passed is True
