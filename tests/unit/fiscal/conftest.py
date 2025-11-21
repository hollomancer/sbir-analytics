"""Shared fixtures for fiscal analysis tests."""

# Import shared fixtures
from tests.conftest_shared import (
    sample_discount_rate,
    sample_fiscal_awards_df,
    sample_fiscal_impacts_df,
    sample_fiscal_summary,
    sample_sbir_investment,
    sample_tax_parameters,
)


# Re-export for pytest discovery
__all__ = [
    "sample_fiscal_awards_df",
    "sample_fiscal_impacts_df",
    "sample_tax_parameters",
    "sample_sbir_investment",
    "sample_discount_rate",
    "sample_fiscal_summary",
]
