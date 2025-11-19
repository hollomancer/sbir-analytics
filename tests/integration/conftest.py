"""Shared fixtures for integration tests."""

from pathlib import Path

import pytest

from tests.utils.config_mocks import create_mock_pipeline_config, create_mock_neo4j_config


@pytest.fixture(scope="session")
def integration_config():
    """Configuration for integration tests."""
    return create_mock_pipeline_config(
        neo4j__uri="bolt://localhost:7687",
        neo4j__database="neo4j_test",
    )


@pytest.fixture
def neo4j_config():
    """Neo4j configuration for integration tests."""
    return create_mock_neo4j_config(
        uri="bolt://localhost:7687",
        database="neo4j_test",
    )


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Temporary directory for test data files."""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def test_reports_dir(tmp_path: Path) -> Path:
    """Temporary directory for test reports."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    return reports_dir

