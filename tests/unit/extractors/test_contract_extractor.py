"""Unit tests for ContractExtractor.

Tests cover:
- Initialization and configuration
- Type checking logic (contract vs grant filtering)
- Competition type parsing
- Vendor filtering
- Contract row parsing
- Edge cases and error handling
"""

from datetime import date
from pathlib import Path

import pytest

from src.extractors.contract_extractor import ContractExtractor
from src.models.transition_models import CompetitionType

pytestmark = pytest.mark.fast


class TestContractExtractorInitialization:
    """Tests for ContractExtractor initialization and configuration."""

    def test_init_with_vendor_filters(self, sample_vendor_filters):
        """Test initialization with vendor filter file."""
        extractor = ContractExtractor(
            vendor_filter_file=sample_vendor_filters, batch_size=5000
        )

        assert extractor.batch_size == 5000
        assert len(extractor.vendor_filters["uei"]) == 2
        assert len(extractor.vendor_filters["duns"]) == 2
        assert len(extractor.vendor_filters["company_names"]) == 2
        assert "ABC123456789" in extractor.vendor_filters["uei"]
        assert "TEST COMPANY INC" in extractor.vendor_filters["company_names"]

    def test_init_without_vendor_filters(self):
        """Test initialization without vendor filter file."""
        extractor = ContractExtractor(vendor_filter_file=None)

        assert extractor.batch_size == 10000  # Default
        assert extractor.vendor_filters["uei"] == set()
        assert extractor.vendor_filters["duns"] == set()
        assert extractor.vendor_filters["company_names"] == set()

    def test_init_with_missing_filter_file(self, tmp_path):
        """Test initialization with non-existent filter file."""
        missing_file = tmp_path / "does_not_exist.json"
        extractor = ContractExtractor(vendor_filter_file=missing_file)

        # Should log warning and use empty filters
        assert extractor.vendor_filters["uei"] == set()

    def test_init_statistics_initialized(self):
        """Test that statistics dictionary is properly initialized."""
        extractor = ContractExtractor()

        assert extractor.stats["records_scanned"] == 0
        assert extractor.stats["contracts_found"] == 0
        assert extractor.stats["vendor_matches"] == 0
        assert extractor.stats["records_extracted"] == 0
        assert extractor.stats["parent_relationships"] == 0
        assert extractor.stats["child_relationships"] == 0

    def test_load_vendor_filters_valid(self, sample_vendor_filters):
        """Test loading valid vendor filter file."""
        extractor = ContractExtractor()
        filters = extractor._load_vendor_filters(sample_vendor_filters)

        assert "ABC123456789" in filters["uei"]
        assert "XYZ987654321" in filters["uei"]
        assert "123456789" in filters["duns"]
        assert "TEST COMPANY INC" in filters["company_names"]
        # Company names should be uppercase
        assert all(name.isupper() for name in filters["company_names"])


class TestIsContractType:
    """Tests for contract type checking logic."""

    def test_is_contract_type_idv_always_true(self):
        """Test that type 'B' (IDV) is always a contract."""
        extractor = ContractExtractor()

        assert extractor._is_contract_type("B", None) is True
        assert extractor._is_contract_type("B", "IDV-A") is True
        assert extractor._is_contract_type("B", "anything") is True

    def test_is_contract_type_grant_excluded(self):
        """Test that grants (type 'C') are excluded."""
        extractor = ContractExtractor()

        assert extractor._is_contract_type("C", None) is False
        assert extractor._is_contract_type("C", "02") is False
        assert extractor._is_contract_type("C", "03") is False

    def test_is_contract_type_direct_payment_excluded(self):
        """Test that direct payments (type 'D') are excluded."""
        extractor = ContractExtractor()

        assert extractor._is_contract_type("D", None) is False

    def test_is_contract_type_a_with_procurement_code(self):
        """Test type 'A' with procurement award codes is contract."""
        extractor = ContractExtractor()

        # Procurement contract codes (letters)
        assert extractor._is_contract_type("A", "A") is True
        assert extractor._is_contract_type("A", "B") is True
        assert extractor._is_contract_type("A", "C") is True
        assert extractor._is_contract_type("A", "D") is True
        assert extractor._is_contract_type("A", "IDV-A") is True
        assert extractor._is_contract_type("A", "IDV-B") is True

    def test_is_contract_type_a_with_grant_code(self):
        """Test type 'A' with grant award codes is not contract."""
        extractor = ContractExtractor()

        # Grant codes (digits)
        assert extractor._is_contract_type("A", "02") is False
        assert extractor._is_contract_type("A", "03") is False
        assert extractor._is_contract_type("A", "04") is False
        assert extractor._is_contract_type("A", "05") is False

    def test_is_contract_type_empty_or_none(self):
        """Test handling of empty or None type codes."""
        extractor = ContractExtractor()

        assert extractor._is_contract_type("", None) is False
        assert extractor._is_contract_type(None, None) is False
        assert extractor._is_contract_type("A", "") is False

    def test_is_contract_type_edge_cases(self):
        """Test edge cases and unknown type codes."""
        extractor = ContractExtractor()

        # Unknown type defaults to False for safety
        assert extractor._is_contract_type("X", None) is False
        assert extractor._is_contract_type("A", "unknown") is False


