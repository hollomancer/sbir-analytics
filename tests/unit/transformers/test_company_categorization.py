"""Unit tests for company categorization transformer.

Tests contract-level classification and company-level aggregation logic
for Product/Service/Mixed/Uncertain categorization of SBIR companies.
"""

from __future__ import annotations

import pytest

from src.transformers.company_categorization import (
    aggregate_company_classification,
    classify_contract,
)


# ---------------------------------------------------------------------------
# Contract classification tests
# ---------------------------------------------------------------------------


class TestClassifyContractPSC:
    """Test PSC-based contract classification."""

    def test_numeric_psc_classified_as_product(self):
        contract = {
            "award_id": "T001",
            "psc": "1234",
            "contract_type": "FFP",
            "pricing": "FFP",
            "award_amount": 100000,
        }
        result = classify_contract(contract)
        assert result.classification == "Product"

    def test_alphabetic_psc_classified_as_service(self):
        contract = {
            "award_id": "T002",
            "psc": "R425",
            "contract_type": "",
            "pricing": "",
            "award_amount": 150000,
        }
        result = classify_contract(contract)
        assert result.classification == "Service"

    def test_rd_psc_a_prefix_classified_as_service(self):
        contract = {
            "award_id": "T003",
            "psc": "A123",
            "contract_type": "FFP",
            "pricing": "FFP",
            "award_amount": 200000,
        }
        result = classify_contract(contract)
        assert result.classification == "Service"
        assert "rd" in result.method.lower() or "service" in result.method.lower()

    def test_rd_psc_b_prefix_classified_as_service(self):
        contract = {
            "award_id": "T004",
            "psc": "B999",
            "contract_type": "FFP",
            "pricing": "FFP",
            "award_amount": 200000,
        }
        result = classify_contract(contract)
        assert result.classification == "Service"


class TestClassifyContractType:
    """Test contract type override rules."""

    def test_cpff_overrides_to_service(self):
        contract = {
            "award_id": "T010",
            "psc": "1234",  # Would be Product by PSC
            "contract_type": "CPFF",
            "pricing": "CPFF",
            "award_amount": 250000,
        }
        result = classify_contract(contract)
        assert result.classification == "Service"
        assert result.method == "contract_type_service"

    def test_tm_overrides_to_service(self):
        contract = {
            "award_id": "T011",
            "psc": "1234",
            "contract_type": "T&M",
            "pricing": "T&M",
            "award_amount": 100000,
        }
        result = classify_contract(contract)
        assert result.classification == "Service"

    def test_ffp_with_numeric_psc_is_product(self):
        contract = {
            "award_id": "T012",
            "psc": "5678",
            "contract_type": "FFP",
            "pricing": "FFP",
            "award_amount": 100000,
        }
        result = classify_contract(contract)
        assert result.classification == "Product"


class TestClassifyContractDescription:
    """Test description-based inference rules."""

    def test_prototype_keyword_product(self):
        contract = {
            "award_id": "T020",
            "psc": "",
            "contract_type": "FFP",
            "pricing": "FFP",
            "description": "Development of a prototype system",
            "award_amount": 100000,
        }
        result = classify_contract(contract)
        assert result.classification == "Product"

    def test_hardware_keyword_product(self):
        contract = {
            "award_id": "T021",
            "psc": "",
            "contract_type": "FFP",
            "pricing": "FFP",
            "description": "Custom hardware development for sensor",
            "award_amount": 100000,
        }
        result = classify_contract(contract)
        assert result.classification == "Product"

    def test_device_keyword_product(self):
        contract = {
            "award_id": "T022",
            "psc": "",
            "contract_type": "FFP",
            "pricing": "FFP",
            "description": "Medical device manufacturing",
            "award_amount": 100000,
        }
        result = classify_contract(contract)
        assert result.classification == "Product"


