"""Unit tests for company enrichment orchestration logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sbir_etl.enrichers.company_enrichment import (
    FederalAwardSummary,
    SAMEntityRecord,
    USARecipientProfile,
    fetch_fpds_descriptions,
    fetch_usaspending_contract_descriptions,
    lookup_company_federal_awards,
    lookup_sam_entity,
    lookup_usaspending_recipient,
    usaspending_autocomplete,
    usaspending_search,
)


pytestmark = pytest.mark.fast

MODULE = "sbir_etl.enrichers.company_enrichment"


# ---------------------------------------------------------------------------
# usaspending_autocomplete
# ---------------------------------------------------------------------------


class TestUSAspendingAutocomplete:
    @patch(f"{MODULE}.SyncUSAspendingClient")
    def test_match_with_uei(self, MockClient):
        client = MockClient.return_value
        client.autocomplete_recipient.return_value = {
            "results": [
                {"legal_business_name": "Acme Inc", "uei": "ABC123DEF456"}
            ]
        }

        result = usaspending_autocomplete("Acme Inc")

        assert result == {"uei": "ABC123DEF456", "name": "Acme Inc"}
        client.close.assert_called_once()

    @patch(f"{MODULE}.SyncUSAspendingClient")
    def test_match_without_uei_returns_best_candidate(self, MockClient):
        client = MockClient.return_value
        client.autocomplete_recipient.return_value = {
            "results": [
                {"legal_business_name": "Acme Incorporated", "uei": None}
            ]
        }

        result = usaspending_autocomplete("Acme Inc")

        assert result is not None
        assert result["name"] == "Acme Incorporated"
        assert result["uei"] is None

    @patch(f"{MODULE}.SyncUSAspendingClient")
    def test_no_match_returns_none(self, MockClient):
        client = MockClient.return_value
        client.autocomplete_recipient.return_value = {"results": []}

        result = usaspending_autocomplete("Totally Unknown Corp")
        assert result is None

    def test_empty_name_returns_none(self):
        assert usaspending_autocomplete("") is None
        assert usaspending_autocomplete("   ") is None


# ---------------------------------------------------------------------------
# usaspending_search
# ---------------------------------------------------------------------------


class TestUSAspendingSearch:
    @patch(f"{MODULE}.SyncUSAspendingClient")
    def test_success_with_results(self, MockClient):
        client = MockClient.return_value
        client.search_awards.return_value = {
            "results": [{"Award ID": "W911NF-20-1-0001", "Award Amount": 100000}]
        }

        result = usaspending_search("Acme", "ABC123", "UEI")

        assert result is not None
        # 5 type groups, each returning 1 result
        assert len(result) == 5
        client.close.assert_called_once()

    @patch(f"{MODULE}.SyncUSAspendingClient")
    def test_empty_results_returns_none(self, MockClient):
        client = MockClient.return_value
        client.search_awards.return_value = {"results": []}

        result = usaspending_search("Acme", "ABC123", "UEI")
        assert result is None


# ---------------------------------------------------------------------------
# lookup_company_federal_awards
# ---------------------------------------------------------------------------


class TestLookupCompanyFederalAwards:
    @patch(f"{MODULE}.usaspending_autocomplete")
    @patch(f"{MODULE}.usaspending_search")
    @patch(f"{MODULE}._is_sbir_award_type")
    def test_uei_path(self, mock_is_sbir, mock_search, mock_auto):
        mock_is_sbir.return_value = False
        mock_search.return_value = [
            {
                "Awarding Agency": "DOD",
                "Award Type": "Contract",
                "Award Amount": 500000,
                "Start Date": "2022-01-01",
                "Description": "R&D services",
                "CFDA Number": "",
            }
        ]

        result = lookup_company_federal_awards("Acme Corp", uei="ABC123")

        assert isinstance(result, FederalAwardSummary)
        assert result.total_awards == 1
        assert result.total_funding == 500000.0
        assert "DOD" in result.agencies
        # UEI path was used first
        mock_search.assert_called_once_with("Acme Corp", "ABC123", "UEI", rate_limiter=None)
        mock_auto.assert_not_called()

    @patch(f"{MODULE}.usaspending_autocomplete")
    @patch(f"{MODULE}.usaspending_search")
    @patch(f"{MODULE}._is_sbir_award_type")
    def test_name_fallback(self, mock_is_sbir, mock_search, mock_auto):
        mock_is_sbir.return_value = False
        # First call (UEI) returns None, second call (name) returns results
        mock_search.side_effect = [None, [
            {
                "Awarding Agency": "NASA",
                "Award Type": "Grant",
                "Award Amount": 100000,
                "Start Date": "2023-03-15",
                "Description": "Space stuff",
                "CFDA Number": "",
            }
        ]]

        result = lookup_company_federal_awards("Acme Corp", uei="ABC123")

        assert isinstance(result, FederalAwardSummary)
        assert result.total_awards == 1
        assert "NASA" in result.agencies

    @patch(f"{MODULE}.usaspending_autocomplete")
    @patch(f"{MODULE}.usaspending_search")
    @patch(f"{MODULE}._is_sbir_award_type")
    def test_sbir_non_sbir_separation(self, mock_is_sbir, mock_search, mock_auto):
        # First award is SBIR, second is not
        mock_is_sbir.side_effect = [True, False]
        mock_search.return_value = [
            {
                "Awarding Agency": "DOD",
                "Award Type": "Grant",
                "Award Amount": 150000,
                "Start Date": "2021-06-01",
                "Description": "SBIR Phase I",
                "CFDA Number": "12.900",
            },
            {
                "Awarding Agency": "DOD",
                "Award Type": "Contract",
                "Award Amount": 2000000,
                "Start Date": "2023-01-01",
                "Description": "Production contract",
                "CFDA Number": "",
            },
        ]

        result = lookup_company_federal_awards("Acme Corp", uei="ABC123")

        assert result.sbir_award_count == 1
        assert result.sbir_funding == 150000.0
        assert result.non_sbir_award_count == 1
        assert result.non_sbir_funding == 2000000.0

    def test_empty_company_returns_none(self):
        assert lookup_company_federal_awards("") is None


# ---------------------------------------------------------------------------
# lookup_usaspending_recipient
# ---------------------------------------------------------------------------


class TestLookupUSAspendingRecipient:
    @patch(f"{MODULE}.SyncUSAspendingClient")
    def test_two_step_lookup(self, MockClient):
        client = MockClient.return_value
        client.search_recipients.return_value = [
            {"id": "hash-abc-123", "name": "Acme Corp"}
        ]
        client.get_recipient_profile.return_value = {
            "name": "Acme Corp",
            "uei": "ABC123DEF456",
            "parent_name": None,
            "parent_uei": None,
            "location": {"state_code": "VA", "congressional_code": "11"},
            "business_types": ["Small Business"],
            "total_transaction_amount": 5000000,
            "total_transactions": 12,
        }

        result = lookup_usaspending_recipient("Acme Corp", uei="ABC123DEF456")

        assert isinstance(result, USARecipientProfile)
        assert result.recipient_id == "hash-abc-123"
        assert result.name == "Acme Corp"
        assert result.location_state == "VA"
        assert result.total_transactions == 12
        client.close.assert_called_once()

    @patch(f"{MODULE}.SyncUSAspendingClient")
    def test_no_recipient_match_returns_none(self, MockClient):
        client = MockClient.return_value
        client.search_recipients.return_value = []

        result = lookup_usaspending_recipient("Unknown Corp")
        assert result is None

    def test_empty_name_returns_none(self):
        assert lookup_usaspending_recipient("") is None


# ---------------------------------------------------------------------------
# lookup_sam_entity
# ---------------------------------------------------------------------------


class TestLookupSAMEntity:
    @patch.dict("os.environ", {"SAM_GOV_API_KEY": "test-key"})
    @patch(f"{MODULE}.SyncSAMGovClient")
    def test_uei_path(self, MockClient):
        client = MockClient.return_value
        client.get_entity_by_uei.return_value = {
            "entityRegistration": {
                "ueiSAM": "ABC123",
                "legalBusinessName": "Acme Corp",
                "cageCode": "1ABC2",
            },
            "coreData": {
                "physicalAddress": {"stateOrProvinceCode": "VA"},
                "businessTypes": {},
                "naicsCodeList": [{"naicsCode": "541511"}],
            },
        }

        result = lookup_sam_entity("Acme Corp", uei="ABC123")

        assert isinstance(result, SAMEntityRecord)
        assert result.uei == "ABC123"
        assert result.legal_business_name == "Acme Corp"
        assert "541511" in result.naics_codes
        client.close.assert_called_once()

    @patch.dict("os.environ", {"SAM_GOV_API_KEY": "test-key"})
    @patch(f"{MODULE}.SyncSAMGovClient")
    def test_cage_fallback(self, MockClient):
        client = MockClient.return_value
        client.get_entity_by_uei.return_value = None
        client.get_entity_by_cage.return_value = {
            "entityRegistration": {
                "ueiSAM": "XYZ789",
                "legalBusinessName": "Acme Corp",
                "cageCode": "1ABC2",
            },
            "coreData": {
                "physicalAddress": {},
                "businessTypes": {},
                "naicsCodeList": [],
            },
        }

        result = lookup_sam_entity("Acme Corp", cage="1ABC2")

        assert isinstance(result, SAMEntityRecord)
        assert result.uei == "XYZ789"
        client.get_entity_by_cage.assert_called_once_with("1ABC2")

    @patch.dict("os.environ", {"SAM_GOV_API_KEY": "test-key"})
    @patch(f"{MODULE}.SyncSAMGovClient")
    def test_name_search_fallback(self, MockClient):
        client = MockClient.return_value
        client.search_entities.return_value = [
            {
                "entityRegistration": {
                    "ueiSAM": "DEF456",
                    "legalBusinessName": "Acme Corp",
                },
                "coreData": {
                    "physicalAddress": {},
                    "businessTypes": {},
                    "naicsCodeList": [],
                },
            }
        ]

        result = lookup_sam_entity("Acme Corp")

        assert isinstance(result, SAMEntityRecord)
        assert result.uei == "DEF456"

    @patch.dict("os.environ", {}, clear=True)
    def test_no_api_key_returns_none(self):
        result = lookup_sam_entity("Acme Corp", uei="ABC123")
        assert result is None


# ---------------------------------------------------------------------------
# fetch_fpds_descriptions
# ---------------------------------------------------------------------------


class TestFetchFPDSDescriptions:
    @patch(f"{MODULE}.FPDSAtomClient")
    def test_success(self, MockClient):
        ctx = MockClient.return_value.__enter__.return_value
        ctx.get_descriptions.return_value = {
            "W911NF-20-1-0001": "Research on advanced materials"
        }

        result = fetch_fpds_descriptions(["W911NF-20-1-0001"])
        assert result == {"W911NF-20-1-0001": "Research on advanced materials"}

    def test_empty_list_returns_empty_dict(self):
        assert fetch_fpds_descriptions([]) == {}


# ---------------------------------------------------------------------------
# fetch_usaspending_contract_descriptions
# ---------------------------------------------------------------------------


class TestFetchUSAspendingContractDescriptions:
    @patch(f"{MODULE}.SyncUSAspendingClient")
    def test_success(self, MockClient):
        client = MockClient.return_value
        client.search_awards.return_value = {
            "results": [
                {
                    "Award ID": "W911NF-20-1-0001",
                    "Description": "Advanced R&D",
                    "Awarding Agency": "DOD",
                    "Award Type": "Contract",
                }
            ]
        }

        awards = [{"Contract": "W911NF-20-1-0001"}]
        result = fetch_usaspending_contract_descriptions(awards)

        assert "W911NF-20-1-0001" in result
        assert result["W911NF-20-1-0001"] == "Advanced R&D"

    @patch(f"{MODULE}.fetch_fpds_descriptions")
    @patch(f"{MODULE}.SyncUSAspendingClient")
    def test_fpds_fallback_on_failure(self, MockClient, mock_fpds):
        client = MockClient.return_value
        # Both USAspending methods fail
        client.search_awards.side_effect = RuntimeError("API error")
        client.search_transactions.side_effect = RuntimeError("API error")

        mock_fpds.return_value = {
            "W911NF-20-1-0001": "Fallback description from FPDS"
        }

        awards = [{"Contract": "W911NF-20-1-0001"}]
        result = fetch_usaspending_contract_descriptions(awards)

        assert "W911NF-20-1-0001" in result
        assert "Fallback" in result["W911NF-20-1-0001"]
        mock_fpds.assert_called_once()

    @patch(f"{MODULE}.SyncUSAspendingClient")
    def test_empty_awards_returns_empty_dict(self, MockClient):
        result = fetch_usaspending_contract_descriptions([])
        assert result == {}
