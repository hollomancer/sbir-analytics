"""Tests for miscellaneous model files (transitions, ma_models, researcher, company)."""

from datetime import date

import pytest
from pydantic import ValidationError

from src.models.company import Company, CompanyMatch, RawCompany
from src.models.ma_models import MAEvent
from src.models.researcher import RawResearcher, Researcher
from src.models.transitions import CompanyTransition, TransitionType


pytestmark = pytest.mark.fast


class TestTransitionModels:
    """Tests for transitions.py models."""

    def test_transition_type_enum_values(self):
        """Test TransitionType enum has correct values."""
        assert TransitionType.MERGER.value == "merger"
        assert TransitionType.ACQUISITION.value == "acquisition"
        assert TransitionType.BANKRUPTCY.value == "bankruptcy"
        assert TransitionType.SPIN_OFF.value == "spin_off"
        assert TransitionType.IPO.value == "ipo"

    def test_company_transition_valid(self):
        """Test creating a valid company transition."""
        transition = CompanyTransition(
            company_id=123,
            transition_type=TransitionType.ACQUISITION,
            date="2023-06-15",
            confidence=0.95,
            source="sec_filings",
        )
        assert transition.company_id == 123
        assert transition.transition_type == TransitionType.ACQUISITION
        assert transition.date == "2023-06-15"
        assert transition.confidence == 0.95
        assert transition.source == "sec_filings"

    def test_company_transition_merger(self):
        """Test company transition with merger type."""
        transition = CompanyTransition(
            company_id=456,
            transition_type=TransitionType.MERGER,
            date="2024-01-01",
            confidence=0.88,
            source="news_article",
        )
        assert transition.transition_type == TransitionType.MERGER

    def test_company_transition_all_types(self):
        """Test company transition accepts all transition types."""
        for trans_type in TransitionType:
            transition = CompanyTransition(
                company_id=1,
                transition_type=trans_type,
                date="2023-01-01",
                confidence=0.8,
                source="test",
            )
            assert transition.transition_type == trans_type


class TestMAEventModel:
    """Tests for MAEvent model."""

    def test_valid_ma_event(self):
        """Test creating a valid M&A event."""
        event = MAEvent(
            acquiring_company_name="Big Corp",
            acquired_company_name="Small Startup",
            acquisition_date=date(2023, 6, 15),
            source="sec_8k_filing",
            confidence_score=0.98,
        )
        assert event.acquiring_company_name == "Big Corp"
        assert event.acquired_company_name == "Small Startup"
        assert event.acquisition_date == date(2023, 6, 15)
        assert event.source == "sec_8k_filing"
        assert event.confidence_score == 0.98

    def test_ma_event_date_parsing(self):
        """Test M&A event accepts date strings."""
        event = MAEvent(
            acquiring_company_name="Acquirer Inc",
            acquired_company_name="Target LLC",
            acquisition_date="2024-03-20",
            source="press_release",
            confidence_score=0.75,
        )
        assert event.acquisition_date == date(2024, 3, 20)

    def test_ma_event_confidence_score(self):
        """Test M&A event with various confidence scores."""
        for score in [0.0, 0.5, 1.0]:
            event = MAEvent(
                acquiring_company_name="Test Corp",
                acquired_company_name="Test Target",
                acquisition_date=date(2023, 1, 1),
                source="test",
                confidence_score=score,
            )
            assert event.confidence_score == score


