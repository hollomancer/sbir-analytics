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
        assert TransitionType.MERGER == "merger"
        assert TransitionType.ACQUISITION == "acquisition"
        assert TransitionType.BANKRUPTCY == "bankruptcy"
        assert TransitionType.SPIN_OFF == "spin_off"
        assert TransitionType.IPO == "ipo"

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

    def test_duns_validator_removes_separators(self):
        """Test DUNS validator removes hyphens and spaces."""
        company = Company(
            name="Test Corp",
            duns="12-345-6789",
        )
        assert company.duns == "123456789"

    def test_duns_validator_accepts_clean_digits(self):
        """Test DUNS validator accepts 9 clean digits."""
        company = Company(
            name="Test Corp",
            duns="987654321",
        )
        assert company.duns == "987654321"

    def test_duns_validator_rejects_wrong_length(self):
        """Test DUNS validator rejects non-9-digit DUNS."""
        with pytest.raises(ValidationError) as exc_info:
            Company(
                name="Test Corp",
                duns="12345",
            )
        assert "DUNS must be 9 digits" in str(exc_info.value)

    def test_duns_validator_rejects_non_numeric(self):
        """Test DUNS validator rejects non-numeric DUNS."""
        with pytest.raises(ValidationError) as exc_info:
            Company(
                name="Test Corp",
                duns="ABC123DEF",  # pragma: allowlist secret
            )
        assert "DUNS must be 9 digits" in str(exc_info.value)

    def test_cage_validator_normalizes_uppercase(self):
        """Test CAGE validator normalizes to uppercase."""
        company = Company(
            name="Test Corp",
            cage="1a2b3",
        )
        assert company.cage == "1A2B3"

    def test_cage_validator_accepts_valid(self):
        """Test CAGE validator accepts 5-character codes."""
        company = Company(
            name="Test Corp",
            cage="ABCDE",
        )
        assert company.cage == "ABCDE"

    def test_cage_validator_rejects_wrong_length(self):
        """Test CAGE validator rejects non-5-character codes."""
        with pytest.raises(ValidationError) as exc_info:
            Company(
                name="Test Corp",
                cage="ABC",
            )
        assert "CAGE code must be 5 characters" in str(exc_info.value)

    def test_zip_code_validator_accepts_5_digit(self):
        """Test ZIP code validator accepts 5-digit codes."""
        company = Company(
            name="Test Corp",
            zip_code="02101",
        )
        assert company.zip_code == "02101"

    def test_zip_code_validator_accepts_9_digit(self):
        """Test ZIP code validator accepts 9-digit codes with hyphen."""
        company = Company(
            name="Test Corp",
            zip_code="02101-1234",
        )
        assert company.zip_code == "02101-1234"

    def test_zip_code_validator_removes_separators_for_validation(self):
        """Test ZIP code validator removes separators for validation."""
        company = Company(
            name="Test Corp",
            zip_code="021011234",
        )
        assert company.zip_code == "021011234"

    def test_zip_code_validator_rejects_too_short(self):
        """Test ZIP code validator rejects codes < 5 digits."""
        with pytest.raises(ValidationError) as exc_info:
            Company(
                name="Test Corp",
                zip_code="123",
            )
        assert "Invalid ZIP code format" in str(exc_info.value)

    def test_zip_code_validator_rejects_non_numeric(self):
        """Test ZIP code validator rejects non-numeric codes."""
        with pytest.raises(ValidationError) as exc_info:
            Company(
                name="Test Corp",
                zip_code="ABCDE",
            )
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

    def test_company_match_confidence_bounds(self):
        """Test CompanyMatch confidence_score respects 0-1 bounds."""
        source = Company(name="Source")
        matched = Company(name="Matched")

        # Test lower bound
        match = CompanyMatch(
            source_company=source,
            matched_company=matched,
            confidence_score=0.0,
            match_method="test",
        )
        assert match.confidence_score == 0.0

        # Test upper bound
        match = CompanyMatch(
            source_company=source,
            matched_company=matched,
            confidence_score=1.0,
            match_method="test",
        )
        assert match.confidence_score == 1.0

    def test_company_match_confidence_validator_rejects_negative(self):
        """Test confidence_score validator rejects negative values."""
        source = Company(name="Source")
        matched = Company(name="Matched")

        with pytest.raises(ValidationError) as exc_info:
            CompanyMatch(
                source_company=source,
                matched_company=matched,
                confidence_score=-0.1,
                match_method="test",
            )
        assert "Confidence score must be between 0.0 and 1.0" in str(exc_info.value)

    def test_company_match_confidence_validator_rejects_too_high(self):
        """Test confidence_score validator rejects values > 1.0."""
        source = Company(name="Source")
        matched = Company(name="Matched")

        with pytest.raises(ValidationError) as exc_info:
            CompanyMatch(
                source_company=source,
                matched_company=matched,
                confidence_score=1.5,
                match_method="test",
            )
        assert "Confidence score must be between 0.0 and 1.0" in str(exc_info.value)

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