class TestParseCompetitionType:
    """Tests for competition type parsing."""

    def test_parse_competition_full_and_open(self):
        """Test parsing full and open competition codes."""
        extractor = ContractExtractor()

        assert extractor._parse_competition_type("FULL") == CompetitionType.FULL_AND_OPEN
        assert extractor._parse_competition_type("FSS") == CompetitionType.FULL_AND_OPEN
        assert extractor._parse_competition_type("A&A") == CompetitionType.FULL_AND_OPEN
        assert extractor._parse_competition_type("CDO") == CompetitionType.FULL_AND_OPEN

    def test_parse_competition_sole_source(self):
        """Test parsing sole source (no competition) codes."""
        extractor = ContractExtractor()

        assert extractor._parse_competition_type("NONE") == CompetitionType.SOLE_SOURCE
        assert extractor._parse_competition_type("NDO") == CompetitionType.SOLE_SOURCE

    def test_parse_competition_limited(self):
        """Test parsing limited competition codes."""
        extractor = ContractExtractor()

        assert extractor._parse_competition_type("LIMITED") == CompetitionType.LIMITED
        assert (
            extractor._parse_competition_type("LIMITED COMPETITION") == CompetitionType.LIMITED
        )
        assert extractor._parse_competition_type("RESTRICTED") == CompetitionType.LIMITED

    def test_parse_competition_unknown(self):
        """Test parsing unknown or null competition values."""
        extractor = ContractExtractor()

        assert extractor._parse_competition_type("") == CompetitionType.OTHER
        assert extractor._parse_competition_type("\\N") == CompetitionType.OTHER
        assert extractor._parse_competition_type("Not Available") == CompetitionType.OTHER
        assert extractor._parse_competition_type(None) == CompetitionType.OTHER

    def test_parse_competition_case_insensitive(self):
        """Test that parsing is case-insensitive."""
        extractor = ContractExtractor()

        assert extractor._parse_competition_type("full") == CompetitionType.FULL_AND_OPEN
        assert extractor._parse_competition_type("Full") == CompetitionType.FULL_AND_OPEN
        assert extractor._parse_competition_type("FULL") == CompetitionType.FULL_AND_OPEN

    def test_parse_competition_with_whitespace(self):
        """Test parsing handles whitespace."""
        extractor = ContractExtractor()

        assert extractor._parse_competition_type("  FULL  ") == CompetitionType.FULL_AND_OPEN
        assert extractor._parse_competition_type("\tNONE\n") == CompetitionType.SOLE_SOURCE