class TestResearcherModels:
    """Tests for Researcher and RawResearcher models."""

    def test_valid_researcher(self):
        """Test creating a valid researcher."""
        researcher = Researcher(
            name="Dr. Jane Smith",
            email="jane.smith@university.edu",
            phone="555-1234",
            institution="MIT",
            department="Computer Science",
            title="Associate Professor",
            expertise="Machine Learning, AI",
            bio="Leading researcher in AI...",
            website="https://example.edu/~jsmith",
            orcid="0000-0001-2345-6789",
            linkedin="https://linkedin.com/in/janesmith",
            google_scholar="https://scholar.google.com/citations?user=abc123",
        )
        assert researcher.name == "Dr. Jane Smith"
        assert researcher.institution == "MIT"
        assert researcher.orcid == "0000-0001-2345-6789"

    def test_researcher_minimal(self):
        """Test researcher with only required field (name)."""
        researcher = Researcher(name="John Doe")
        assert researcher.name == "John Doe"
        assert researcher.email is None
        assert researcher.phone is None
        assert researcher.institution is None

    def test_researcher_partial_fields(self):
        """Test researcher with some optional fields."""
        researcher = Researcher(
            name="Dr. Alice Johnson",
            institution="Stanford",
            title="Senior Scientist",
            orcid="0000-0002-1234-5678",
        )
        assert researcher.name == "Dr. Alice Johnson"
        assert researcher.institution == "Stanford"
        assert researcher.title == "Senior Scientist"
        assert researcher.orcid == "0000-0002-1234-5678"
        assert researcher.email is None
        assert researcher.bio is None

    def test_raw_researcher_all_none(self):
        """Test RawResearcher can be created with all None values."""
        raw = RawResearcher()
        assert raw.name is None
        assert raw.email is None
        assert raw.phone is None
        assert raw.institution is None
        assert raw.department is None
        assert raw.title is None
        assert raw.expertise is None

    def test_raw_researcher_partial(self):
        """Test RawResearcher with some fields."""
        raw = RawResearcher(
            name="Bob Smith",
            institution="Harvard",
            email="bob@harvard.edu",
        )
        assert raw.name == "Bob Smith"
        assert raw.institution == "Harvard"
        assert raw.email == "bob@harvard.edu"
        assert raw.phone is None


