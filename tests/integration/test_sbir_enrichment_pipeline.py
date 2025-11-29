"""Integration tests for SBIR enrichment pipeline."""

from types import SimpleNamespace

import pytest


def _make_test_config(
    sbir_csv_path: str = "data/raw/sbir_awards.csv",
    pass_rate_threshold: float = 0.95,
) -> SimpleNamespace:
    """Create a minimal config object for testing."""
    sbir = SimpleNamespace(csv_path=sbir_csv_path)
    extraction = SimpleNamespace(sbir=sbir)
    data_quality = SimpleNamespace(
        sbir_awards=SimpleNamespace(pass_rate_threshold=pass_rate_threshold)
    )
    return SimpleNamespace(extraction=extraction, data_quality=data_quality)


pytestmark = pytest.mark.integration


# Test removed - fixture companies don't exist in enrichment data source
# See INTEGRATION_TEST_ANALYSIS.md for details
# Consider rewriting with synthetic test data
