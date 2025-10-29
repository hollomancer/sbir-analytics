import pytest

from src.extractors.contract_extractor import ContractExtractor
from src.models.transition_models import FederalContract


def _build_row_with_length(length: int = 110) -> list[str]:
    """Utility to create a default USAspending row with sensible defaults."""
    return [""] * length


def _populate_base_contract_fields(row_data: list[str]) -> None:
    """Populate common fields required for parsing a contract row."""
    row_data[0] = "999999"  # transaction_id
    row_data[1] = "AWARD-0001"  # generated_unique_award_id
    row_data[2] = "20240115"  # action_date
    row_data[3] = "A"  # type (contract)
    row_data[4] = "A"  # action_type
    row_data[5] = "A"  # award_type_code (contract indicator)
    row_data[7] = "Prototype development services"  # award_description
    row_data[8] = "0"  # modification_number
    row_data[9] = "Acme Defense Systems"  # recipient_name
    row_data[10] = "UEIACME12345"  # recipient_unique_id
    row_data[11] = "9700"  # awarding_agency_code
    row_data[12] = "Department of Defense"  # awarding_agency_name
    row_data[13] = "9701"  # awarding_sub_tier_agency_code
    row_data[14] = "Department of the Air Force"  # awarding_sub_tier_agency_name
    row_data[15] = "097"  # awarding_toptier_agency_code
    row_data[16] = "Department of Defense"  # awarding_toptier_agency_name
    row_data[17] = "{small_business}"  # business_categories
    row_data[28] = "PIID-001"  # piid
    row_data[29] = "1000000"  # federal_action_obligation
    row_data[31] = "097"  # funding_agency_code
    row_data[32] = "Department of Defense"  # funding_agency_name
    row_data[33] = "0970"  # funding_sub_tier_agency_code
    row_data[34] = "Office of the Secretary"  # funding_sub_tier_agency_name
    row_data[63] = "VA"  # recipient_state_code
    row_data[64] = "Virginia"  # recipient_state_name
    row_data[70] = "20250315"  # period_of_performance_current_end_date
    row_data[71] = "20240201"  # period_of_performance_start_date
    row_data[96] = "UEIACME12345"  # recipient_uei
    row_data[97] = "UEIACME_PARENT"  # parent_uei
    row_data[98] = "CAGE1234"  # cage_code
    row_data[99] = "FULL"  # extent_competed (full and open)


@pytest.fixture
def extractor() -> ContractExtractor:
    """Instantiate a ContractExtractor with no vendor filters for testing."""
    return ContractExtractor(vendor_filter_file=None, batch_size=10)


def test_parse_contract_child_sets_parent_fields(extractor: ContractExtractor) -> None:
    """Ensure child task orders populate parent metadata and stats."""
    row_data = _build_row_with_length()
    _populate_base_contract_fields(row_data)

    parent_piid = "IDV-PIID-1234"
    parent_agency = "0970"
    row_data[100] = "A"  # contract_award_type
    row_data[101] = parent_agency  # referenced_idv_agency_iden
    row_data[102] = parent_piid  # referenced_idv_piid

    contract: FederalContract | None = extractor._parse_contract_row(row_data)  # type: ignore[attr-defined]

    assert contract is not None, "Expected contract to be parsed successfully"
    assert contract.parent_contract_id == parent_piid
    assert contract.parent_contract_agency == parent_agency
    assert contract.contract_award_type == "A"
    assert (
        contract.metadata.get("parent_relationship_type") == "child_of_idv"
    ), "Child contracts should be labeled as such in metadata"
    assert (
        contract.metadata.get("parent_idv_piid") == parent_piid
    ), "Metadata should carry parent PIID for downstream processing"
    assert (
        contract.metadata.get("referenced_idv_agency") == parent_agency
    ), "Metadata should capture the referenced agency identifier"

    # Stats should record the parent-child relationship
    assert extractor.stats["parent_relationships"] == 1
    assert extractor.stats["child_relationships"] == 1
    assert extractor.stats["idv_parents"] == 0
    assert extractor.stats["unique_parent_ids"] == 0
    assert extractor.stats["unique_idv_parents"] == 0


def test_parse_idv_parent_contract_classification(extractor: ContractExtractor) -> None:
    """IDV/BPA parent records should be classified and tracked distinctly."""
    row_data = _build_row_with_length()
    _populate_base_contract_fields(row_data)

    row_data[100] = "IDV-B"  # contract_award_type indicating an IDV parent
    row_data[102] = ""  # no parent reference -> this is the parent record itself

    contract: FederalContract | None = extractor._parse_contract_row(row_data)  # type: ignore[attr-defined]

    assert contract is not None, "Expected contract to be parsed successfully"
    assert contract.parent_contract_id is None, "Parent contracts should not report a parent ID"
    assert (
        contract.contract_award_type == "IDV-B"
    ), "Contract award type should be preserved on the model"
    assert (
        contract.metadata.get("parent_relationship_type") == "idv_parent"
    ), "Metadata should flag this record as an IDV parent"
    assert (
        contract.metadata.get("parent_idv_piid") is None
    ), "Parent records should not carry a referenced parent PIID"

    # Stats should record the IDV parent classification without counting a child relationship
    assert extractor.stats["idv_parents"] == 1
    assert extractor.stats["parent_relationships"] == 0
    assert extractor.stats["child_relationships"] == 0
    assert extractor.stats["unique_parent_ids"] == 0
    assert extractor.stats["unique_idv_parents"] == 0
