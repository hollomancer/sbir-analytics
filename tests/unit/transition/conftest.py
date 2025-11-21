"""Shared fixtures for transition detection tests."""

# Import shared fixtures
from tests.conftest_shared import (
    default_config,
    default_transition_config,
    mock_evidence_generator,
    mock_scorer,
    mock_vendor_resolver,
    old_award,
    recent_award,
    sample_award,
    sample_contract,
    sample_contracts_df,
)


# Re-export for pytest discovery
__all__ = [
    "default_transition_config",
    "mock_vendor_resolver",
    "mock_scorer",
    "mock_evidence_generator",
    "sample_award",
    "sample_contract",
    "sample_contracts_df",
    "recent_award",
    "old_award",
    "default_config",
]
