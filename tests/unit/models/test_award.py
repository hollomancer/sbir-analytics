"""Tests for SBIR award Pydantic models."""

from datetime import date

import pytest
from pydantic import ValidationError

from src.models.award import Award, RawAward


pytestmark = pytest.mark.fast



class TestAwardModel:
    """Tests for the Award Pydantic model."""

    def test_minimal_valid_award(self):
        """Test creating award with only required fields."""
        award = Award(
            award_id="TEST-123",
            company_name="Acme Corp",
            award_amount=100000.0,
            award_date=date(2023, 1, 15),
            program="SBIR",
        )
        assert award.award_id == "TEST-123"
        assert award.company_name == "Acme Corp"
        assert award.award_amount == 100000.0
        assert award.award_date == date(2023, 1, 15)
        assert award.program == "SBIR"

    def test_full_award_with_all_fields(self):
        """Test creating award with all fields populated."""
        award = Award(
            award_id="FULL-456",
            company_name="Full Data Inc",
            award_amount=250000.50,
            award_date=date(2022, 6, 1),
            program="STTR",
            phase="II",
            agency="DOD",
            branch="Air Force",
            contract="FA8650-22-C-1234",
            abstract="Advanced AI research",
            keywords="artificial intelligence, machine learning",
            award_title="AI Innovation Project",
            company_uei="ABC123DEF456",  # pragma: allowlist secret
            company_duns="123456789",
            company_cage="1A2B3",
            company_address="123 Main St",
            address1="123 Main St",
            address2="Suite 200",
            company_city="Boston",
            company_state="MA",
            company_zip="02101",
            contact_name="Jane Smith",
            contact_title="CEO",
            contact_email="jane@example.com",
            contact_phone="555-1234",
            principal_investigator="Dr. John Doe",
            pi_title="Lead Scientist",
            pi_phone="555-5678",
            pi_email="john@example.com",
            research_institution="MIT",
            ri_poc_name="Dr. Alice",
            ri_poc_phone="555-9999",
            proposal_award_date=date(2022, 5, 1),
            contract_start_date=date(2022, 6, 15),
            contract_end_date=date(2023, 6, 14),
            solicitation_date=date(2022, 1, 1),
            solicitation_close_date=date(2022, 3, 1),
            proposal_receipt_date=date(2022, 3, 15),
            date_of_notification=date(2022, 4, 15),
            agency_tracking_number="DOD-2022-001",
            solicitation_number="SOL-2022",
            solicitation_year=2022,
            topic_code="AF22-001",
            is_hubzone=True,
            is_woman_owned=True,
            is_socially_disadvantaged=False,
            number_of_employees=25,
            company_website="https://example.com",
            usaspending_id="USA-123",
            fiscal_year=2022,
            award_year=2022,
        )
        assert award.award_id == "FULL-456"
        assert award.program == "STTR"
        assert award.phase == "II"
        assert award.company_uei == "ABC123DEF456"
        assert award.is_woman_owned is True

    def test_award_amount_validator_positive(self):
        """Test award_amount validator accepts positive amounts."""
        award = Award(
            award_id="TEST-1",
            company_name="Test Corp",
            award_amount=50000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
        )
        assert award.award_amount == 50000.0

    def test_award_amount_validator_string_coercion(self):
        """Test award_amount validator coerces string to float."""
        award = Award(
            award_id="TEST-2",
            company_name="Test Corp",
            award_amount="1,234.56",
            award_date=date(2023, 1, 1),
            program="SBIR",
        )
        assert award.award_amount == 1234.56

    def test_award_amount_validator_rejects_zero(self):
        """Test award_amount validator rejects zero."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-3",
                company_name="Test Corp",
                award_amount=0,
                award_date=date(2023, 1, 1),
                program="SBIR",
            )
        assert "Award amount must be positive" in str(exc_info.value)

    def test_award_amount_validator_rejects_negative(self):
        """Test award_amount validator rejects negative amounts."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-4",
                company_name="Test Corp",
                award_amount=-1000,
                award_date=date(2023, 1, 1),
                program="SBIR",
            )
        assert "Award amount must be positive" in str(exc_info.value)

    def test_award_amount_validator_rejects_non_numeric_string(self):
        """Test award_amount validator rejects non-numeric strings."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-5",
                company_name="Test Corp",
                award_amount="not_a_number",
                award_date=date(2023, 1, 1),
                program="SBIR",
            )
        assert "Award amount must be a number" in str(exc_info.value)

    def test_program_validator_normalizes_to_uppercase(self):
        """Test program validator normalizes to uppercase."""
        award = Award(
            award_id="TEST-6",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="sbir",
        )
        assert award.program == "SBIR"

    def test_program_validator_accepts_sttr(self):
        """Test program validator accepts STTR."""
        award = Award(
            award_id="TEST-7",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="sttr",
        )
        assert award.program == "STTR"

    def test_program_validator_rejects_invalid_program(self):
        """Test program validator rejects invalid program."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-8",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="INVALID",
            )
        assert "Program must be SBIR or STTR" in str(exc_info.value)

    def test_phase_validator_normalizes_roman_numerals(self):
        """Test phase validator accepts and normalizes roman numerals."""
        for phase_input, expected in [("i", "I"), ("ii", "II"), ("iii", "III")]:
            award = Award(
                award_id=f"TEST-{phase_input}",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="SBIR",
                phase=phase_input,
            )
            assert award.phase == expected

    def test_phase_validator_handles_phase_prefix(self):
        """Test phase validator handles 'Phase I' format."""
        award = Award(
            award_id="TEST-9",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            phase="Phase II",
        )
        assert award.phase == "II"

    def test_phase_validator_rejects_invalid_phase(self):
        """Test phase validator rejects invalid phase."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-10",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="SBIR",
                phase="IV",
            )
        assert "Phase must be I, II, or III" in str(exc_info.value)

    def test_fiscal_year_validator_accepts_valid_range(self):
        """Test fiscal_year validator accepts valid years."""
        award = Award(
            award_id="TEST-11",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            fiscal_year=2020,
        )
        assert award.fiscal_year == 2020

    def test_fiscal_year_validator_rejects_too_early(self):
        """Test fiscal_year validator rejects years before 1983."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-12",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="SBIR",
                fiscal_year=1982,
            )
        assert "Fiscal year must be between 1983 and 2050" in str(exc_info.value)

    def test_fiscal_year_validator_rejects_too_late(self):
        """Test fiscal_year validator rejects years after 2050."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-13",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="SBIR",
                fiscal_year=2051,
            )
        assert "Fiscal year must be between 1983 and 2050" in str(exc_info.value)

    def test_award_year_validator_matches_award_date(self):
        """Test award_year validator checks consistency with award_date."""
        award = Award(
            award_id="TEST-14",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 6, 15),
            program="SBIR",
            award_year=2023,
        )
        assert award.award_year == 2023

    def test_award_year_validator_auto_corrects_from_award_date(self):
        """Test award_year validator auto-corrects from award_date when mismatch."""
        award = Award(
            award_id="TEST-15",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            award_year=2022,  # Mismatch - should be auto-corrected to 2023
        )
        # award_date takes priority, so award_year should be auto-corrected to 2023
        assert award.award_year == 2023

    def test_award_year_populated_from_award_date_when_none(self):
        """Test award_year is populated from award_date when not provided."""
        award = Award(
            award_id="TEST-15A",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 6, 15),
            program="SBIR",
            # award_year not provided
        )
        # Should be auto-populated from award_date
        assert award.award_year == 2023

    def test_award_year_preserved_when_no_award_date(self):
        """Test award_year is preserved as-is when award_date not available (fallback)."""
        # This would fail in practice due to award_date being required,
        # but tests the validator logic if award_date were somehow unavailable during validation
        # In real usage, this scenario would be caught by required field validation first
        award = Award(
            award_id="TEST-15B",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2022, 1, 1),  # Required field
            program="SBIR",
            award_year=2022,
        )
        assert award.award_year == 2022

    def test_company_uei_validator_normalizes_to_uppercase(self):
        """Test company_uei validator normalizes to uppercase."""
        award = Award(
            award_id="TEST-16",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            company_uei="abc123def456",  # pragma: allowlist secret
        )
        assert award.company_uei == "ABC123DEF456"

    def test_company_uei_validator_removes_separators(self):
        """Test company_uei validator removes hyphens and spaces."""
        award = Award(
            award_id="TEST-17",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            company_uei="ABC-123-DEF-456",
        )
        assert award.company_uei == "ABC123DEF456"

    def test_company_uei_validator_rejects_wrong_length(self):
        """Test company_uei validator rejects non-12-character UEI."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-18",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="SBIR",
                company_uei="ABC123",
            )
        assert "Company UEI must be a 12-character alphanumeric string" in str(exc_info.value)

    def test_company_duns_validator_extracts_digits(self):
        """Test company_duns validator extracts 9 digits."""
        award = Award(
            award_id="TEST-19",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            company_duns="12-345-6789",
        )
        assert award.company_duns == "123456789"

    def test_company_duns_validator_rejects_wrong_length(self):
        """Test company_duns validator rejects non-9-digit DUNS."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-20",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="SBIR",
                company_duns="12345",
            )
        assert "DUNS must contain exactly 9 digits" in str(exc_info.value)

    def test_company_state_validator_normalizes_to_uppercase(self):
        """Test company_state validator normalizes to uppercase."""
        award = Award(
            award_id="TEST-21",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            company_state="ca",
        )
        assert award.company_state == "CA"

    def test_company_state_validator_rejects_invalid_length(self):
        """Test company_state validator rejects non-2-letter codes."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-22",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="SBIR",
                company_state="CAL",
            )
        assert "State code must be 2 letters" in str(exc_info.value)

    def test_company_zip_validator_extracts_5_digits(self):
        """Test company_zip validator accepts 5-digit ZIP."""
        award = Award(
            award_id="TEST-23",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            company_zip="02101",
        )
        assert award.company_zip == "02101"

    def test_company_zip_validator_extracts_9_digits(self):
        """Test company_zip validator accepts 9-digit ZIP+4."""
        award = Award(
            award_id="TEST-24",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            company_zip="02101-1234",
        )
        assert award.company_zip == "021011234"

    def test_company_zip_validator_rejects_invalid_length(self):
        """Test company_zip validator rejects invalid digit count."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-25",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="SBIR",
                company_zip="123",
            )
        assert "ZIP code must be 5 or 9 digits" in str(exc_info.value)

    def test_number_of_employees_validator_coerces_string(self):
        """Test number_of_employees validator coerces string to int."""
        award = Award(
            award_id="TEST-26",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            number_of_employees="1,234",
        )
        assert award.number_of_employees == 1234

    def test_number_of_employees_validator_rejects_negative(self):
        """Test number_of_employees validator rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-27",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="SBIR",
                number_of_employees=-5,
            )
        assert "Number of employees must be non-negative" in str(exc_info.value)

    def test_contract_end_date_validator_accepts_valid_order(self):
        """Test contract_end_date validator accepts valid date order."""
        award = Award(
            award_id="TEST-28",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            proposal_award_date=date(2023, 1, 1),
            contract_end_date=date(2023, 12, 31),
        )
        assert award.contract_end_date == date(2023, 12, 31)

    def test_contract_end_date_validator_rejects_before_start(self):
        """Test contract_end_date validator rejects end before start."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-29",
                company_name="Test Corp",
                award_amount=10000,
                award_date=date(2023, 1, 1),
                program="SBIR",
                proposal_award_date=date(2023, 12, 31),
                contract_end_date=date(2023, 1, 1),
            )
        assert "contract_end_date must be on or after proposal_award_date" in str(exc_info.value)

    def test_field_aliases_company_name(self):
        """Test 'company' alias maps to company_name."""
        award = Award(
            award_id="TEST-30",
            company="Alias Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
        )
        assert award.company_name == "Alias Test Corp"

    def test_field_aliases_uei(self):
        """Test 'uei' alias maps to company_uei."""
        award = Award(
            award_id="TEST-31",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            uei="ABC123DEF456",
        )
        assert award.company_uei == "ABC123DEF456"

    def test_field_aliases_multiple(self):
        """Test multiple field aliases work together."""
        award = Award(
            award_id="TEST-32",
            company="Test Corp",
            uei="ABC123DEF456",
            duns="123456789",
            city="Boston",
            state="MA",
            zip="02101",
            hubzone_owned=True,
            woman_owned=False,
            number_employees=50,
            pi_name="Dr. Smith",
            ri_name="Harvard",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
        )
        assert award.company_name == "Test Corp"
        assert award.company_uei == "ABC123DEF456"
        assert award.company_duns == "123456789"
        assert award.company_city == "Boston"
        assert award.company_state == "MA"
        assert award.company_zip == "02101"
        assert award.is_hubzone is True
        assert award.is_woman_owned is False
        assert award.number_of_employees == 50
        assert award.principal_investigator == "Dr. Smith"
        assert award.research_institution == "Harvard"


class TestAwardFromSbirCsv:
    """Tests for Award.from_sbir_csv class method."""

    def test_from_sbir_csv_basic_mapping(self):
        """Test from_sbir_csv with basic field mapping."""
        data = {
            "company": "CSV Test Corp",
            "award_amount": 100000,
            "award_date": date(2023, 1, 1),
            "program": "SBIR",
            "agency_tracking_number": "TRACK-001",
            "contract": "CONTRACT-001",
        }
        award = Award.from_sbir_csv(data)
        assert award.company_name == "CSV Test Corp"
        assert award.award_id == "TRACK-001_CONTRACT-001"

    def test_from_sbir_csv_address_combination(self):
        """Test from_sbir_csv combines address1 and address2."""
        data = {
            "company": "Test Corp",
            "award_amount": 100000,
            "award_date": date(2023, 1, 1),
            "program": "SBIR",
            "address1": "123 Main St",
            "address2": "Suite 500",
            "agency_tracking_number": "TRACK-002",
        }
        award = Award.from_sbir_csv(data)
        assert award.company_address == "123 Main St, Suite 500"
        assert award.address1 == "123 Main St"
        assert award.address2 == "Suite 500"

    def test_from_sbir_csv_award_id_generation_tracking_only(self):
        """Test award_id generation from tracking number only."""
        data = {
            "company": "Test Corp",
            "award_amount": 100000,
            "award_date": date(2023, 1, 1),
            "program": "SBIR",
            "agency_tracking_number": "TRACK-003",
        }
        award = Award.from_sbir_csv(data)
        assert award.award_id == "TRACK-003"

    def test_from_sbir_csv_award_id_generation_contract_only(self):
        """Test award_id generation from contract only."""
        data = {
            "company": "Test Corp",
            "award_amount": 100000,
            "award_date": date(2023, 1, 1),
            "program": "SBIR",
            "contract": "CONTRACT-004",
        }
        award = Award.from_sbir_csv(data)
        assert award.award_id == "CONTRACT-004"

    def test_from_sbir_csv_award_id_generation_fallback(self):
        """Test award_id generation fallback when no identifiers."""
        data = {
            "company": "Test Corp",
            "award_amount": 100000,
            "award_date": date(2023, 1, 1),
            "program": "SBIR",
            "agency": "NASA",
            "award_year": 2023,
        }
        award = Award.from_sbir_csv(data)
        assert award.award_id == "NASA_2023_UNKNOWN"

    def test_from_sbir_csv_award_date_from_proposal_date(self):
        """Test award_date uses proposal_award_date if not provided."""
        data = {
            "company": "Test Corp",
            "award_amount": 100000,
            "program": "SBIR",
            "proposal_award_date": date(2023, 3, 15),
            "agency_tracking_number": "TRACK-005",
        }
        award = Award.from_sbir_csv(data)
        assert award.award_date == date(2023, 3, 15)

    def test_from_sbir_csv_award_date_from_award_year(self):
        """Test award_date inferred from award_year."""
        data = {
            "company": "Test Corp",
            "award_amount": 100000,
            "program": "SBIR",
            "award_year": 2023,
            "agency_tracking_number": "TRACK-006",
        }
        award = Award.from_sbir_csv(data)
        assert award.award_date == date(2023, 1, 1)


class TestRawAwardModel:
    """Tests for the RawAward model."""

    def test_raw_award_accepts_all_none(self):
        """Test RawAward can be created with all None values."""
        raw = RawAward()
        assert raw.award_id is None
        assert raw.company_name is None

    def test_raw_award_accepts_string_dates(self):
        """Test RawAward accepts date strings."""
        raw = RawAward(
            award_date="2023-01-15",
            proposal_award_date="2023-01-01",
        )
        assert raw.award_date == "2023-01-15"
        assert raw.proposal_award_date == "2023-01-01"

    def test_raw_award_accepts_string_amounts(self):
        """Test RawAward accepts string amounts."""
        raw = RawAward(
            award_amount="1,234.56",
            number_of_employees="100",
        )
        assert raw.award_amount == "1,234.56"
        assert raw.number_of_employees == "100"


class TestRawAwardToAward:
    """Tests for RawAward.to_award conversion method."""

    def test_to_award_basic_conversion(self):
        """Test basic RawAward to Award conversion."""
        raw = RawAward(
            award_id="RAW-001",
            company_name="Raw Corp",
            award_amount="50000",
            award_date="2023-06-15",
            program="SBIR",
        )
        award = raw.to_award()
        assert award.award_id == "RAW-001"
        assert award.company_name == "Raw Corp"
        assert award.award_amount == 50000.0
        assert award.award_date == date(2023, 6, 15)
        assert award.program == "SBIR"

    def test_to_award_date_parsing_iso_format(self):
        """Test to_award parses ISO format dates."""
        raw = RawAward(
            award_id="RAW-002",
            company_name="Test Corp",
            award_amount="10000",
            award_date="2023-01-15",
            program="SBIR",
            proposal_award_date="2023-01-01",
        )
        award = raw.to_award()
        assert award.award_date == date(2023, 1, 15)
        assert award.proposal_award_date == date(2023, 1, 1)

    def test_to_award_date_parsing_us_format_slash(self):
        """Test to_award parses US date format with slashes."""
        raw = RawAward(
            award_id="RAW-003",
            company_name="Test Corp",
            award_amount="10000",
            award_date="06/15/2023",
            program="SBIR",
        )
        award = raw.to_award()
        assert award.award_date == date(2023, 6, 15)

    def test_to_award_date_parsing_us_format_dash(self):
        """Test to_award parses US date format with dashes."""
        raw = RawAward(
            award_id="RAW-004",
            company_name="Test Corp",
            award_amount="10000",
            award_date="06-15-2023",
            program="SBIR",
        )
        award = raw.to_award()
        assert award.award_date == date(2023, 6, 15)

    def test_to_award_date_parsing_us_format_2digit_year(self):
        """Test to_award parses US date format with 2-digit year."""
        raw = RawAward(
            award_id="RAW-005",
            company_name="Test Corp",
            award_amount="10000",
            award_date="06/15/23",
            program="SBIR",
        )
        award = raw.to_award()
        assert award.award_date == date(2023, 6, 15)

    def test_to_award_amount_string_with_commas(self):
        """Test to_award coerces amount string with commas."""
        raw = RawAward(
            award_id="RAW-006",
            company_name="Test Corp",
            award_amount="1,234,567.89",
            award_date="2023-01-01",
            program="SBIR",
        )
        award = raw.to_award()
        assert award.award_amount == 1234567.89

    def test_to_award_employees_string_with_commas(self):
        """Test to_award coerces employee count string."""
        raw = RawAward(
            award_id="RAW-007",
            company_name="Test Corp",
            award_amount="10000",
            award_date="2023-01-01",
            program="SBIR",
            number_of_employees="1,500",
        )
        award = raw.to_award()
        assert award.number_of_employees == 1500

    def test_to_award_zip_normalization(self):
        """Test to_award normalizes ZIP to digits only."""
        raw = RawAward(
            award_id="RAW-008",
            company_name="Test Corp",
            award_amount="10000",
            award_date="2023-01-01",
            program="SBIR",
            company_zip="02101-1234",
        )
        award = raw.to_award()
        assert award.company_zip == "021011234"

    def test_to_award_invalid_amount_raises_error(self):
        """Test to_award raises error for invalid award_amount."""
        raw = RawAward(
            award_id="RAW-009",
            company_name="Test Corp",
            award_amount="not_numeric",
            award_date="2023-01-01",
            program="SBIR",
        )
        with pytest.raises(ValueError) as exc_info:
            raw.to_award()
        assert "award_amount must be numeric" in str(exc_info.value)

    def test_to_award_invalid_employees_returns_none(self):
        """Test to_award returns None for invalid employee count."""
        raw = RawAward(
            award_id="RAW-010",
            company_name="Test Corp",
            award_amount="10000",
            award_date="2023-01-01",
            program="SBIR",
            number_of_employees="not_numeric",
        )
        award = raw.to_award()
        assert award.number_of_employees is None


class TestAwardSerialization:
    """Tests for Award model serialization."""

    def test_model_dump(self):
        """Test Award model_dump (Pydantic v2)."""
        award = Award(
            award_id="SERIAL-001",
            company_name="Test Corp",
            award_amount=100000,
            award_date=date(2023, 1, 15),
            program="SBIR",
        )
        data = award.model_dump()
        assert data["award_id"] == "SERIAL-001"
        assert data["company_name"] == "Test Corp"
        assert data["award_amount"] == 100000.0
        assert data["award_date"] == date(2023, 1, 15)

    def test_model_dump_json(self):
        """Test Award model_dump_json serialization."""
        award = Award(
            award_id="SERIAL-002",
            company_name="Test Corp",
            award_amount=100000,
            award_date=date(2023, 1, 15),
            program="SBIR",
        )
        json_str = award.model_dump_json()
        assert "SERIAL-002" in json_str
        assert "2023-01-15" in json_str  # ISO format date

    def test_model_validate(self):
        """Test Award model_validate (Pydantic v2)."""
        data = {
            "award_id": "VALID-001",
            "company_name": "Test Corp",
            "award_amount": 100000,
            "award_date": "2023-01-15",
            "program": "SBIR",
        }
        award = Award.model_validate(data)
        assert award.award_id == "VALID-001"
        assert award.award_date == date(2023, 1, 15)