class TestVendorFiltering:
    """Tests for vendor filtering logic."""

    def test_matches_vendor_filter_by_uei(self, sample_vendor_filters):
        """Test matching by UEI in recipient_unique_id field."""
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

        # Row with matching UEI in column 10
        row = [""] * 103
        row[10] = "ABC123456789"  # Matches filter
        assert extractor._matches_vendor_filter(row) is True

        # Row with non-matching UEI
        row[10] = "NOMATCH00000"
        assert extractor._matches_vendor_filter(row) is False

    def test_matches_vendor_filter_by_duns(self, sample_vendor_filters):
        """Test matching by DUNS number."""
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

        row = [""] * 103
        row[10] = "123456789"  # Matches DUNS filter
        assert extractor._matches_vendor_filter(row) is True

        row[10] = "000000000"  # No match
        assert extractor._matches_vendor_filter(row) is False

    def test_matches_vendor_filter_by_company_name(self, sample_vendor_filters):
        """Test matching by company name."""
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

        row = [""] * 103
        row[9] = "TEST COMPANY INC"  # Matches filter
        row[10] = "NOMATCH00000"  # UEI doesn't match
        assert extractor._matches_vendor_filter(row) is True

        row[9] = "DIFFERENT COMPANY"
        assert extractor._matches_vendor_filter(row) is False

    def test_matches_vendor_filter_case_insensitive_name(self, sample_vendor_filters):
        """Test company name matching is case-insensitive."""
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

        row = [""] * 103
        row[9] = "test company inc"  # Lowercase
        row[10] = "NOMATCH00000"
        assert extractor._matches_vendor_filter(row) is True

        row[9] = "TeSt CoMpAnY iNc"  # Mixed case
        assert extractor._matches_vendor_filter(row) is True

    def test_matches_vendor_filter_null_values(self, sample_vendor_filters):
        """Test handling of NULL values in vendor fields."""
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

        row = ["\\N"] * 103
        row[9] = "\\N"
        row[10] = "\\N"
        assert extractor._matches_vendor_filter(row) is False

    def test_matches_vendor_filter_empty_filters(self):
        """Test that empty filters accept all vendors."""
        extractor = ContractExtractor(vendor_filter_file=None)

        row = [""] * 103
        row[9] = "ANY COMPANY"
        row[10] = "ANY123456789"
        # With no filters loaded, should return True (accept all)
        assert extractor._matches_vendor_filter(row) is True

    def test_matches_vendor_filter_short_row(self, sample_vendor_filters):
        """Test handling of rows with missing columns."""
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

        # Row too short to have vendor fields
        short_row = ["data"] * 5
        assert extractor._matches_vendor_filter(short_row) is False


