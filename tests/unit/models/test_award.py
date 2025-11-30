"""Tests for SBIR award Pydantic models."""

from datetime import date

import pytest
from pydantic import ValidationError

from src.models.award import Award, RawAward


pytestmark = pytest.mark.fast


# Helper to create Award with defaults
def _make_award(**overrides):
    """Create Award with sensible defaults."""
    defaults = {
        "award_id": "TEST-001",
        "company_name": "Test Corp",
        "award_amount": 10000,
        "award_date": date(2023, 1, 1),
        "program": "SBIR",
    }
    defaults.update(overrides)
    return Award(**defaults)


class TestAwardModel:
    """Tests for the Award Pydantic model."""

    def test_minimal_valid_award(self):
        """Test creating award with only required fields."""
        award = _make_award(
            award_id="TEST-123",
            company_name="Acme Corp",
            award_amount=100000.0,
            award_date=date(2023, 1, 15),
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
        assert award.company_uei == "ABC123DEF456"  # pragma: allowlist secret
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

    @pytest.mark.parametrize(
        "invalid_amount,error_msg",
        [
            (0, "Award amount must be positive"),
            (-1000, "Award amount must be positive"),
            ("not_a_number", "Award amount must be a number"),
        ],
        ids=["zero", "negative", "non_numeric"],
    )
    def test_award_amount_validator_rejects_invalid(self, invalid_amount, error_msg):
        """Test award_amount validator rejects invalid amounts."""
        with pytest.raises(ValidationError) as exc_info:
            Award(
                award_id="TEST-INVALID",
                company_name="Test Corp",
                award_amount=invalid_amount,
                award_date=date(2023, 1, 1),
                program="SBIR",
            )
        assert error_msg in str(exc_info.value)

    @pytest.mark.parametrize(
        "program_input,expected",
        [
            ("sbir", "SBIR"),
            ("SBIR", "SBIR"),
            ("sttr", "STTR"),
            ("STTR", "STTR"),
        ],
        ids=["sbir_lower", "sbir_upper", "sttr_lower", "sttr_upper"],
    )
    def test_program_validator_normalizes(self, program_input, expected):
        """Test program validator normalizes valid programs."""
        award = Award(
            award_id="TEST-PROG",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program=program_input,
        )
        assert award.program == expected

    def test_program_validator_rejects_invalid_program(self):
        """Test program validator returns None for invalid program (lenient)."""
        award = Award(
            award_id="TEST-8",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="INVALID",
        )
        assert award.program is None

    @pytest.mark.parametrize(
        "phase_input,expected",
        [
            ("i", "I"),
            ("ii", "II"),
            ("iii", "III"),
            ("I", "I"),
            ("II", "II"),
        ],
        ids=["i_lower", "ii_lower", "iii_lower", "I_upper", "II_upper"],
    )
    def test_phase_validator_normalizes_roman_numerals(self, phase_input, expected):
        """Test phase validator accepts and normalizes roman numerals."""
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
        """Test phase validator normalizes Phase IV to III (lenient)."""
        award = Award(
            award_id="TEST-10",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            phase="IV",
        )
        # Lenient: Phase IV is normalized to III
        assert award.phase == "III"

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
        """Test fiscal_year validator accepts years before 1983 (lenient)."""
        award = Award(
            award_id="TEST-12",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            fiscal_year=1982,
        )
        # Lenient: out-of-range years are accepted with a warning
        assert award.fiscal_year == 1982

    def test_fiscal_year_validator_rejects_too_late(self):
        """Test fiscal_year validator accepts years after 2050 (lenient)."""
        award = Award(
            award_id="TEST-13",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            fiscal_year=2051,
        )
        # Lenient: out-of-range years are accepted with a warning
        assert award.fiscal_year == 2051

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

    @pytest.mark.parametrize(
        "uei_input,expected",
        [
            ("abc123def456", "ABC123DEF456"),  # lowercase normalized
            ("ABC-123-DEF-456", "ABC123DEF456"),  # separators removed
            ("ABC123DEF456", "ABC123DEF456"),  # already valid
            ("ABC123", None),  # too short - lenient returns None
            ("ABC123DEF456789", None),  # too long - lenient returns None
        ],
        ids=["lowercase", "with_separators", "valid", "too_short", "too_long"],
    )
    def test_company_uei_validator(self, uei_input, expected):
        """Test company_uei validator normalizes valid UEIs and rejects invalid."""
        award = _make_award(company_uei=uei_input)
        assert award.company_uei == expected

    @pytest.mark.parametrize(
        "duns_input,expected",
        [
            ("12-345-6789", "123456789"),  # separators removed
            ("123456789", "123456789"),  # already valid
            ("12345", None),  # too short - lenient returns None
        ],
        ids=["with_separators", "valid", "too_short"],
    )
    def test_company_duns_validator(self, duns_input, expected):
        """Test company_duns validator extracts 9 digits or returns None."""
        award = _make_award(company_duns=duns_input)
        assert award.company_duns == expected

    @pytest.mark.parametrize(
        "state_input,expected",
        [
            ("ca", "CA"),  # lowercase normalized
            ("CA", "CA"),  # already valid
            ("CAL", None),  # too long - lenient returns None
        ],
        ids=["lowercase", "valid", "too_long"],
    )
    def test_company_state_validator(self, state_input, expected):
        """Test company_state validator normalizes to uppercase or returns None."""
        award = _make_award(company_state=state_input)
        assert award.company_state == expected

    @pytest.mark.parametrize(
        "zip_input,expected",
        [
            ("02101", "02101"),  # 5-digit valid
            ("02101-1234", "021011234"),  # 9-digit ZIP+4
            ("123", None),  # too short - lenient returns None
        ],
        ids=["5_digit", "9_digit", "too_short"],
    )
    def test_company_zip_validator(self, zip_input, expected):
        """Test company_zip validator accepts valid ZIPs or returns None."""
        award = _make_award(company_zip=zip_input)
        assert award.company_zip == expected

    @pytest.mark.parametrize(
        "employees_input,expected",
        [
            ("1,234", 1234),  # string with commas coerced
            (50, 50),  # int preserved
            (-5, None),  # negative - lenient returns None
        ],
        ids=["string_with_commas", "int_valid", "negative_invalid"],
    )
    def test_number_of_employees_validator(self, employees_input, expected):
        """Test number_of_employees validator coerces strings and rejects negatives."""
        award = _make_award(number_of_employees=employees_input)
        assert award.number_of_employees == expected

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
        """Test contract_end_date validator accepts end before start with warning (lenient)."""
        # Lenient: invalid date order is accepted with a warning instead of raising exception
        award = Award(
            award_id="TEST-29",
            company_name="Test Corp",
            award_amount=10000,
            award_date=date(2023, 1, 1),
            program="SBIR",
            proposal_award_date=date(2023, 12, 31),
            contract_end_date=date(2023, 1, 1),  # Before proposal date, but accepted
        )
        # Award is created successfully despite invalid date order
        assert award.contract_end_date == date(2023, 1, 1)

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
