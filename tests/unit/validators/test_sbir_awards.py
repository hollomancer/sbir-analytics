"""Tests for SBIR award validation rules."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

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


pytestmark = pytest.mark.fast


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

    @pytest.mark.parametrize(
        "phase",
        ["Phase I", "Phase II", "Phase III"],
        ids=["phase_i", "phase_ii", "phase_iii"],
    )
    def test_valid_phase_values(self, phase):
        """Test validation passes for valid phase values (exact case)."""
        result = validate_phase(phase, 0)
        assert result is None

    @pytest.mark.parametrize(
        "invalid_phase",
        ["Phase IV", "I", "phase i", "PHASE II", "Invalid", "", pd.NA],
        ids=["phase_iv", "roman_only", "lowercase", "uppercase", "invalid_text", "empty", "na"],
    )
    def test_invalid_phase_values(self, invalid_phase):
        """Test validation fails for invalid or incorrectly cased phase values."""
        result = validate_phase(invalid_phase, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateProgram:
    """Tests for validate_program function."""

    @pytest.mark.parametrize(
        "program",
        ["SBIR", "sbir", "STTR", "sttr", "Sbir", "Sttr"],
        ids=["sbir_upper", "sbir_lower", "sttr_upper", "sttr_lower", "sbir_mixed", "sttr_mixed"],
    )
    def test_valid_program_values(self, program):
        """Test validation passes for valid program values (case-insensitive)."""
        result = validate_program(program, 0)
        assert result is None

    @pytest.mark.parametrize(
        "invalid_program",
        ["INVALID", "OTHER", "", pd.NA],
        ids=["invalid", "other", "empty", "na"],
    )
    def test_invalid_program_values(self, invalid_program):
        """Test validation fails for invalid program values."""
        result = validate_program(invalid_program, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateAwardYear:
    """Tests for validate_award_year function."""

    @pytest.mark.parametrize(
        "year",
        [1983, 2000, 2020, 2026],
        ids=["lower_bound", "mid_range", "recent", "upper_bound"],
    )
    def test_valid_year_in_range(self, year):
        """Test validation passes for years in valid range (1983-2026)."""
        result = validate_award_year(year, 0)
        assert result is None

    @pytest.mark.parametrize(
        "invalid_year",
        [1982, 1900, 2027, 2050, pd.NA],
        ids=["before_1983", "way_before", "after_2026", "way_after", "missing"],
    )
    def test_invalid_year_values(self, invalid_year):
        """Test validation fails for years outside valid range or missing."""
        result = validate_award_year(invalid_year, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR
        result = validate_award_year(pd.NA, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR


class TestValidateAwardAmount:
    """Tests for validate_award_amount function."""

    @pytest.mark.parametrize(
        "amount",
        [100000.0, 1, 5000000, "1,000,000.00", "500000"],
        ids=["float", "small_int", "large", "string_commas", "string_plain"],
    )
    def test_valid_amount_values(self, amount):
        """Test validation passes for valid positive amounts."""
        result = validate_award_amount(amount, 0)
        assert result is None

    @pytest.mark.parametrize(
        "invalid_amount",
        [0, -1000, "not a number", pd.NA],
        ids=["zero", "negative", "non_numeric", "missing"],
    )
    def test_invalid_amount_values(self, invalid_amount):
        """Test validation fails for invalid amounts."""
        result = validate_award_amount(invalid_amount, 0)
        assert result is not None
        assert result.severity == QualitySeverity.ERROR

    def test_excessive_amount_warning(self):
        """Test validation warns for amount over $10M."""
        result = validate_award_amount(15000000, 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING
        assert "exceeds typical maximum" in result.message


class TestValidateUEIFormat:
    """Tests for validate_uei_format function."""

    @pytest.mark.parametrize(
        "uei",
        ["ABC123DEF456", "ABCDEFGHIJKL", pd.NA, None],
        ids=["valid_12char", "all_alpha", "na_optional", "none_optional"],
    )
    def test_valid_or_optional_uei(self, uei):
        """Test validation passes for valid UEI or optional missing value."""
        result = validate_uei_format(uei, 0)
        assert result is None

    @pytest.mark.parametrize(
        "invalid_uei",
        ["ABC123", "ABC-123-DEF!", "TOOLONGVALUE123"],
        ids=["too_short", "special_chars", "too_long"],
    )
    def test_invalid_uei_format(self, invalid_uei):
        """Test validation warns for invalid UEI format."""
        result = validate_uei_format(invalid_uei, 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidateDUNSFormat:
    """Tests for validate_duns_format function."""

    @pytest.mark.parametrize(
        "duns",
        ["123456789", "000000000", pd.NA, None],
        ids=["valid_9digit", "all_zeros", "na_optional", "none_optional"],
    )
    def test_valid_or_optional_duns(self, duns):
        """Test validation passes for valid DUNS or optional missing value."""
        result = validate_duns_format(duns, 0)
        assert result is None

    @pytest.mark.parametrize(
        "invalid_duns",
        ["12345", "ABC123DEF", "1234567890"],
        ids=["too_short", "non_digits", "too_long"],
    )
    def test_invalid_duns_format(self, invalid_duns):
        """Test validation warns for invalid DUNS format."""
        result = validate_duns_format(invalid_duns, 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidateEmailFormat:
    """Tests for validate_email_format function."""

    @pytest.mark.parametrize(
        "email",
        ["user@example.com", "test.user@domain.org", pd.NA, None],
        ids=["simple", "with_dot", "na_optional", "none_optional"],
    )
    def test_valid_or_optional_email(self, email):
        """Test validation passes for valid email or optional missing value."""
        result = validate_email_format(email, "Email", 0)
        assert result is None

    @pytest.mark.parametrize(
        "invalid_email",
        ["invalid.email.com", "user@", "@domain.com"],
        ids=["no_at", "no_domain", "no_user"],
    )
    def test_invalid_email_format(self, invalid_email):
        """Test validation warns for invalid email format."""
        result = validate_email_format(invalid_email, "Email", 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidateStateCode:
    """Tests for validate_state_code function."""

    @pytest.mark.parametrize(
        "state",
        ["CA", "NY", "TX", "DC", "PR", pd.NA, None],
        ids=[
            "california",
            "new_york",
            "texas",
            "dc",
            "puerto_rico",
            "na_optional",
            "none_optional",
        ],
    )
    def test_valid_or_optional_state(self, state):
        """Test validation passes for valid state code or optional missing value."""
        result = validate_state_code(state, 0)
        assert result is None

    @pytest.mark.parametrize(
        "invalid_state",
        ["CAL", "XX", "ZZ", "1A"],
        ids=["too_long", "invalid_xx", "invalid_zz", "has_digit"],
    )
    def test_invalid_state_code(self, invalid_state):
        """Test validation warns for invalid state code."""
        result = validate_state_code(invalid_state, 0)
        assert result is not None
        assert result.severity == QualitySeverity.WARNING


class TestValidateZIPCode:
    """Tests for validate_zip_code function."""

    @pytest.mark.parametrize(
        "zip_code",
        ["02101", "90210", "02101-1234", "123456789", pd.NA, None],
        ids=[
            "5digit",
            "5digit_alt",
            "9digit_hyphen",
            "9digit_plain",
            "na_optional",
            "none_optional",
        ],
    )
    def test_valid_or_optional_zip(self, zip_code):
        """Test validation passes for valid ZIP code or optional missing value."""
        result = validate_zip_code(zip_code, 0)
        assert result is None

    @pytest.mark.parametrize(
        "invalid_zip",
        ["123", "ABCDE", "12-34"],
        ids=["too_short", "non_digits", "invalid_format"],
    )
    def test_invalid_zip_code(self, invalid_zip):
        """Test validation warns for invalid ZIP code format."""
        result = validate_zip_code(invalid_zip, 0)
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
        row = pd.Series(
            {
                "Company": "Acme Corp",
                "Award Title": "AI Research",
                "Agency": "DOD",
                "Phase": "Phase I",
                "Program": "SBIR",
                "Award Year": 2020,
                "Award Amount": 150000,
                "UEI": "ABC123DEF456",  # pragma: allowlist secret
                "Duns": "123456789",
                "Contact Email": "contact@acme.com",
                "PI Email": "pi@acme.com",
                "State": "CA",
                "Zip": "94105",
                "Contact Phone": "555-123-4567",
                "PI Phone": "555-987-6543",
                "Proposal Award Date": date(2020, 6, 15),
                "Contract End Date": date(2021, 6, 14),
            }
        )
        issues = validate_sbir_award_record(row, 0)
        assert len(issues) == 0

    def test_missing_required_fields(self):
        """Test validation fails for missing required fields."""
        row = pd.Series(
            {
                "Company": pd.NA,  # Missing
                "Award Title": "",  # Missing
                "Agency": "DOD",
                "Phase": "Phase I",
                "Program": "SBIR",
                "Award Year": 2020,
                "Award Amount": 150000,
            }
        )
        issues = validate_sbir_award_record(row, 0)
        # Should have errors for missing Company and Award Title
        assert len(issues) >= 2
        assert any(i.field == "Company" for i in issues)
        assert any(i.field == "Award Title" for i in issues)

    def test_invalid_formats(self):
        """Test validation warns for invalid formats."""
        row = pd.Series(
            {
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
            }
        )
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
        df = pd.DataFrame(
            [
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
            ]
        )
        report = validate_sbir_awards(df)
        assert report.total_records == 2
        assert report.passed_records == 2
        assert report.failed_records == 0
        assert report.passed is True

    def test_some_invalid_records(self):
        """Test validation fails when some records are invalid."""
        df = pd.DataFrame(
            [
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
            ]
        )
        report = validate_sbir_awards(df)
        assert report.total_records == 2
        assert report.failed_records >= 1
        assert len(report.issues) >= 5  # Multiple errors in second record

    def test_pass_rate_threshold(self):
        """Test validation respects pass rate threshold."""
        df = pd.DataFrame(
            [
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
            ]
        )
        # 50% pass rate with 95% threshold should fail
        report = validate_sbir_awards(df, pass_rate_threshold=0.95)
        assert report.passed is False

        # 50% pass rate with 40% threshold should pass
        report = validate_sbir_awards(df, pass_rate_threshold=0.40)
        assert report.passed is True
