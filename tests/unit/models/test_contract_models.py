"""Tests for contract models."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError


pytestmark = pytest.mark.fast

from src.models.contract_models import (
    CompetitionType,
    ContractDescription,
    ContractParty,
    ContractPeriod,
    ContractStatus,
    ContractValue,
    VendorMatch,
)


pytestmark = pytest.mark.fast



class TestContractEnums:
    """Tests for contract enumeration types."""

    def test_competition_type_values(self):
        """Test CompetitionType enum values."""
        assert CompetitionType.SOLE_SOURCE == "sole_source"
        assert CompetitionType.LIMITED == "limited"
        assert CompetitionType.FULL_AND_OPEN == "full_and_open"
        assert CompetitionType.SET_ASIDE == "set_aside"
        assert CompetitionType.OTHER == "other"

    def test_contract_status_values(self):
        """Test ContractStatus enum values."""
        assert ContractStatus.ACTIVE == "active"
        assert ContractStatus.COMPLETED == "completed"
        assert ContractStatus.TERMINATED == "terminated"
        assert ContractStatus.CANCELLED == "cancelled"
        assert ContractStatus.PENDING == "pending"


class TestVendorMatchModel:
    """Tests for VendorMatch model."""

    def test_valid_vendor_match(self):
        """Test creating a valid vendor match."""
        match = VendorMatch(
            vendor_id="VENDOR-123",
            method="uei",
            score=0.95,
            matched_name="Acme Corporation",
            matched_uei="ABC123DEF456",  # pragma: allowlist secret
            matched_cage="1A2B3",
            matched_duns="123456789",
            metadata={"source": "sam_gov"},
        )
        assert match.vendor_id == "VENDOR-123"
        assert match.method == "uei"
        assert match.score == 0.95

    def test_vendor_match_minimal(self):
        """Test vendor match with only required field."""
        match = VendorMatch(method="cage")
        assert match.method == "cage"
        assert match.vendor_id is None
        assert match.score == 0.0
        assert match.metadata == {}

    def test_method_validator_accepts_valid(self):
        """Test method validator accepts valid methods."""
        valid_methods = ["uei", "cage", "duns", "name_fuzzy", "address_match", "manual"]
        for method in valid_methods:
            match = VendorMatch(method=method)
            assert match.method == method

    def test_method_validator_rejects_invalid(self):
        """Test method validator rejects invalid methods."""
        with pytest.raises(ValidationError) as exc_info:
            VendorMatch(method="invalid_method")
        assert "method must be one of" in str(exc_info.value)

    def test_score_constraints(self):
        """Test score field has 0-1 constraints."""
        # Valid bounds
        VendorMatch(method="uei", score=0.0)
        VendorMatch(method="uei", score=1.0)

        # Invalid bounds
        with pytest.raises(ValidationError):
            VendorMatch(method="uei", score=-0.1)
        with pytest.raises(ValidationError):
            VendorMatch(method="uei", score=1.5)


class TestContractPartyModel:
    """Tests for ContractParty model."""

    def test_valid_contract_party(self):
        """Test creating a valid contract party."""
        party = ContractParty(
            name="Acme Corp",
            uei="ABC123DEF456",
            cage_code="1A2B3",
            duns_number="123456789",
            address="123 Main St",
            city="Boston",
            state="MA",
            zip_code="02101",
            country="USA",
        )
        assert party.name == "Acme Corp"
        assert party.uei == "ABC123DEF456"
        assert party.cage_code == "1A2B3"

    def test_contract_party_minimal(self):
        """Test contract party with minimal fields."""
        party = ContractParty()
        assert party.name is None
        assert party.uei is None
        assert party.cage_code is None

    def test_contract_party_partial(self):
        """Test contract party with some fields."""
        party = ContractParty(
            name="Test Vendor",
            city="New York",
            state="NY",
        )
        assert party.name == "Test Vendor"
        assert party.city == "New York"
        assert party.state == "NY"
        assert party.uei is None


class TestContractValueModel:
    """Tests for ContractValue model."""

    def test_valid_contract_value(self):
        """Test creating a valid contract value."""
        value = ContractValue(
            obligated_amount=500000.0,
            current_value=750000.0,
            potential_value=1000000.0,
            base_and_all_options_value=1500000.0,
            currency="USD",
        )
        assert value.obligated_amount == 500000.0
        assert value.current_value == 750000.0
        assert value.currency == "USD"

    def test_contract_value_defaults(self):
        """Test contract value with default currency."""
        value = ContractValue()
        assert value.currency == "USD"
        assert value.obligated_amount is None

    def test_contract_value_non_negative_constraints(self):
        """Test contract value fields must be non-negative."""
        # Valid: zero and positive
        ContractValue(obligated_amount=0.0)
        ContractValue(current_value=100000.0)

        # Invalid: negative
        with pytest.raises(ValidationError):
            ContractValue(obligated_amount=-1000.0)
        with pytest.raises(ValidationError):
            ContractValue(current_value=-500.0)

    def test_contract_value_other_currency(self):
        """Test contract value with non-USD currency."""
        value = ContractValue(
            obligated_amount=1000000.0,
            currency="EUR",
        )
        assert value.currency == "EUR"


class TestContractPeriodModel:
    """Tests for ContractPeriod model."""

    def test_valid_contract_period(self):
        """Test creating a valid contract period."""
        period = ContractPeriod(
            signed_date=date(2023, 1, 1),
            effective_date=date(2023, 1, 15),
            current_end_date=date(2024, 1, 14),
            ultimate_completion_date=date(2025, 1, 14),
            last_date_to_order=date(2024, 12, 1),
        )
        assert period.signed_date == date(2023, 1, 1)
        assert period.effective_date == date(2023, 1, 15)
        assert period.current_end_date == date(2024, 1, 14)

    def test_contract_period_minimal(self):
        """Test contract period with no dates."""
        period = ContractPeriod()
        assert period.signed_date is None
        assert period.effective_date is None
        assert period.current_end_date is None

    def test_date_validator_parses_iso_strings(self):
        """Test date validator parses ISO format strings."""
        period = ContractPeriod(
            signed_date="2023-06-15",
            effective_date="2023-07-01",
        )
        assert period.signed_date == date(2023, 6, 15)
        assert period.effective_date == date(2023, 7, 1)

    def test_date_validator_accepts_date_objects(self):
        """Test date validator accepts date objects."""
        period = ContractPeriod(
            signed_date=date(2023, 1, 1),
            effective_date=date(2023, 2, 1),
        )
        assert period.signed_date == date(2023, 1, 1)
        assert period.effective_date == date(2023, 2, 1)

    def test_date_validator_converts_datetime(self):
        """Test date validator converts datetime to date."""
        period = ContractPeriod(
            signed_date=datetime(2023, 1, 1, 10, 30),
        )
        assert period.signed_date == date(2023, 1, 1)

    def test_date_validator_rejects_invalid_format(self):
        """Test date validator rejects invalid date formats."""
        with pytest.raises(ValidationError) as exc_info:
            ContractPeriod(signed_date="invalid-date")
        assert "Dates must be ISO-formatted strings or date objects" in str(exc_info.value)

    def test_contract_period_all_date_fields(self):
        """Test contract period with all date fields."""
        period = ContractPeriod(
            signed_date="2022-01-01",
            effective_date="2022-02-01",
            current_end_date="2023-01-31",
            ultimate_completion_date="2024-01-31",
            last_date_to_order="2023-12-01",
        )
        assert all(
            [
                period.signed_date,
                period.effective_date,
                period.current_end_date,
                period.ultimate_completion_date,
                period.last_date_to_order,
            ]
        )


class TestContractDescriptionModel:
    """Tests for ContractDescription model."""

    def test_valid_contract_description(self):
        """Test creating a valid contract description."""
        desc = ContractDescription(
            description="Advanced R&D services",
            naics_code="541715",
            naics_description="R&D in Physical, Engineering, and Life Sciences",
            product_or_service_code="R425",
            product_or_service_description="R&D - Defense Systems",
            principal_naics_code="541715",
        )
        assert desc.description == "Advanced R&D services"
        assert desc.naics_code == "541715"
        assert desc.product_or_service_code == "R425"

    def test_contract_description_minimal(self):
        """Test contract description with no fields."""
        desc = ContractDescription()
        assert desc.description is None
        assert desc.naics_code is None
        assert desc.product_or_service_code is None

    def test_contract_description_partial(self):
        """Test contract description with some fields."""
        desc = ContractDescription(
            naics_code="541330",
            naics_description="Engineering Services",
        )
        assert desc.naics_code == "541330"
        assert desc.naics_description == "Engineering Services"
        assert desc.description is None


class TestFederalContractModel:
    """Tests for FederalContract model (basic structure tests)."""

    def test_federal_contract_requires_identifiers(self):
        """Test FederalContract requires contract_id and vendor."""
        # Should work with minimal required fields
        from src.models.contract_models import FederalContract

        contract = FederalContract(
            contract_id="CONTRACT-001",
            vendor=ContractParty(name="Test Vendor"),
        )
        assert contract.contract_id == "CONTRACT-001"
        assert contract.vendor.name == "Test Vendor"

    def test_federal_contract_with_enums(self):
        """Test FederalContract with status and competition type."""
        from src.models.contract_models import FederalContract

        contract = FederalContract(
            contract_id="CONTRACT-002",
            vendor=ContractParty(name="Vendor Inc"),
            status=ContractStatus.COMPLETED,
            competition_type=CompetitionType.SOLE_SOURCE,
        )
        assert contract.status == ContractStatus.COMPLETED
        assert contract.competition_type == CompetitionType.SOLE_SOURCE

    def test_federal_contract_default_status(self):
        """Test FederalContract has default status of ACTIVE."""
        from src.models.contract_models import FederalContract

        contract = FederalContract(
            contract_id="CONTRACT-003",
            vendor=ContractParty(name="Vendor"),
        )
        assert contract.status == ContractStatus.ACTIVE
