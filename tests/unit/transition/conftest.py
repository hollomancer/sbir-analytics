"""Shared fixtures for transition detection tests."""

# Import shared fixtures for pytest discovery
from tests.conftest_shared import (  # noqa: F401
    default_config,
    mock_evidence_generator,
    mock_scorer,
    mock_vendor_resolver,
    sample_award,
    sample_contract,
)
