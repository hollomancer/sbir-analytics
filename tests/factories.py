"""Factory functions for creating test data objects.

This module provides factory functions for creating Award, RawAward, and other
test data objects with sensible defaults, reducing boilerplate in tests.
"""

from datetime import date
from typing import Any

from src.models.award import Award, RawAward


class AwardFactory:
    """Factory for creating Award instances for testing."""

    @staticmethod
    def create(**kwargs: Any) -> Award:
        """Create an Award instance with default values.
        
        Args:
            **kwargs: Override default values with custom values.
            
        Returns:
            Award instance with merged defaults and overrides.
        """
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
        """Create multiple Award instances with sequential IDs.
        
        Args:
            count: Number of awards to create.
            **kwargs: Override default values (applied to all awards).
            
        Returns:
            List of Award instances.
        """
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
        """Create a RawAward instance with default values.
        
        Args:
            **kwargs: Override default values with custom values.
            
        Returns:
            RawAward instance with merged defaults and overrides.
        """
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
        """Create multiple RawAward instances with sequential IDs.
        
        Args:
            count: Number of raw awards to create.
            **kwargs: Override default values (applied to all awards).
            
        Returns:
            List of RawAward instances.
        """
        awards = []
        for i in range(1, count + 1):
            overrides = kwargs.copy()
            if "award_id" not in overrides:
                overrides["award_id"] = f"TEST-AWARD-{i:03d}"
            if "company_name" not in overrides:
                overrides["company_name"] = f"Test Company {i}"
            awards.append(RawAwardFactory.create(**overrides))
        return awards
