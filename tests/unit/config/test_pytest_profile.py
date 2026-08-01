"""Contracts for pytest's default configuration profile."""

import os

from sbir_etl.config.loader import get_config, reload_config


def test_pytest_defaults_to_test_profile():
    """Local pytest and CI both load test.yaml unless a test overrides selection."""
    assert os.environ["SBIR_ETL__PIPELINE__ENVIRONMENT"] == "test"

    reload_config()
    try:
        config = get_config()
    finally:
        reload_config()

    assert config.pipeline.environment == "test"
    assert config.duckdb.database_path == ":memory:"
