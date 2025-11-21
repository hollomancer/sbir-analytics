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
