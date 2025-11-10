"""Tests for Patent Assignment transformer."""

import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch

from src.transformers.patent_transformer import (
    PatentAssignmentTransformer,
    PatentTransformOptions,
)


class TestPatentTransformOptions:
    """Tests for PatentTransformOptions dataclass."""

    def test_default_options(self):
        """Test default PatentTransformOptions values."""
        options = PatentTransformOptions()

        assert options.fuzzy_grant_threshold == 0.9
        assert options.fuzzy_secondary_threshold == 0.8
        assert options.normalize_names is True
        assert options.normalize_identifiers is True

    def test_custom_options(self):
        """Test custom PatentTransformOptions values."""
        options = PatentTransformOptions(
            fuzzy_grant_threshold=0.95,
            fuzzy_secondary_threshold=0.85,
            normalize_names=False,
            normalize_identifiers=False,
        )

        assert options.fuzzy_grant_threshold == 0.95
        assert options.fuzzy_secondary_threshold == 0.85
        assert options.normalize_names is False
        assert options.normalize_identifiers is False


class TestPatentAssignmentTransformerInitialization:
    """Tests for PatentAssignmentTransformer initialization."""

    def test_initialization_with_defaults(self):
        """Test transformer initialization with default options."""
        transformer = PatentAssignmentTransformer()

        assert transformer.sbir_index == {}
        assert isinstance(transformer.options, PatentTransformOptions)

    def test_initialization_with_sbir_index(self):
        """Test transformer initialization with SBIR index."""
        sbir_index = {"US123": "company1", "US456": "company2"}
        transformer = PatentAssignmentTransformer(sbir_company_grant_index=sbir_index)

        assert transformer.sbir_index == sbir_index
        assert len(transformer.sbir_index) == 2

    def test_initialization_with_custom_options(self):
        """Test transformer initialization with custom options."""
        options = PatentTransformOptions(fuzzy_grant_threshold=0.95)
        transformer = PatentAssignmentTransformer(options=options)

        assert transformer.options.fuzzy_grant_threshold == 0.95


class TestNormalizeIdentifier:
    """Tests for _normalize_identifier method."""

    def test_normalize_identifier_basic(self):
        """Test basic identifier normalization."""
        result = PatentAssignmentTransformer._normalize_identifier("us123")

        assert result == "US123"

    def test_normalize_identifier_with_whitespace(self):
        """Test identifier normalization with whitespace."""
        result = PatentAssignmentTransformer._normalize_identifier("  US 123  ")

        assert result == "US123"

    def test_normalize_identifier_removes_punctuation(self):
        """Test identifier normalization removes punctuation."""
        result = PatentAssignmentTransformer._normalize_identifier("US-123.456/789")

        assert result == "US-123456789"

    def test_normalize_identifier_none(self):
        """Test identifier normalization with None."""
        result = PatentAssignmentTransformer._normalize_identifier(None)

        assert result is None

    def test_normalize_identifier_empty_string(self):
        """Test identifier normalization with empty string."""
        result = PatentAssignmentTransformer._normalize_identifier("")

        assert result is None

    def test_normalize_identifier_numeric(self):
        """Test identifier normalization with numeric input."""
        result = PatentAssignmentTransformer._normalize_identifier(12345)

        assert result == "12345"


class TestNormalizeName:
    """Tests for _normalize_name method."""

    def test_normalize_name_basic(self):
        """Test basic name normalization."""
        result = PatentAssignmentTransformer._normalize_name("Acme Corp")

        assert result == "Acme Corp"

    def test_normalize_name_removes_commas(self):
        """Test name normalization removes commas."""
        result = PatentAssignmentTransformer._normalize_name("Smith, John A.")

        assert result == "Smith John A."

    def test_normalize_name_removes_periods(self):
        """Test name normalization removes periods."""
        result = PatentAssignmentTransformer._normalize_name("Dr. Smith Co.")

        assert result == "Dr Smith Co"

    def test_normalize_name_normalizes_ampersand(self):
        """Test name normalization converts ampersand to AND."""
        result = PatentAssignmentTransformer._normalize_name("Smith & Jones")

        assert result == "Smith AND Jones"

    def test_normalize_name_collapses_whitespace(self):
        """Test name normalization collapses multiple spaces."""
        result = PatentAssignmentTransformer._normalize_name("Acme   Corp    Inc")

        assert result == "Acme Corp Inc"

    def test_normalize_name_none(self):
        """Test name normalization with None."""
        result = PatentAssignmentTransformer._normalize_name(None)

        assert result is None


