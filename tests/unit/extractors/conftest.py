"""Shared fixtures for schema-verified contract extractor tests."""

import json
from collections.abc import Callable, Mapping, Sequence

import pytest


CONTRACT_COPY_COLUMNS = (
    "transaction_unique_id",
    "is_fpds",
    "research",
    "generated_unique_award_id",
    "product_or_service_code",
    "naics_code",
    "recipient_uei",
    "recipient_unique_id",
    "recipient_name",
    "awarding_toptier_agency_name",
    "awarding_subtier_agency_name",
    "action_date",
    "extent_competed",
    "federal_action_obligation",
    "piid",
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
    "cage_code",
    "parent_award_id",
    "referenced_idv_piid",
    "referenced_idv_agency_iden",
    "contract_award_type",
    "transaction_description",
    "modification_number",
    "funding_toptier_agency_name",
    "parent_uei",
    "recipient_location_state_code",
    "business_categories",
)


def _base_contract_row() -> dict[str, str | None]:
    return {
        "transaction_unique_id": "TX-12345678",
        "is_fpds": "t",
        "research": "SR2",
        "generated_unique_award_id": "CONT_AWD_1234_9700_SPE4A924D0001",
        "product_or_service_code": "AC12",
        "naics_code": "541715",
        "recipient_uei": "ABC123456789",  # pragma: allowlist secret
        "recipient_unique_id": "123456789",
        "recipient_name": "TEST COMPANY INC",
        "awarding_toptier_agency_name": "Department of Defense",
        "awarding_subtier_agency_name": ("Defense Advanced Research Projects Agency"),
        "action_date": "20230315",
        "extent_competed": "FULL",
        "federal_action_obligation": "250000.00",
        "piid": "SPE4A924D0001",
        "period_of_performance_start_date": "20230315",
        "period_of_performance_current_end_date": "20240315",
        "cage_code": "1A2B3",
        "parent_award_id": None,
        "referenced_idv_piid": None,
        "referenced_idv_agency_iden": None,
        "contract_award_type": "A",
        "transaction_description": ("Software development services for data analytics platform"),
        "modification_number": "0",
        "funding_toptier_agency_name": "Department of Defense",
        "parent_uei": "XYZ987654321",
        "recipient_location_state_code": "CA",
        "business_categories": "{small_business,woman_owned}",
    }


@pytest.fixture
def sample_vendor_filters(tmp_path):
    """Sample vendor filter JSON file."""
    filter_data = {
        "uei": ["ABC123456789", "XYZ987654321"],  # pragma: allowlist secret
        "duns": ["123456789", "987654321"],
        "company_names": ["TEST COMPANY INC", "ACME CORPORATION"],
    }
    filter_file = tmp_path / "vendor_filters.json"
    with open(filter_file, "w") as file:
        json.dump(filter_data, file)
    return filter_file


@pytest.fixture
def empty_vendor_filters():
    """Empty vendor filter set."""
    return {"uei": set(), "duns": set(), "company_names": set()}


@pytest.fixture
def contract_copy_columns() -> tuple[str, ...]:
    """COPY-owned serialized column order used by line/streaming tests."""
    return CONTRACT_COPY_COLUMNS


@pytest.fixture
def serialize_contract_row() -> Callable[[Mapping[str, str | None], Sequence[str]], str]:
    """Serialize a named source row in an explicitly supplied COPY order."""

    def serialize(row: Mapping[str, str | None], columns: Sequence[str]) -> str:
        return "\t".join(
            r"\N" if row.get(column) is None else str(row[column]) for column in columns
        )

    return serialize


@pytest.fixture
def sample_contract_row_full() -> dict[str, str | None]:
    """Complete named FPDS transaction row."""
    return _base_contract_row()


@pytest.fixture
def sample_contract_row_minimal() -> dict[str, str | None]:
    """Minimal named row accepted by the model parser."""
    row = _base_contract_row()
    row.update(
        {
            "transaction_unique_id": "TX-MINIMAL",
            "generated_unique_award_id": "CONT_AWD_MINIMAL",
            "recipient_uei": "MIN000000001",
            "recipient_unique_id": None,
            "recipient_name": "MINIMAL COMPANY",
            "piid": "MIN001",
            "federal_action_obligation": "1000.00",
            "action_date": "20230101",
            "period_of_performance_start_date": None,
            "period_of_performance_current_end_date": None,
            "cage_code": None,
        }
    )
    return row


@pytest.fixture
def sample_grant_row() -> dict[str, str | None]:
    """Non-FPDS transaction row filtered when reading the parent partition."""
    row = _base_contract_row()
    row.update(
        {
            "transaction_unique_id": "TX-FABS-001",
            "generated_unique_award_id": "ASST_NON_FPDS_001",
            "is_fpds": "f",
            "recipient_uei": "GRT000000001",
            "recipient_name": "GRANT RECIPIENT",
            "federal_action_obligation": "50000.00",
        }
    )
    return row


@pytest.fixture
def sample_idv_parent_row() -> dict[str, str | None]:
    """Named row representing an IDV parent contract."""
    row = _base_contract_row()
    row.update(
        {
            "transaction_unique_id": "TX-IDV-PARENT-001",
            "generated_unique_award_id": "IDV_PARENT_001",
            "recipient_uei": "IDV000000001",
            "recipient_name": "IDV COMPANY",
            "piid": "IDV001",
            "federal_action_obligation": "5000000.00",
            "contract_award_type": "IDV-A",
        }
    )
    return row


@pytest.fixture
def sample_child_contract_row() -> dict[str, str | None]:
    """Named row representing a task order under an IDV parent."""
    row = _base_contract_row()
    row.update(
        {
            "transaction_unique_id": "TX-CHILD-TASK-001",
            "generated_unique_award_id": "CHILD_TASK_001",
            "recipient_uei": "IDV000000001",
            "recipient_name": "IDV COMPANY",
            "piid": "TASK001",
            "federal_action_obligation": "100000.00",
            "extent_competed": "CDO",
            "referenced_idv_agency_iden": "9700",
            "referenced_idv_piid": "IDV001",
        }
    )
    return row


@pytest.fixture
def sample_malformed_date_row() -> dict[str, str | None]:
    """Named contract row with malformed date fields."""
    row = _base_contract_row()
    row.update(
        {
            "transaction_unique_id": "TX-MALFORMED-DATE-001",
            "generated_unique_award_id": "MALFORMED_DATE_001",
            "recipient_uei": "MAL000000001",
            "recipient_name": "BAD DATE COMPANY",
            "piid": "MAL001",
            "federal_action_obligation": "10000.00",
            "action_date": "INVALID",
            "period_of_performance_start_date": "BADDATE",
            "period_of_performance_current_end_date": "99999999",
        }
    )
    return row


@pytest.fixture
def sample_negative_amount_row() -> dict[str, str | None]:
    """Named contract row with a signed deobligation."""
    row = _base_contract_row()
    row.update(
        {
            "transaction_unique_id": "TX-DEOBLIG-001",
            "generated_unique_award_id": "DEOBLIG_001",
            "recipient_uei": "DEB000000001",
            "recipient_name": "DEOBLIGATION COMPANY",
            "piid": "DEOB001",
            "federal_action_obligation": "-50000.00",
            "action_date": "20230301",
        }
    )
    return row
