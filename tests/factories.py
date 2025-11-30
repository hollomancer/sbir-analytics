"""Factory functions for creating test data objects.

This module provides factory functions for creating Award, RawAward, and other
test data objects with sensible defaults, reducing boilerplate in tests.
"""

from datetime import UTC, date, datetime
from typing import Any

from src.models.award import Award, RawAward
from src.models.cet_models import (
    CETAssessment,
    CETClassification,
    ClassificationLevel,
    CompanyCETProfile,
    EvidenceStatement,
)


class AwardFactory:
    """Factory for creating Award instances for testing."""

    @staticmethod
    def create(**kwargs: Any) -> Award:
        """Create an Award instance with default values."""
        defaults = {
            "award_id": "TEST-AWARD-001",
            "company_name": "Test Company",
            "award_amount": 100000.0,
            "award_date": date(2023, 1, 1),
            "program": "SBIR",
            "phase": "I",
            "agency": "DOD",
            "branch": "Army",
            "contract": "C-2023-001",
            "abstract": "Test abstract for award",
            "award_title": "Test Award Title",
            "company_uei": "UEI123456789",
            "company_duns": "123456789",
            "company_address": "123 Test St",
            "company_city": "Test City",
            "company_state": "CA",
            "company_zip": "90210",
            "number_of_employees": 10,
            "is_hubzone": False,
            "is_woman_owned": False,
            "is_socially_disadvantaged": False,
        }
        defaults.update(kwargs)
        return Award(**defaults)

    @staticmethod
    def create_batch(count: int, **kwargs: Any) -> list[Award]:
        """Create multiple Award instances with sequential IDs."""
        awards = []
        for i in range(1, count + 1):
            overrides = kwargs.copy()
            if "award_id" not in overrides:
                overrides["award_id"] = f"TEST-AWARD-{i:03d}"
            if "company_name" not in overrides:
                overrides["company_name"] = f"Test Company {i}"
            awards.append(AwardFactory.create(**overrides))
        return awards


class RawAwardFactory:
    """Factory for creating RawAward instances for testing."""

    @staticmethod
    def create(**kwargs: Any) -> RawAward:
        """Create a RawAward instance with default values."""
        defaults = {
            "award_id": "TEST-AWARD-001",
            "company_name": "Test Company",
            "award_amount": "100000.0",
            "award_date": "2023-01-01",
            "program": "SBIR",
            "phase": "Phase I",
            "agency": "DOD",
            "branch": "Army",
            "contract": "C-2023-001",
            "abstract": "Test abstract for raw award",
            "award_title": "Test Award Title",
            "company_uei": "UEI123456789",
            "company_duns": "123456789",
            "company_address": "123 Test St",
            "company_city": "Test City",
            "company_state": "CA",
            "company_zip": "90210",
            "number_of_employees": "10",
            "is_hubzone": False,
            "is_woman_owned": False,
            "is_socially_disadvantaged": False,
        }
        defaults.update(kwargs)
        return RawAward(**defaults)

    @staticmethod
    def create_batch(count: int, **kwargs: Any) -> list[RawAward]:
        """Create multiple RawAward instances with sequential IDs."""
        awards = []
        for i in range(1, count + 1):
            overrides = kwargs.copy()
            if "award_id" not in overrides:
                overrides["award_id"] = f"TEST-AWARD-{i:03d}"
            if "company_name" not in overrides:
                overrides["company_name"] = f"Test Company {i}"
            awards.append(RawAwardFactory.create(**overrides))
        return awards


class EvidenceStatementFactory:
    """Factory for EvidenceStatement model."""

    @staticmethod
    def create(**kwargs: Any) -> EvidenceStatement:
        """Create an EvidenceStatement instance with sensible defaults."""
        defaults = {
            "excerpt": "This project uses machine learning for pattern recognition.",
            "source_location": "abstract",
            "rationale_tag": "Contains: machine learning",
        }
        defaults.update(kwargs)
        return EvidenceStatement(**defaults)


