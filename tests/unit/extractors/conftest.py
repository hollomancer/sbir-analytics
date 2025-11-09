"""Shared fixtures for extractor tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_vendor_filters(tmp_path):
    """Sample vendor filter JSON file."""
    filter_data = {
        "uei": ["ABC123456789", "XYZ987654321"],
        "duns": ["123456789", "987654321"],
        "company_names": ["TEST COMPANY INC", "ACME CORPORATION"],
    }
    filter_file = tmp_path / "vendor_filters.json"
    with open(filter_file, "w") as f:
        json.dump(filter_data, f)
    return filter_file


@pytest.fixture
def empty_vendor_filters():
    """Empty vendor filter set."""
    return {"uei": set(), "duns": set(), "company_names": set()}


@pytest.fixture
def sample_contract_row_full():
    """Complete 102-column contract row with all fields populated."""
    # Based on USASPENDING_COLUMNS mapping in contract_extractor.py
    row = [""] * 103  # 103 columns (0-102)

    # Core identifiers
    row[0] = "12345678"  # transaction_id
    row[1] = "CONT_AWD_1234_9700_SPE4A924D0001"  # generated_unique_award_id
    row[2] = "20230315"  # action_date (YYYYMMDD)
    row[3] = "A"  # type (Contract)
    row[4] = "A"  # action_type
    row[5] = "A"  # award_type_code (procurement contract)
    row[6] = "New Contract"  # action_type_description

    # Award description
    row[7] = "Software development services for data analytics platform"  # award_description
    row[8] = "0"  # modification_number
    row[9] = "TEST COMPANY INC"  # recipient_name

    # Recipient identifiers (legacy)
    row[10] = "ABC123456789"  # recipient_unique_id (UEI or DUNS)

    # Agency info
    row[11] = "9700"  # awarding_agency_code
    row[12] = "Department of Defense"  # awarding_agency_name
    row[13] = "9700"  # awarding_sub_tier_agency_code
    row[14] = "Defense Advanced Research Projects Agency"  # awarding_sub_tier_agency_name
    row[15] = "097"  # awarding_toptier_agency_code
    row[16] = "Department of Defense"  # awarding_toptier_agency_name

    # Business categories
    row[17] = "{small_business,woman_owned}"  # business_categories

    # Fill in middle columns
    for i in range(18, 28):
        row[i] = "\\N"

    # Identifiers
    row[28] = "SPE4A924D0001"  # piid (Procurement Instrument ID)
    row[29] = "250000.00"  # federal_action_obligation

    # Funding agency (columns 30-34)
    row[30] = "\\N"
    row[31] = "9700"  # funding_agency_code
    row[32] = "Department of Defense"  # funding_agency_name
    row[33] = "9700"  # funding_sub_tier_agency_code
    row[34] = "Defense Advanced Research Projects Agency"  # funding_sub_tier_agency_name

    # Fill middle columns
    for i in range(35, 63):
        row[i] = "\\N"

    # Location
    row[63] = "CA"  # recipient_state_code
    row[64] = "California"  # recipient_state_name

    # Fill more middle columns
    for i in range(65, 70):
        row[i] = "\\N"

    # Performance period
    row[70] = "20240315"  # period_of_performance_current_end_date
    row[71] = "20230315"  # period_of_performance_start_date

    # Fill more middle columns
    for i in range(72, 96):
        row[i] = "\\N"

    # Additional identifiers
    row[96] = "ABC123456789"  # recipient_uei (12-character format)
    row[97] = "XYZ987654321"  # parent_uei
    row[98] = "1A2B3"  # cage_code
    row[99] = "FULL"  # extent_competed (Full and open competition)
    row[100] = "A"  # contract_award_type
    row[101] = "\\N"  # referenced_idv_agency_iden
    row[102] = "\\N"  # referenced_idv_piid

    return row


@pytest.fixture
def sample_contract_row_minimal():
    """Minimal valid contract row with only required fields."""
    row = ["\\N"] * 103

    # Minimum required fields for a valid contract
    row[0] = "99999"  # transaction_id
    row[1] = "CONT_AWD_MINIMAL"  # award_id
    row[2] = "20230101"  # action_date
    row[3] = "B"  # type (IDV - always contract)
    row[5] = "IDV-A"  # award_type_code
    row[9] = "MINIMAL COMPANY"  # recipient_name
    row[28] = "MIN001"  # piid
    row[29] = "1000.00"  # obligation_amount
    row[96] = "MIN000000001"  # recipient_uei

    return row


@pytest.fixture
def sample_grant_row():
    """Grant row that should be filtered out (not a contract)."""
    row = ["\\N"] * 103

    row[0] = "88888"
    row[1] = "GRANT_AWD_001"
    row[2] = "20230201"
    row[3] = "C"  # type = Grant (NOT a contract)
    row[5] = "02"  # award_type_code (grant)
    row[9] = "GRANT RECIPIENT"
    row[96] = "GRT000000001"
    row[29] = "50000.00"

    return row


@pytest.fixture
def sample_idv_parent_row():
    """IDV parent contract row."""
    row = ["\\N"] * 103

    row[0] = "77777"
    row[1] = "IDV_PARENT_001"
    row[2] = "20230115"
    row[3] = "B"  # type = IDV
    row[5] = "IDV-A"
    row[9] = "IDV COMPANY"
    row[28] = "IDV001"  # piid
    row[29] = "5000000.00"
    row[96] = "IDV000000001"
    row[99] = "FULL"
    row[100] = "IDV-A"  # contract_award_type indicates IDV

    return row


@pytest.fixture
def sample_child_contract_row():
    """Child contract referencing an IDV parent."""
    row = ["\\N"] * 103

    row[0] = "66666"
    row[1] = "CHILD_TASK_001"
    row[2] = "20230120"
    row[3] = "A"
    row[5] = "A"
    row[9] = "IDV COMPANY"
    row[28] = "TASK001"  # piid
    row[29] = "100000.00"
    row[96] = "IDV000000001"
    row[99] = "CDO"  # Competitive Delivery Order
    row[100] = "A"
    row[101] = "9700"  # referenced_idv_agency_iden
    row[102] = "IDV001"  # referenced_idv_piid (parent)

    return row


@pytest.fixture
def sample_malformed_date_row():
    """Contract row with malformed dates."""
    row = ["\\N"] * 103

    row[0] = "55555"
    row[1] = "MALFORMED_DATE_001"
    row[2] = "INVALID"  # Bad date format
    row[3] = "A"
    row[5] = "A"
    row[9] = "BAD DATE COMPANY"
    row[28] = "MAL001"
    row[29] = "10000.00"
    row[70] = "99999999"  # Invalid end date
    row[71] = "BADDATE"  # Invalid start date
    row[96] = "MAL000000001"

    return row


@pytest.fixture
def sample_negative_amount_row():
    """Contract row with negative obligation (deobligation)."""
    row = ["\\N"] * 103

    row[0] = "44444"
    row[1] = "DEOBLIG_001"
    row[2] = "20230301"
    row[3] = "A"
    row[5] = "A"
    row[9] = "DEOBLIGATION COMPANY"
    row[28] = "DEOB001"
    row[29] = "-50000.00"  # Negative amount
    row[96] = "DEB000000001"

    return row