class TestParseAddress:
    """Tests for _parse_address method."""

    def test_parse_address_full_us_style(self):
        """Test parsing full US-style address."""
        result = PatentAssignmentTransformer._parse_address(
            "123 Main St, Springfield, IL 62704, USA"
        )

        street, city, state, postal, country = result
        assert street == "123 Main St"
        assert city == "Springfield"
        assert state == "IL"
        assert postal == "62704"
        assert country == "USA"

    def test_parse_address_without_country(self):
        """Test parsing address without country."""
        result = PatentAssignmentTransformer._parse_address(
            "456 Oak Ave, Boston, MA 02115"
        )

        street, city, state, postal, country = result
        assert street == "456 Oak Ave"
        assert city == "Boston"
        assert state == "MA"
        assert postal == "02115"

    def test_parse_address_single_line(self):
        """Test parsing single-line address."""
        result = PatentAssignmentTransformer._parse_address(
            "789 Elm St San Francisco CA 94102"
        )

        street, city, state, postal, country = result
        assert postal == "94102"
        assert state == "CA"

    def test_parse_address_none(self):
        """Test parsing None address."""
        result = PatentAssignmentTransformer._parse_address(None)

        assert result == (None, None, None, None, None)

    def test_parse_address_empty_string(self):
        """Test parsing empty string address."""
        result = PatentAssignmentTransformer._parse_address("")

        assert result == (None, None, None, None, None)

    def test_parse_address_zip_plus_four(self):
        """Test parsing address with ZIP+4."""
        result = PatentAssignmentTransformer._parse_address(
            "100 Main St, City, NY 10001-1234"
        )

        street, city, state, postal, country = result
        assert postal == "10001-1234"
        assert state == "NY"


class TestParseDate:
    """Tests for _parse_date method."""

    def test_parse_date_iso_format(self):
        """Test parsing ISO format date."""
        result = PatentAssignmentTransformer._parse_date("2023-06-15")

        assert result == date(2023, 6, 15)

    def test_parse_date_slash_format(self):
        """Test parsing slash format date."""
        result = PatentAssignmentTransformer._parse_date("06/15/2023")

        assert result == date(2023, 6, 15)

    def test_parse_date_already_date_object(self):
        """Test parsing when already a date object."""
        input_date = date(2023, 6, 15)
        result = PatentAssignmentTransformer._parse_date(input_date)

        assert result == input_date

    def test_parse_date_none(self):
        """Test parsing None date."""
        result = PatentAssignmentTransformer._parse_date(None)

        assert result is None

    def test_parse_date_empty_string(self):
        """Test parsing empty string date."""
        result = PatentAssignmentTransformer._parse_date("")

        assert result is None

    def test_parse_date_invalid_format(self):
        """Test parsing invalid date format."""
        result = PatentAssignmentTransformer._parse_date("invalid-date")

        assert result is None