class TestClassifyContractSBIRPhase:
    """Test SBIR phase adjustment rules."""

    def test_sbir_phase_i_with_numeric_psc_keeps_product(self):
        contract = {
            "award_id": "T030",
            "psc": "1234",
            "contract_type": "",
            "pricing": "",
            "description": "SBIR Phase I research",
            "award_amount": 100000,
            "sbir_phase": "I",
        }
        result = classify_contract(contract)
        assert result.classification == "Product"

    def test_sbir_phase_i_with_service_psc_is_service(self):
        contract = {
            "award_id": "T031",
            "psc": "R425",
            "contract_type": "",
            "pricing": "",
            "description": "SBIR Phase I research",
            "award_amount": 150000,
            "sbir_phase": "I",
        }
        result = classify_contract(contract)
        assert result.classification == "Service"


class TestClassifyContractEdgeCases:
    """Test edge cases for contract classification."""

    def test_empty_contract_returns_classification(self):
        result = classify_contract({})
        assert result.classification in ("Product", "Service", "R&D")

    def test_none_psc_handled(self):
        contract = {
            "award_id": "T040",
            "psc": None,
            "contract_type": "FFP",
            "pricing": "FFP",
            "award_amount": 100000,
        }
        result = classify_contract(contract)
        assert result.classification in ("Product", "Service", "R&D")

    def test_confidence_is_positive(self):
        contract = {
            "award_id": "T041",
            "psc": "1234",
            "contract_type": "FFP",
            "pricing": "FFP",
            "award_amount": 50000,
        }
        result = classify_contract(contract)
        assert result.confidence > 0


# ---------------------------------------------------------------------------
# Company aggregation tests
# ---------------------------------------------------------------------------


class TestAggregateCompanyClassification:
    """Test company-level classification aggregation."""

    def test_product_leaning_above_51_percent(self):
        contracts = [
            {"award_id": "C1", "classification": "Product", "award_amount": 300000, "psc": "1234"},
            {"award_id": "C2", "classification": "Product", "award_amount": 200000, "psc": "5678"},
            {"award_id": "C3", "classification": "Service", "award_amount": 100000, "psc": "R425"},
        ]
        result = aggregate_company_classification(contracts, "UEI001", "Test Corp")
        assert result.classification == "Product-leaning"
        assert result.product_pct >= 51

    def test_service_leaning_above_51_percent(self):
        contracts = [
            {"award_id": "C1", "classification": "Service", "award_amount": 300000, "psc": "R425"},
            {"award_id": "C2", "classification": "Service", "award_amount": 200000, "psc": "A123"},
            {"award_id": "C3", "classification": "Product", "award_amount": 100000, "psc": "1234"},
        ]
        result = aggregate_company_classification(contracts, "UEI002", "Service Corp")
        assert result.classification == "Service-leaning"
        assert result.service_pct >= 51

    def test_mixed_when_neither_threshold_met(self):
        contracts = [
            {"award_id": "C1", "classification": "Product", "award_amount": 250000, "psc": "1234"},
            {"award_id": "C2", "classification": "Service", "award_amount": 250000, "psc": "R425"},
        ]
        result = aggregate_company_classification(contracts, "UEI003", "Mixed Corp")
        assert result.classification == "Mixed"

    def test_uncertain_with_single_award(self):
        contracts = [
            {"award_id": "C1", "classification": "Product", "award_amount": 100000, "psc": "1234"},
        ]
        result = aggregate_company_classification(contracts, "UEI004", "Small Corp")
        assert result.classification == "Uncertain"
        assert result.confidence == "Low"

    def test_psc_diversity_override_to_mixed(self):
        # >6 PSC families should trigger Mixed override
        contracts = [
            {"award_id": f"C{i}", "classification": "Product", "award_amount": 100000, "psc": f"{chr(65 + i)}123"}
            for i in range(8)  # 8 different PSC families (A-H)
        ]
        result = aggregate_company_classification(contracts, "UEI005", "Diverse Corp")
        assert result.classification == "Mixed"
        assert result.override_reason == "high_psc_diversity"