class CETClassificationFactory:
    """Factory for CETClassification model."""

    @staticmethod
    def create(**kwargs: Any) -> CETClassification:
        """Create a CETClassification instance with sensible defaults."""
        defaults = {
            "cet_id": "artificial_intelligence",
            "cet_name": "Artificial Intelligence",
            "score": 85.0,
            "classification": ClassificationLevel.HIGH,
            "primary": True,
            "evidence": [],
            "classified_at": datetime.now(UTC).isoformat(),
            "taxonomy_version": "NSTC-2025Q1",
        }
        defaults.update(kwargs)

        # Auto-adjust classification level if score is provided but level isn't
        if "score" in kwargs and "classification" not in kwargs:
            score = kwargs["score"]
            if score >= 70:
                defaults["classification"] = ClassificationLevel.HIGH
            elif score >= 40:
                defaults["classification"] = ClassificationLevel.MEDIUM
            else:
                defaults["classification"] = ClassificationLevel.LOW

        return CETClassification(**defaults)


class CETAssessmentFactory:
    """Factory for CETAssessment model."""

    @staticmethod
    def create(**kwargs: Any) -> CETAssessment:
        """Create a CETAssessment instance with sensible defaults."""
        defaults = {
            "entity_id": "award_123",
            "entity_type": "award",
            "primary_cet": CETClassificationFactory.create(primary=True),
            "supporting_cets": [],
            "classified_at": datetime.now(UTC),
            "taxonomy_version": "NSTC-2025Q1",
            "model_version": "v1.0.0",
        }
        defaults.update(kwargs)
        return CETAssessment(**defaults)


class CompanyCETProfileFactory:
    """Factory for CompanyCETProfile model."""

    @staticmethod
    def create(**kwargs: Any) -> CompanyCETProfile:
        """Create a CompanyCETProfile instance with sensible defaults."""
        defaults = {
            "company_id": "company_123",
            "dominant_cet_id": "artificial_intelligence",
            "award_count": 10,
            "total_funding": 1000000.0,
            "avg_score": 80.0,
            "specialization_score": 0.75,
            "dominant_phase": "II",
            "first_award_date": datetime(2020, 1, 1),
            "last_award_date": datetime(2023, 1, 1),
            "cet_areas": ["artificial_intelligence", "autonomous_systems"],
        }
        defaults.update(kwargs)
        return CompanyCETProfile(**defaults)


# DataFrame Builders
# ==================


class DataFrameBuilder:
    """Fluent builder for test DataFrames."""

    @staticmethod
    def awards(count: int = 5) -> "AwardDataFrameBuilder":
        """Create an award DataFrame builder."""
        return AwardDataFrameBuilder(count)

    @staticmethod
    def contracts(count: int = 5) -> "ContractDataFrameBuilder":
        """Create a contract DataFrame builder."""
        return ContractDataFrameBuilder(count)

    @staticmethod
    def companies(count: int = 5) -> "CompanyDataFrameBuilder":
        """Create a company DataFrame builder."""
        return CompanyDataFrameBuilder(count)

    @staticmethod
    def patents(count: int = 5) -> "PatentDataFrameBuilder":
        """Create a patent DataFrame builder."""
        return PatentDataFrameBuilder(count)