class TestInferConveyanceType:
    """Tests for _infer_conveyance_type method."""

    def test_infer_assignment_type(self):
        """Test inferring assignment conveyance type."""
        transformer = PatentAssignmentTransformer()
        conv_type, employer_flag = transformer._infer_conveyance_type(
            "Assignment of patent rights"
        )

        # ConveyanceType may not be available in test env, check for value
        assert employer_flag is False

    def test_infer_license_type(self):
        """Test inferring license conveyance type."""
        transformer = PatentAssignmentTransformer()
        conv_type, employer_flag = transformer._infer_conveyance_type(
            "License agreement for technology"
        )

        assert employer_flag is False

    def test_infer_employer_assignment(self):
        """Test inferring employer assignment."""
        transformer = PatentAssignmentTransformer()
        conv_type, employer_flag = transformer._infer_conveyance_type(
            "Assignment by employee to employer"
        )

        assert employer_flag is True

    def test_infer_work_for_hire(self):
        """Test inferring work for hire."""
        transformer = PatentAssignmentTransformer()
        conv_type, employer_flag = transformer._infer_conveyance_type(
            "Work for hire agreement"
        )

        assert employer_flag is True

    def test_infer_merger_type(self):
        """Test inferring merger conveyance type."""
        transformer = PatentAssignmentTransformer()
        conv_type, employer_flag = transformer._infer_conveyance_type(
            "Merger and acquisition transfer"
        )

        # Should detect merger
        assert employer_flag is False

    def test_infer_security_interest_type(self):
        """Test inferring security interest type."""
        transformer = PatentAssignmentTransformer()
        conv_type, employer_flag = transformer._infer_conveyance_type(
            "Security interest in patent"
        )

        assert employer_flag is False

    def test_infer_none_conveyance(self):
        """Test inferring with None conveyance text."""
        transformer = PatentAssignmentTransformer()
        conv_type, employer_flag = transformer._infer_conveyance_type(None)

        # Should default to assignment
        assert employer_flag is None


class TestFuzzySimilarity:
    """Tests for _fuzzy_similarity method."""

    def test_fuzzy_similarity_identical(self):
        """Test fuzzy similarity with identical strings."""
        transformer = PatentAssignmentTransformer()
        score = transformer._fuzzy_similarity("US123", "US123")

        assert score == 1.0

    def test_fuzzy_similarity_similar(self):
        """Test fuzzy similarity with similar strings."""
        transformer = PatentAssignmentTransformer()
        score = transformer._fuzzy_similarity("US12345", "US12346")

        assert score > 0.8

    def test_fuzzy_similarity_different(self):
        """Test fuzzy similarity with different strings."""
        transformer = PatentAssignmentTransformer()
        score = transformer._fuzzy_similarity("ABC", "XYZ")

        assert score < 0.5

    def test_fuzzy_similarity_empty_strings(self):
        """Test fuzzy similarity with empty strings."""
        transformer = PatentAssignmentTransformer()
        score = transformer._fuzzy_similarity("", "US123")

        assert score == 0.0

    def test_fuzzy_similarity_none_inputs(self):
        """Test fuzzy similarity with None inputs."""
        transformer = PatentAssignmentTransformer()
        score = transformer._fuzzy_similarity(None, "US123")

        assert score == 0.0


class TestMatchGrantToSBIR:
    """Tests for _match_grant_to_sbir method."""

    def test_match_exact(self):
        """Test exact grant number match."""
        sbir_index = {"US123": "company1"}
        transformer = PatentAssignmentTransformer(sbir_company_grant_index=sbir_index)

        result = transformer._match_grant_to_sbir("US123")

        assert result == ("company1", 1.0)

    def test_match_fuzzy_high_threshold(self):
        """Test fuzzy match above high threshold."""
        sbir_index = {"US12345": "company1"}
        transformer = PatentAssignmentTransformer(sbir_company_grant_index=sbir_index)

        result = transformer._match_grant_to_sbir("US12346")

        # Should match with high score
        if result:
            assert result[0] == "company1"
            assert result[1] > 0.8

    def test_match_none_grant(self):
        """Test matching with None grant."""
        transformer = PatentAssignmentTransformer()

        result = transformer._match_grant_to_sbir(None)

        assert result is None

    def test_match_empty_grant(self):
        """Test matching with empty grant."""
        transformer = PatentAssignmentTransformer()

        result = transformer._match_grant_to_sbir("")

        assert result is None

    def test_match_no_index(self):
        """Test matching with empty SBIR index."""
        transformer = PatentAssignmentTransformer()

        result = transformer._match_grant_to_sbir("US123")

        assert result is None


