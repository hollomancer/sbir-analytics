"""Test utilities for SBIR ETL pipeline.

This package provides:
- Consolidated fixtures and data generators (fixtures.py)
- Configuration mocking utilities (config_mocks.py)
- Exception testing helpers (exception_helpers.py)
- Shared mocks and test helpers
"""

from .config_mocks import (
    create_mock_enrichment_refresh_config,
    create_mock_neo4j_config,
    create_mock_pipeline_config,
    create_mock_usaspending_config,
)
from .exception_helpers import (
    assert_exception_details,
    assert_exception_serialization,
    assert_exception_structure,
    assert_non_retryable_exception,
    assert_raises_with_context,
    assert_retryable_exception,
    create_test_exception,
)
from .fixtures import (
    create_sample_award_data,
    create_sample_award_dict,
    create_sample_cet_area,
    create_sample_cet_classifications_df,
    create_sample_contract_data,
    create_sample_contracts_df,
    create_sample_enriched_awards_df,
    create_sample_evidence_statement,
    create_sample_patents_df,
    create_sample_sbir_data,
    create_sample_transition_detector_config,
    create_sample_transitions_df,
)

__all__ = [
    # Exception helpers
    "assert_exception_structure",
    "assert_raises_with_context",
    "assert_exception_details",
    "assert_exception_serialization",
    "assert_retryable_exception",
    "assert_non_retryable_exception",
    "create_test_exception",
    # Fixtures
    "create_sample_sbir_data",
    "create_sample_cet_area",
    "create_sample_evidence_statement",
    "create_sample_award_data",
    "create_sample_award_dict",
    "create_sample_contract_data",
    "create_sample_contracts_df",
    "create_sample_patents_df",
    "create_sample_cet_classifications_df",
    "create_sample_transitions_df",
    "create_sample_enriched_awards_df",
    "create_sample_transition_detector_config",
    # Config mocks
    "create_mock_pipeline_config",
    "create_mock_usaspending_config",
    "create_mock_neo4j_config",
    "create_mock_enrichment_refresh_config",
]