class TestCompanyModels:
    """Tests for Company, RawCompany, and CompanyMatch models."""

    def test_valid_company(self):
        """Test creating a valid company."""
        company = Company(
            name="Acme Corporation",
            duns="123456789",
            cage="1A2B3",
            address_line_1="123 Main St",
            address_line_2="Suite 500",
            city="Boston",
            state="MA",
            zip_code="02101",
            country="USA",
            business_type="Corporation",
            naics_code="541715",
            naics_description="R&D in Physical, Engineering, and Life Sciences",
            phone="555-0100",
            email="info@acme.com",
            sam_registration_status="Active",
            sam_exclusion_status="Not Excluded",
            last_updated="2023-06-15",
        )
        assert company.name == "Acme Corporation"
        assert company.duns == "123456789"
        assert company.cage == "1A2B3"

    def test_company_minimal(self):
        """Test company with only required field (name)."""
        company = Company(name="Test Company")
        assert company.name == "Test Company"
        assert company.duns is None
        assert company.cage is None

    @pytest.mark.parametrize(
        "duns_input,expected",
        [
            ("12-345-6789", "123456789"),
            ("987654321", "987654321"),
            ("12 345 6789", "123456789"),
        ],
        ids=["with_hyphens", "clean_digits", "with_spaces"],
    )
    def test_duns_validator_normalizes(self, duns_input, expected):
        """Test DUNS validator removes separators and normalizes."""
        company = Company(name="Test Corp", duns=duns_input)
        assert company.duns == expected

    @pytest.mark.parametrize(
        "invalid_duns",
        ["12345", "ABC123DEF", "1234567890"],
        ids=["too_short", "non_numeric", "too_long"],
    )
    def test_duns_validator_rejects_invalid(self, invalid_duns):
        """Test DUNS validator rejects invalid DUNS numbers."""
        with pytest.raises(ValidationError) as exc_info:
            Company(name="Test Corp", duns=invalid_duns)
        assert "DUNS must be 9 digits" in str(exc_info.value)

    @pytest.mark.parametrize(
        "cage_input,expected",
        [
            ("1a2b3", "1A2B3"),
            ("ABCDE", "ABCDE"),
            ("12345", "12345"),
        ],
        ids=["mixed_case", "uppercase", "numeric"],
    )
    def test_cage_validator_normalizes(self, cage_input, expected):
        """Test CAGE validator normalizes to uppercase."""
        company = Company(name="Test Corp", cage=cage_input)
        assert company.cage == expected

    def test_cage_validator_rejects_wrong_length(self):
        """Test CAGE validator rejects non-5-character codes."""
        with pytest.raises(ValidationError) as exc_info:
            Company(name="Test Corp", cage="ABC")
        assert "CAGE code must be 5 characters" in str(exc_info.value)

    @pytest.mark.parametrize(
        "zip_input,expected",
        [
            ("02101", "02101"),
            ("02101-1234", "02101-1234"),
            ("021011234", "021011234"),
        ],
        ids=["5_digit", "9_digit_hyphen", "9_digit_no_hyphen"],
    )
    def test_zip_code_validator_accepts_valid(self, zip_input, expected):
        """Test ZIP code validator accepts valid formats."""
        company = Company(name="Test Corp", zip_code=zip_input)
        assert company.zip_code == expected

    @pytest.mark.parametrize(
        "invalid_zip",
        ["123", "ABCDE", "1234"],
        ids=["too_short", "non_numeric", "4_digits"],
    )
    def test_zip_code_validator_rejects_invalid(self, invalid_zip):
        """Test ZIP code validator rejects invalid formats."""
        with pytest.raises(ValidationError) as exc_info:
            Company(name="Test Corp", zip_code=invalid_zip)
        assert "Invalid ZIP code format" in str(exc_info.value)

    def test_raw_company_all_none(self):
        """Test RawCompany can be created with all None values."""
        raw = RawCompany()
        assert raw.name is None
        assert raw.duns is None
        assert raw.cage is None
        assert raw.address_line_1 is None

    def test_raw_company_partial(self):
        """Test RawCompany with some fields."""
        raw = RawCompany(
            name="Raw Corp",
            duns="123456789",
            city="New York",
            state="NY",
        )
        assert raw.name == "Raw Corp"
        assert raw.duns == "123456789"
        assert raw.city == "New York"
        assert raw.state == "NY"
        assert raw.address_line_1 is None

    def test_company_match_valid(self):
        """Test creating a valid company match."""
        source = Company(name="Source Corp")
        matched = Company(name="Matched Corp")
        match = CompanyMatch(
            source_company=source,
            matched_company=matched,
            confidence_score=0.95,
            match_method="uei_exact",
        )
        assert match.source_company.name == "Source Corp"
        assert match.matched_company.name == "Matched Corp"
        assert match.confidence_score == 0.95
        assert match.match_method == "uei_exact"

    @pytest.mark.parametrize(
        "score,should_pass",
        [
            (0.0, True),
            (0.5, True),
            (1.0, True),
            (-0.1, False),
            (1.5, False),
        ],
        ids=["min_bound", "mid_range", "max_bound", "negative_invalid", "above_one_invalid"],
    )
    def test_company_match_confidence_bounds(self, score, should_pass):
        """Test CompanyMatch confidence_score respects 0-1 bounds."""
        source = Company(name="Source")
        matched = Company(name="Matched")

        if should_pass:
            match = CompanyMatch(
                source_company=source,
                matched_company=matched,
                confidence_score=score,
                match_method="test",
            )
            assert match.confidence_score == score
        else:
            with pytest.raises(ValidationError):
                CompanyMatch(
                    source_company=source,
                    matched_company=matched,
                    confidence_score=score,
                    match_method="test",
                )

    def test_company_match_various_methods(self):
        """Test CompanyMatch with various matching methods."""
        source = Company(name="Source")
        matched = Company(name="Matched")

        methods = ["uei_exact", "duns_exact", "cage_exact", "name_fuzzy", "hybrid"]
        for method in methods:
            match = CompanyMatch(
                source_company=source,
                matched_company=matched,
                confidence_score=0.8,
                match_method=method,
            )
            assert match.match_method == method