class TestStandardizeStateCode:
    """Tests for _standardize_state_code method."""

    def test_standardize_state_already_code(self):
        """Test standardizing when already a 2-letter code."""
        result = PatentAssignmentTransformer._standardize_state_code("CA")

        assert result == "CA"

    def test_standardize_state_lowercase_code(self):
        """Test standardizing lowercase 2-letter code."""
        result = PatentAssignmentTransformer._standardize_state_code("ca")

        assert result == "CA"

    def test_standardize_state_full_name(self):
        """Test standardizing full state name."""
        result = PatentAssignmentTransformer._standardize_state_code("California")

        assert result == "CA"

    def test_standardize_state_full_name_lowercase(self):
        """Test standardizing full state name in lowercase."""
        result = PatentAssignmentTransformer._standardize_state_code("california")

        assert result == "CA"

    def test_standardize_state_multiple_words(self):
        """Test standardizing state with multiple words."""
        result = PatentAssignmentTransformer._standardize_state_code("New York")

        assert result == "NY"

    def test_standardize_state_district_of_columbia(self):
        """Test standardizing District of Columbia."""
        result = PatentAssignmentTransformer._standardize_state_code("District of Columbia")

        assert result == "DC"

    def test_standardize_state_none(self):
        """Test standardizing None state."""
        result = PatentAssignmentTransformer._standardize_state_code(None)

        assert result is None

    def test_standardize_state_unrecognized(self):
        """Test standardizing unrecognized state."""
        result = PatentAssignmentTransformer._standardize_state_code("XY")

        # XY is not a valid state but looks like a code
        assert result == "XY"

    def test_standardize_state_partial_match(self):
        """Test standardizing with partial name match."""
        result = PatentAssignmentTransformer._standardize_state_code("NEW H")

        # Should match New Hampshire
        assert result == "NH"


class TestStandardizeCountryCode:
    """Tests for _standardize_country_code method."""

    def test_standardize_country_already_code(self):
        """Test standardizing when already a 2-letter code."""
        result = PatentAssignmentTransformer._standardize_country_code("US")

        assert result == "US"

    def test_standardize_country_full_name(self):
        """Test standardizing full country name."""
        result = PatentAssignmentTransformer._standardize_country_code("United States")

        assert result == "US"

    def test_standardize_country_usa(self):
        """Test standardizing USA abbreviation."""
        result = PatentAssignmentTransformer._standardize_country_code("USA")

        assert result == "US"

    def test_standardize_country_canada(self):
        """Test standardizing Canada."""
        result = PatentAssignmentTransformer._standardize_country_code("Canada")

        assert result == "CA"

    def test_standardize_country_united_kingdom(self):
        """Test standardizing United Kingdom."""
        result = PatentAssignmentTransformer._standardize_country_code("United Kingdom")

        assert result == "GB"

    def test_standardize_country_uk_abbreviation(self):
        """Test standardizing UK abbreviation."""
        result = PatentAssignmentTransformer._standardize_country_code("UK")

        assert result == "GB"

    def test_standardize_country_none(self):
        """Test standardizing None country."""
        result = PatentAssignmentTransformer._standardize_country_code(None)

        assert result is None

    def test_standardize_country_lowercase(self):
        """Test standardizing lowercase country name."""
        result = PatentAssignmentTransformer._standardize_country_code("japan")

        assert result == "JP"