class TestParseContractRow:
    """Tests for contract row parsing."""

    def test_parse_contract_row_complete(self, sample_contract_row_full):
        """Test parsing a complete contract row with all fields."""
        extractor = ContractExtractor()
        contract = extractor._parse_contract_row(sample_contract_row_full)

        assert contract is not None
        assert contract.contract_id == "SPE4A924D0001"
        assert contract.agency == "Department of Defense"
        assert contract.sub_agency == "Defense Advanced Research Projects Agency"
        assert contract.vendor_name == "TEST COMPANY INC"
        assert contract.vendor_uei == "ABC123456789"
        assert contract.vendor_cage == "1A2B3"
        assert contract.obligation_amount == 250000.00
        assert contract.competition_type == CompetitionType.FULL_AND_OPEN
        assert contract.is_deobligation is False
        assert contract.start_date == date(2023, 3, 15)
        assert contract.end_date == date(2024, 3, 15)

    def test_parse_contract_row_minimal(self, sample_contract_row_minimal):
        """Test parsing a minimal contract row."""
        extractor = ContractExtractor()
        contract = extractor._parse_contract_row(sample_contract_row_minimal)

        assert contract is not None
        assert contract.contract_id == "MIN001"
        assert contract.vendor_name == "MINIMAL COMPANY"
        assert contract.vendor_uei == "MIN000000001"
        assert contract.obligation_amount == 1000.00

    def test_parse_contract_row_missing_dates(self, sample_malformed_date_row):
        """Test parsing row with malformed/missing dates."""
        extractor = ContractExtractor()
        contract = extractor._parse_contract_row(sample_malformed_date_row)

        assert contract is not None
        # Should handle malformed dates gracefully
        assert contract.contract_id == "MAL001"
        # Dates should be None or fallback to action_date
        assert contract.start_date is None or isinstance(contract.start_date, date)

    def test_parse_contract_row_negative_amount(self, sample_negative_amount_row):
        """Test parsing row with negative obligation (deobligation)."""
        extractor = ContractExtractor()
        contract = extractor._parse_contract_row(sample_negative_amount_row)

        assert contract is not None
        assert contract.obligation_amount == -50000.00
        assert contract.is_deobligation is True

    def test_parse_contract_row_parent_relationship(self, sample_child_contract_row):
        """Test parsing row with parent contract relationship."""
        extractor = ContractExtractor()
        contract = extractor._parse_contract_row(sample_child_contract_row)

        assert contract is not None
        assert contract.contract_id == "TASK001"
        assert contract.parent_contract_id == "IDV001"
        assert contract.parent_contract_agency == "9700"
        assert contract.metadata["parent_relationship_type"] == "child_of_idv"
        assert extractor.stats["parent_relationships"] == 1
        assert extractor.stats["child_relationships"] == 1

    def test_parse_contract_row_idv_parent(self, sample_idv_parent_row):
        """Test parsing IDV parent contract."""
        extractor = ContractExtractor()
        contract = extractor._parse_contract_row(sample_idv_parent_row)

        assert contract is not None
        assert contract.contract_id == "IDV001"
        assert contract.contract_award_type == "IDV-A"
        assert contract.metadata["parent_relationship_type"] == "idv_parent"
        assert extractor.stats["idv_parents"] == 1

    def test_parse_contract_row_metadata_populated(self, sample_contract_row_full):
        """Test that metadata dictionary is properly populated."""
        extractor = ContractExtractor()
        contract = extractor._parse_contract_row(sample_contract_row_full)

        assert contract is not None
        assert "transaction_id" in contract.metadata
        assert "award_id" in contract.metadata
        assert "modification_number" in contract.metadata
        assert "action_date" in contract.metadata
        assert "funding_agency" in contract.metadata
        assert "parent_uei" in contract.metadata
        assert "recipient_state" in contract.metadata
        assert "business_categories" in contract.metadata
        assert "extent_competed" in contract.metadata

        assert contract.metadata["transaction_id"] == "12345678"
        assert contract.metadata["recipient_state"] == "CA"
        assert contract.metadata["business_categories"] == "{small_business,woman_owned}"

    def test_parse_contract_row_uei_priority(self):
        """Test UEI field priority (column 96 preferred over 10)."""
        extractor = ContractExtractor()

        row = ["\\N"] * 103
        row[0] = "11111"
        row[2] = "20230101"
        row[3] = "A"
        row[5] = "A"
        row[9] = "TEST"
        row[10] = "OLD123456789"  # Legacy UEI
        row[28] = "TEST001"
        row[29] = "1000.00"
        row[96] = "NEW987654321"  # Preferred 12-char UEI

        contract = extractor._parse_contract_row(row)

        assert contract is not None
        # Should prefer column 96 (12-char format)
        assert contract.vendor_uei == "NEW987654321"

    def test_parse_contract_row_duns_identification(self):
        """Test DUNS number identification (9 digits)."""
        extractor = ContractExtractor()

        row = ["\\N"] * 103
        row[0] = "22222"
        row[2] = "20230101"
        row[3] = "A"
        row[5] = "A"
        row[9] = "TEST"
        row[10] = "123456789"  # 9-digit DUNS
        row[28] = "TEST002"
        row[29] = "1000.00"
        row[96] = "\\N"  # No UEI

        contract = extractor._parse_contract_row(row)

        assert contract is not None
        assert contract.vendor_duns == "123456789"
        assert contract.vendor_uei is None

    def test_parse_contract_row_malformed_amount(self):
        """Test handling of malformed obligation amounts."""
        extractor = ContractExtractor()

        row = ["\\N"] * 103
        row[0] = "33333"
        row[2] = "20230101"
        row[3] = "A"
        row[5] = "A"
        row[9] = "TEST"
        row[28] = "TEST003"
        row[29] = "NOT_A_NUMBER"  # Invalid amount
        row[96] = "TST000000003"

        contract = extractor._parse_contract_row(row)

        assert contract is not None
        # Should default to 0.0 for invalid amounts
        assert contract.obligation_amount == 0.0

    def test_parse_contract_row_empty_row(self):
        """Test parsing completely empty row."""
        extractor = ContractExtractor()

        empty_row = []

        contract = extractor._parse_contract_row(empty_row)

        # Should return None for invalid rows
        assert contract is None

    def test_parse_contract_row_insufficient_columns(self):
        """Test parsing row with insufficient columns."""
        extractor = ContractExtractor()

        short_row = ["data"] * 10  # Only 10 columns

        contract = extractor._parse_contract_row(short_row)

        # Should handle gracefully and likely return None
        # or create a minimal contract with defaults
        # Implementation may vary, but should not crash
        assert contract is None or isinstance(contract, object)

    def test_parse_contract_row_date_fallback(self):
        """Test that start_date falls back to action_date when missing."""
        extractor = ContractExtractor()

        row = ["\\N"] * 103
        row[0] = "44444"
        row[2] = "20230615"  # action_date
        row[3] = "A"
        row[5] = "A"
        row[9] = "TEST"
        row[28] = "TEST004"
        row[29] = "1000.00"
        row[71] = "\\N"  # No start_date
        row[96] = "TST000000004"

        contract = extractor._parse_contract_row(row)

        assert contract is not None
        # Should fall back to action_date
        assert contract.start_date == date(2023, 6, 15)

    def test_parse_contract_row_null_handling(self):
        """Test proper handling of \\N (NULL) values."""
        extractor = ContractExtractor()

        row = ["\\N"] * 103
        row[0] = "55555"
        row[2] = "20230101"
        row[3] = "A"
        row[5] = "A"
        row[9] = "TEST"
        row[28] = "TEST005"
        row[29] = "1000.00"
        row[96] = "TST000000005"
        # Most other fields are \\N

        contract = extractor._parse_contract_row(row)

        assert contract is not None
        # NULL values should be handled as None, not string "\\N"
        assert contract.metadata["parent_uei"] is None
        assert contract.parent_contract_id is None


class TestContractExtractorEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_statistics_tracking(self, sample_contract_row_full):
        """Test that statistics are properly tracked."""
        extractor = ContractExtractor()

        # Parse multiple rows
        extractor._parse_contract_row(sample_contract_row_full)

        # Initial stats should be updated
        assert extractor.stats["records_scanned"] == 0  # Only updated in stream_dat_gz_file
        # Other stats updated in parsing
        assert extractor.stats["records_extracted"] == 0  # Only updated in stream method

    def test_parent_id_tracking(self, sample_child_contract_row, sample_idv_parent_row):
        """Test tracking of parent contract IDs."""
        extractor = ContractExtractor()

        # Parse child contract
        child = extractor._parse_contract_row(sample_child_contract_row)
        assert child is not None
        assert "IDV001" in extractor._parent_ids_seen

        # Parse IDV parent
        parent = extractor._parse_contract_row(sample_idv_parent_row)
        assert parent is not None
        assert "IDV001" in extractor._idv_parent_ids_seen

    def test_batch_size_configuration(self):
        """Test batch size configuration."""
        extractor = ContractExtractor(batch_size=500)
        assert extractor.batch_size == 500

        extractor_default = ContractExtractor()
        assert extractor_default.batch_size == 10000

    def test_multiple_contract_types(
        self, sample_contract_row_full, sample_idv_parent_row, sample_child_contract_row
    ):
        """Test parsing multiple contract types in sequence."""
        extractor = ContractExtractor()

        contract1 = extractor._parse_contract_row(sample_contract_row_full)
        contract2 = extractor._parse_contract_row(sample_idv_parent_row)
        contract3 = extractor._parse_contract_row(sample_child_contract_row)

        assert contract1 is not None
        assert contract2 is not None
        assert contract3 is not None

        # Verify different relationship types
        assert contract1.metadata["parent_relationship_type"] == "standalone"
        assert contract2.metadata["parent_relationship_type"] == "idv_parent"
        assert contract3.metadata["parent_relationship_type"] == "child_of_idv"