class AwardDataFrameBuilder:
    """Builder for award DataFrames."""

    def __init__(self, count: int):
        self.count = count
        self.overrides = {}
        self.custom_rows = []

    def with_agency(self, agency: str) -> "AwardDataFrameBuilder":
        self.overrides["agency"] = agency
        return self

    def with_phase(self, phase: str) -> "AwardDataFrameBuilder":
        self.overrides["phase"] = phase
        return self

    def with_amount_range(self, min_amount: float, max_amount: float) -> "AwardDataFrameBuilder":
        self.overrides["amount_range"] = (min_amount, max_amount)
        return self

    def with_date_range(self, start_date: date, end_date: date) -> "AwardDataFrameBuilder":
        self.overrides["date_range"] = (start_date, end_date)
        return self

    def with_naics(self, naics: str) -> "AwardDataFrameBuilder":
        self.overrides["naics_code"] = naics
        return self

    def with_custom_row(self, **kwargs) -> "AwardDataFrameBuilder":
        self.custom_rows.append(kwargs)
        return self

    def build(self):
        """Build the DataFrame."""
        import pandas as pd
        import random
        from datetime import timedelta

        awards = []
        for i in range(1, self.count + 1):
            award_data = {
                "award_id": f"TEST-AWARD-{i:03d}",
                "company_name": f"Test Company {i}",
                "award_amount": 100000.0,
                "award_date": date(2023, 1, 1),
                "program": "SBIR",
                "phase": "I",
                "agency": "DOD",
                "branch": "Army",
                "contract": f"C-2023-{i:03d}",
                "abstract": f"Test abstract for award {i}",
                "award_title": f"Test Award Title {i}",
                "company_uei": f"UEI{i:09d}",
                "company_duns": f"{i:09d}",
                "company_address": f"{i} Test St",
                "company_city": "Test City",
                "company_state": "CA",
                "company_zip": "90210",
                "number_of_employees": 10,
            }

            for key, value in self.overrides.items():
                if key == "amount_range":
                    min_amt, max_amt = value
                    award_data["award_amount"] = random.uniform(min_amt, max_amt)
                elif key == "date_range":
                    start, end = value
                    days_diff = (end - start).days
                    random_days = random.randint(0, days_diff)
                    award_data["award_date"] = start + timedelta(days=random_days)
                else:
                    award_data[key] = value

            awards.append(award_data)

        for custom in self.custom_rows:
            award_data = awards[0].copy()
            award_data.update(custom)
            awards.append(award_data)

        return pd.DataFrame(awards)


class ContractDataFrameBuilder:
    """Builder for contract DataFrames."""

    def __init__(self, count: int):
        self.count = count
        self.overrides = {}

    def with_agency(self, agency: str) -> "ContractDataFrameBuilder":
        self.overrides["awarding_agency_name"] = agency
        return self

    def with_recipient(self, name: str, uei: str) -> "ContractDataFrameBuilder":
        self.overrides["recipient_name"] = name
        self.overrides["recipient_uei"] = uei
        return self

    def with_date_range(self, start_date: date, end_date: date) -> "ContractDataFrameBuilder":
        self.overrides["date_range"] = (start_date, end_date)
        return self

    def build(self):
        """Build the DataFrame."""
        import pandas as pd
        import random
        from datetime import timedelta

        contracts = []
        for i in range(1, self.count + 1):
            contract_data = {
                "contract_id": f"CONTRACT-{i:03d}",
                "piid": f"PIID-{i:03d}",
                "recipient_name": f"Test Company {i}",
                "recipient_uei": f"UEI{i:09d}",
                "awarding_agency_name": "DOD",
                "federal_action_obligation": 500000.0,
                "action_date": date(2023, 8, 1),
                "period_of_performance_start_date": date(2023, 8, 1),
                "period_of_performance_current_end_date": date(2024, 8, 1),
            }

            for key, value in self.overrides.items():
                if key == "date_range":
                    start, end = value
                    days_diff = (end - start).days
                    random_days = random.randint(0, days_diff)
                    contract_data["action_date"] = start + timedelta(days=random_days)
                else:
                    contract_data[key] = value

            contracts.append(contract_data)

        return pd.DataFrame(contracts)


class CompanyDataFrameBuilder:
    """Builder for company DataFrames."""

    def __init__(self, count: int):
        self.count = count
        self.overrides = {}

    def with_state(self, state: str) -> "CompanyDataFrameBuilder":
        self.overrides["state"] = state
        return self

    def with_size_range(self, min_employees: int, max_employees: int) -> "CompanyDataFrameBuilder":
        self.overrides["size_range"] = (min_employees, max_employees)
        return self

    def build(self):
        """Build the DataFrame."""
        import pandas as pd
        import random

        companies = []
        for i in range(1, self.count + 1):
            company_data = {
                "name": f"Test Company {i}",
                "uei": f"UEI{i:09d}",
                "duns": f"{i:09d}",
                "address": f"{i} Test St",
                "city": "Test City",
                "state": "CA",
                "zip": "90210",
                "number_of_employees": 10,
            }

            for key, value in self.overrides.items():
                if key == "size_range":
                    min_emp, max_emp = value
                    company_data["number_of_employees"] = random.randint(min_emp, max_emp)
                else:
                    company_data[key] = value

            companies.append(company_data)

        return pd.DataFrame(companies)


