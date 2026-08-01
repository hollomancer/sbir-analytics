"""Focused parent/child classification tests for named contract rows."""

import pytest

from sbir_etl.extractors.contract_extractor import ContractExtractor


pytestmark = pytest.mark.fast


def _base_contract_row() -> dict[str, str | None]:
    return {
        "transaction_unique_id": "TX-999999",
        "generated_unique_award_id": "AWARD-0001",
        "action_date": "20240115",
        "transaction_description": "Prototype development services",
        "modification_number": "0",
        "recipient_name": "Acme Defense Systems",
        "recipient_unique_id": "123456789",
        "recipient_uei": "UEIACME12345",
        "awarding_toptier_agency_name": "Department of Defense",
        "awarding_subtier_agency_name": "Department of the Air Force",
        "business_categories": "{small_business}",
        "piid": "PIID-001",
        "federal_action_obligation": "1000000",
        "funding_toptier_agency_name": "Department of Defense",
        "recipient_location_state_code": "VA",
        "period_of_performance_current_end_date": "20250315",
        "period_of_performance_start_date": "20240201",
        "parent_uei": "UEIACMEPARNT",
        "cage_code": "CAGE1",
        "extent_competed": "FULL",
        "research": "SR2",
        "naics_code": "541715",
        "product_or_service_code": "AC12",
        "parent_award_id": None,
        "referenced_idv_agency_iden": None,
        "referenced_idv_piid": None,
        "contract_award_type": "A",
    }


@pytest.fixture
def extractor() -> ContractExtractor:
    return ContractExtractor(vendor_filter_file=None, batch_size=10)


def test_parse_contract_child_sets_parent_fields(extractor: ContractExtractor) -> None:
    row = _base_contract_row()
    row.update(
        {
            "contract_award_type": "A",
            "referenced_idv_agency_iden": "0970",
            "referenced_idv_piid": "IDV-PIID-1234",
        }
    )

    contract = extractor._parse_contract_row(row)

    assert contract.parent_contract_id == "IDV-PIID-1234"
    assert contract.parent_contract_agency == "0970"
    assert contract.contract_award_type == "A"
    assert contract.metadata["parent_relationship_type"] == "child_of_idv"
    assert contract.metadata["parent_idv_piid"] == "IDV-PIID-1234"
    assert contract.metadata["referenced_idv_agency"] == "0970"
    assert extractor.stats["parent_relationships"] == 1
    assert extractor.stats["child_relationships"] == 1
    assert extractor.stats["idv_parents"] == 0


@pytest.mark.parametrize("award_type", ["IDV-B", "BPA", "BOA", "IDIQ"])
def test_parse_idv_parent_contract_classification(
    extractor: ContractExtractor,
    award_type: str,
) -> None:
    row = _base_contract_row()
    row["contract_award_type"] = award_type

    contract = extractor._parse_contract_row(row)

    assert contract.parent_contract_id is None
    assert contract.contract_award_type == award_type
    assert contract.metadata["parent_relationship_type"] == "idv_parent"
    assert contract.metadata["parent_idv_piid"] is None
    assert extractor.stats["idv_parents"] == 1
    assert extractor.stats["parent_relationships"] == 0
    assert extractor.stats["child_relationships"] == 0


def test_explicit_parent_award_id_takes_precedence(
    extractor: ContractExtractor,
) -> None:
    row = _base_contract_row()
    row.update(
        {
            "parent_award_id": "GENERATED-IDV-AWARD-ID",
            "referenced_idv_piid": "IDV-PIID-FALLBACK",
            "referenced_idv_agency_iden": "0970",
        }
    )

    contract = extractor._parse_contract_row(row)

    assert contract.parent_contract_id == "GENERATED-IDV-AWARD-ID"
    assert contract.metadata["parent_idv_piid"] == "GENERATED-IDV-AWARD-ID"
    assert extractor._parent_ids_seen == {"GENERATED-IDV-AWARD-ID"}