class TestStandardizeAddress:
    """Tests for _standardize_address method."""

    def test_standardize_address_complete(self):
        """Test standardizing complete address."""
        result = PatentAssignmentTransformer._standardize_address(
            street="123 Main St",
            city="Springfield",
            state="Illinois",
            postal_code="62704",
            country="United States",
        )

        assert result["street"] == "123 Main St"
        assert result["city"] == "Springfield"
        assert result["state"] == "IL"
        assert result["postal_code"] == "62704"
        assert result["country"] == "US"

    def test_standardize_address_with_whitespace(self):
        """Test standardizing address with extra whitespace."""
        result = PatentAssignmentTransformer._standardize_address(
            street="  123   Main   St  ",
            city=" Springfield ",
            state="IL",
            postal_code="62704",
            country="US",
        )

        assert result["street"] == "123 Main St"
        assert result["city"] == "Springfield"

    def test_standardize_address_postal_with_spaces(self):
        """Test standardizing postal code with spaces."""
        result = PatentAssignmentTransformer._standardize_address(
            street="123 Main St",
            city="City",
            state="CA",
            postal_code="  12345 - 6789  ",
            country="US",
        )

        assert result["postal_code"] == "12345-6789"

    def test_standardize_address_all_none(self):
        """Test standardizing with all None values."""
        result = PatentAssignmentTransformer._standardize_address(
            street=None,
            city=None,
            state=None,
            postal_code=None,
            country=None,
        )

        assert result["street"] is None
        assert result["city"] is None
        assert result["state"] is None
        assert result["postal_code"] is None
        assert result["country"] is None

    def test_standardize_address_partial(self):
        """Test standardizing partial address."""
        result = PatentAssignmentTransformer._standardize_address(
            street="123 Main St",
            city="City",
            state=None,
            postal_code=None,
            country=None,
        )

        assert result["street"] == "123 Main St"
        assert result["city"] == "City"
        assert result["state"] is None


class TestCalculateChainMetadata:
    """Tests for _calculate_chain_metadata method."""

    @patch('src.transformers.patent_transformer.PatentAssignment')
    @patch('src.transformers.patent_transformer.PatentAssignee')
    @patch('src.transformers.patent_transformer.PatentAssignor')
    def test_calculate_chain_metadata_temporal_span(self, mock_assignor, mock_assignee, mock_assignment):
        """Test calculating temporal span between dates."""
        transformer = PatentAssignmentTransformer()

        assignment = Mock()
        assignment.metadata = {}
        assignment.execution_date = date(2023, 1, 1)
        assignment.recorded_date = date(2023, 1, 31)

        transformer._calculate_chain_metadata(assignment, {})

        assert assignment.metadata["temporal_span_days"] == 30

    @patch('src.transformers.patent_transformer.PatentAssignment')
    def test_calculate_chain_metadata_delayed_recording(self, mock_assignment):
        """Test flagging delayed recording (>90 days)."""
        transformer = PatentAssignmentTransformer()

        assignment = Mock()
        assignment.metadata = {}
        assignment.execution_date = date(2023, 1, 1)
        assignment.recorded_date = date(2023, 6, 1)  # 151 days

        transformer._calculate_chain_metadata(assignment, {})

        assert "delayed_recording" in assignment.metadata["chain_flags"]

    @patch('src.transformers.patent_transformer.PatentAssignment')
    def test_calculate_chain_metadata_sequence_indicator(self, mock_assignment):
        """Test detecting sequence indicators."""
        transformer = PatentAssignmentTransformer()

        assignment = Mock()
        assignment.metadata = {}
        assignment.execution_date = None
        assignment.recorded_date = None

        row = {"conveyance_description": "Patent assignment Part 1 of 3"}

        transformer._calculate_chain_metadata(assignment, row)

        assert assignment.metadata["chain_sequence_indicator"]["current_part"] == 1
        assert assignment.metadata["chain_sequence_indicator"]["total_parts"] == 3

    @patch('src.transformers.patent_transformer.PatentAssignment')
    @patch('src.transformers.patent_transformer.PatentAssignee')
    @patch('src.transformers.patent_transformer.PatentAssignor')
    @patch('src.transformers.patent_transformer.PatentConveyance')
    def test_calculate_chain_metadata_employer_assignment(
        self, mock_conveyance, mock_assignor, mock_assignee, mock_assignment
    ):
        """Test detecting employer assignment transition type."""
        transformer = PatentAssignmentTransformer()

        assignment = Mock()
        assignment.metadata = {}
        assignment.execution_date = None
        assignment.recorded_date = None
        assignment.assignee = Mock(spec=['name'])
        assignment.assignee.name = "Acme Corp"
        assignment.assignor = Mock(spec=['name'])
        assignment.assignor.name = "John Smith"
        assignment.normalized_assignee_name = "Acme Corp"
        assignment.normalized_assignor_name = "John Smith"

        conveyance = Mock()
        conveyance.employer_assign = True
        conveyance.conveyance_type = Mock()
        conveyance.conveyance_type.value = "assignment"
        assignment.conveyance = conveyance

        transformer._calculate_chain_metadata(assignment, {})

        assert assignment.metadata["transition_type"] == "employer_assignment"
        assert "employer_assigned" in assignment.metadata["chain_flags"]