class PatentDataFrameBuilder:
    """Builder for patent DataFrames."""

    def __init__(self, count: int):
        self.count = count
        self.overrides = {}

    def with_grant_date_range(self, start_date: date, end_date: date) -> "PatentDataFrameBuilder":
        self.overrides["date_range"] = (start_date, end_date)
        return self

    def build(self):
        """Build the DataFrame."""
        import pandas as pd
        import random
        from datetime import timedelta

        patents = []
        for i in range(1, self.count + 1):
            patent_data = {
                "grant_doc_num": f"{5858000 + i}",
                "title": f"Test Patent {i}",
                "abstract": f"Test patent abstract {i}",
                "grant_date": date(2023, 1, 1),
                "assignee_name": f"Test Company {i}",
            }

            for key, value in self.overrides.items():
                if key == "date_range":
                    start, end = value
                    days_diff = (end - start).days
                    random_days = random.randint(0, days_diff)
                    patent_data["grant_date"] = start + timedelta(days=random_days)
                else:
                    patent_data[key] = value

            patents.append(patent_data)

        return pd.DataFrame(patents)


# =============================================================================
# Fiscal Model Factories
# =============================================================================


class EconomicShockFactory:
    """Factory for EconomicShock model."""

    @staticmethod
    def create(**kwargs: Any):
        """Create an EconomicShock instance with sensible defaults."""
        from decimal import Decimal
        from src.models.fiscal_models import EconomicShock

        defaults = {
            "state": "CA",
            "bea_sector": "54",
            "fiscal_year": 2022,
            "shock_amount": Decimal("500000"),
            "award_ids": ["AWARD-001"],
            "confidence": 0.9,
            "naics_coverage_rate": 0.85,
            "geographic_resolution_rate": 0.95,
            "base_year": 2020,
        }
        defaults.update(kwargs)
        return EconomicShock(**defaults)


class FiscalReturnSummaryFactory:
    """Factory for FiscalReturnSummary model."""

    @staticmethod
    def create(**kwargs: Any):
        """Create a FiscalReturnSummary instance with sensible defaults."""
        from decimal import Decimal
        from src.models.fiscal_models import FiscalReturnSummary

        defaults = {
            "analysis_id": "ANALYSIS-001",
            "base_year": 2020,
            "methodology_version": "v2.1",
            "total_sbir_investment": Decimal("10000000"),
            "total_tax_receipts": Decimal("15000000"),
            "net_fiscal_return": Decimal("5000000"),
            "roi_ratio": 1.5,
            "net_present_value": Decimal("4500000"),
            "benefit_cost_ratio": 1.5,
            "confidence_interval_low": Decimal("14000000"),
            "confidence_interval_high": Decimal("16000000"),
            "quality_score": 0.85,
        }
        defaults.update(kwargs)
        return FiscalReturnSummary(**defaults)


class NAICSMappingFactory:
    """Factory for NAICSMapping model."""

    @staticmethod
    def create(**kwargs: Any):
        """Create a NAICSMapping instance with sensible defaults."""
        from src.models.fiscal_models import NAICSMapping

        defaults = {
            "award_id": "AWARD-001",
            "naics_code": "541715",
            "bea_sector_code": "54",
            "bea_sector_name": "Professional Services",
            "crosswalk_version": "2022",
            "naics_source": "usaspending",
            "naics_confidence": 0.95,
            "mapping_confidence": 0.90,
        }
        defaults.update(kwargs)
        return NAICSMapping(**defaults)
