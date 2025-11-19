"""Shared fixtures for enricher tests."""

from unittest.mock import Mock

import pandas as pd
import pytest

from tests.utils.config_mocks import create_mock_pipeline_config
from tests.utils.fixtures import create_sample_sbir_data


@pytest.fixture
def mock_enrichment_config():
    """Mock enrichment configuration using consolidated utility."""
    config = create_mock_pipeline_config()
    # Set enrichment performance settings
    if hasattr(config, "enrichment"):
        if not hasattr(config.enrichment, "performance"):
            config.enrichment.performance = Mock()
        config.enrichment.performance.chunk_size = 100
        config.enrichment.performance.memory_threshold_mb = 512
        config.enrichment.performance.timeout_seconds = 300
        config.enrichment.performance.high_confidence_threshold = 0.95
        config.enrichment.performance.low_confidence_threshold = 0.85
        config.enrichment.performance.enable_memory_monitoring = True
        config.enrichment.performance.enable_fuzzy_matching = True
    return config


@pytest.fixture
def sample_sbir_df():
    """Sample SBIR DataFrame using consolidated utility."""
    return create_sample_sbir_data(num_records=5)


@pytest.fixture
def sample_recipient_df():
    """Sample recipient DataFrame."""
    return pd.DataFrame(
        {
            "recipient_name": ["Acme Corp", "TechStart Inc", "DataPro LLC", "BioMed Co"],
            "recipient_uei": ["UEI001", "UEI002", "UEI003", "UEI004"],
            "recipient_duns": ["123456789", "987654321", "111222333", "444555666"],
            "total_amount": [5000000, 3000000, 2000000, 1000000],
        }
    )