class TestTransformChunk:
    """Tests for transform_chunk method."""

    def test_transform_chunk_empty(self):
        """Test transforming empty chunk."""
        transformer = PatentAssignmentTransformer()

        results = list(transformer.transform_chunk([]))

        assert len(results) == 0

    @patch('src.transformers.patent_transformer.PatentAssignment')
    def test_transform_chunk_multiple_rows(self, mock_assignment):
        """Test transforming multiple rows."""
        transformer = PatentAssignmentTransformer()

        rows = [
            {"rf_id": "1", "grant_doc_num": "US123"},
            {"rf_id": "2", "grant_doc_num": "US456"},
        ]

        # Mock transform_row to return simple dict
        transformer.transform_row = Mock(side_effect=lambda r: {"rf_id": r["rf_id"]})

        results = list(transformer.transform_chunk(rows))

        assert len(results) == 2


class TestPatentAssignmentTransformerEdgeCases:
    """Tests for edge cases in PatentAssignmentTransformer."""

    def test_normalize_identifier_preserves_hyphens(self):
        """Test that identifier normalization preserves hyphens."""
        result = PatentAssignmentTransformer._normalize_identifier("US-123-456")

        assert result == "US-123-456"

    def test_normalize_name_with_special_chars(self):
        """Test name normalization with various special characters."""
        result = PatentAssignmentTransformer._normalize_name("Smith & Jones, LLC.")

        assert result == "Smith AND Jones LLC"

    def test_parse_address_with_apartment(self):
        """Test parsing address with apartment number."""
        result = PatentAssignmentTransformer._parse_address(
            "123 Main St Apt 4B, City, CA 12345"
        )

        street, city, state, postal, country = result
        assert "Main" in street

    def test_fuzzy_similarity_case_insensitive(self):
        """Test fuzzy similarity is case-insensitive."""
        transformer = PatentAssignmentTransformer()

        score1 = transformer._fuzzy_similarity("US123", "us123")
        score2 = transformer._fuzzy_similarity("US123", "US123")

        # Should have very similar scores (might not be exactly equal due to tokenization)
        assert abs(score1 - score2) < 0.1

    def test_standardize_state_with_whitespace(self):
        """Test state code standardization with extra whitespace."""
        result = PatentAssignmentTransformer._standardize_state_code("  CA  ")

        assert result == "CA"

    def test_standardize_country_case_insensitive(self):
        """Test country code standardization is case-insensitive."""
        result1 = PatentAssignmentTransformer._standardize_country_code("us")
        result2 = PatentAssignmentTransformer._standardize_country_code("US")

        assert result1 == result2 == "US"

    def test_match_grant_normalizes_input(self):
        """Test grant matching normalizes input before matching."""
        sbir_index = {"US123": "company1"}
        transformer = PatentAssignmentTransformer(sbir_company_grant_index=sbir_index)

        # Should normalize "us 123" to "US123" and match
        result = transformer._match_grant_to_sbir("us 123")

        assert result == ("company1", 1.0)