class TestAggregateConfidenceLevels:
    """Test confidence level assignment."""

    def test_low_confidence_two_or_fewer_awards(self):
        contracts = [
            {"award_id": "C1", "classification": "Product", "award_amount": 100000, "psc": "1234"},
            {"award_id": "C2", "classification": "Product", "award_amount": 100000, "psc": "5678"},
        ]
        result = aggregate_company_classification(contracts, "UEI010", "Low Co")
        assert result.confidence == "Low"

    def test_medium_confidence_three_to_five_awards(self):
        contracts = [
            {"award_id": f"C{i}", "classification": "Product", "award_amount": 100000, "psc": "1234"}
            for i in range(4)
        ]
        result = aggregate_company_classification(contracts, "UEI011", "Med Co")
        assert result.confidence == "Medium"

    def test_high_confidence_more_than_five_awards(self):
        contracts = [
            {"award_id": f"C{i}", "classification": "Product", "award_amount": 100000, "psc": "1234"}
            for i in range(7)
        ]
        result = aggregate_company_classification(contracts, "UEI012", "High Co")
        assert result.confidence == "High"


class TestAggregateOutputFields:
    """Test that aggregation output fields are populated correctly."""

    def test_total_dollars_calculated(self):
        contracts = [
            {"award_id": "C1", "classification": "Product", "award_amount": 100000, "psc": "1234"},
            {"award_id": "C2", "classification": "Service", "award_amount": 200000, "psc": "R425"},
            {"award_id": "C3", "classification": "Product", "award_amount": 300000, "psc": "5678"},
        ]
        result = aggregate_company_classification(contracts, "UEI020", "Test Co")
        assert result.total_dollars == 600000

    def test_product_and_service_dollars_sum_to_total(self):
        contracts = [
            {"award_id": "C1", "classification": "Product", "award_amount": 100000, "psc": "1234"},
            {"award_id": "C2", "classification": "Service", "award_amount": 200000, "psc": "R425"},
        ]
        result = aggregate_company_classification(contracts, "UEI021", "Test Co")
        assert result.product_dollars + result.service_dollars == pytest.approx(
            result.total_dollars, rel=0.01
        )

    def test_product_pct_plus_service_pct_equals_100(self):
        contracts = [
            {"award_id": "C1", "classification": "Product", "award_amount": 300000, "psc": "1234"},
            {"award_id": "C2", "classification": "Service", "award_amount": 200000, "psc": "R425"},
            {"award_id": "C3", "classification": "Product", "award_amount": 100000, "psc": "5678"},
        ]
        result = aggregate_company_classification(contracts, "UEI022", "Test Co")
        assert result.product_pct + result.service_pct == pytest.approx(100.0, abs=1.0)

    def test_award_count_matches_input(self):
        contracts = [
            {"award_id": f"C{i}", "classification": "Product", "award_amount": 100000, "psc": "1234"}
            for i in range(5)
        ]
        result = aggregate_company_classification(contracts, "UEI023", "Test Co")
        assert result.award_count == 5

    def test_company_identifiers_stored(self):
        result = aggregate_company_classification(
            [
                {"award_id": "C1", "classification": "Product", "award_amount": 100000, "psc": "1234"},
                {"award_id": "C2", "classification": "Product", "award_amount": 100000, "psc": "5678"},
                {"award_id": "C3", "classification": "Product", "award_amount": 100000, "psc": "9012"},
            ],
            "MY_UEI_123",
            "Acme Corp",
        )
        assert result.company_uei == "MY_UEI_123"
        assert result.company_name == "Acme Corp"

    def test_empty_contracts_returns_uncertain(self):
        result = aggregate_company_classification([], "UEI_EMPTY", "Empty Co")
        assert result.classification == "Uncertain"
        assert result.confidence == "Low"
        assert result.award_count == 0
