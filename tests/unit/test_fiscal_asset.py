"""Unit tests for fiscal asset preparation and NAICS enrichment."""

import shutil
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from dagster import Output, build_asset_context

from src.assets.fiscal_assets import fiscal_prepared_sbir_awards


pytestmark = pytest.mark.fast


@pytest.fixture
def mock_config():
    """Create mock config for fiscal asset tests."""
    from tests.utils.config_mocks import create_mock_pipeline_config

    return create_mock_pipeline_config()


@pytest.fixture
def sample_raw_awards():
    """Sample raw awards DataFrame."""
    return pd.DataFrame(
        [
            {"award_id": "A12345", "recipient_uei": "R-UEI-001", "fiscal_naics_code": "541330"},
            {"award_id": "A12346", "recipient_uei": "R-UEI-002", "fiscal_naics_code": "541715"},
            {"award_id": "A12347", "recipient_uei": "R-UEI-003", "fiscal_naics_code": None},
        ]
    )


def test_asset_returns_output_type(mock_config, sample_raw_awards):
    """Test fiscal_prepared_sbir_awards returns Output type."""
    context = build_asset_context()

    with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
        result = fiscal_prepared_sbir_awards(context, sample_raw_awards)

    assert isinstance(result, Output)
    assert isinstance(result.value, pd.DataFrame)


def test_asset_preserves_award_ids(mock_config, sample_raw_awards):
    """Test that award IDs are preserved in output."""
    context = build_asset_context()

    with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
        result = fiscal_prepared_sbir_awards(context, sample_raw_awards)

    enriched = result.value
    assert set(enriched["award_id"]) == {"A12345", "A12346", "A12347"}


def test_asset_handles_missing_naics(mock_config):
    """Test asset handles records with missing NAICS codes."""
    raw_awards = pd.DataFrame(
        [
            {"award_id": "A001", "recipient_uei": "UEI001", "fiscal_naics_code": None},
        ]
    )
    context = build_asset_context()

    with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
        result = fiscal_prepared_sbir_awards(context, raw_awards)

    assert isinstance(result.value, pd.DataFrame)
    assert len(result.value) == 1


def test_asset_uses_fixture(tmp_path):
    """Test asset with fixture data (legacy test)."""
    fixture = Path("tests/fixtures/naics_index_fixture.parquet")
    if not fixture.exists():
        pass

    dest_dir = Path("data/processed/usaspending")
    dest_dir.mkdir(parents=True, exist_ok=True)
    if fixture.exists():
        shutil.copy(fixture, dest_dir / "naics_index.parquet")

    raw_awards = pd.DataFrame(
        [{"award_id": "A12345", "recipient_uei": "R-UEI-001", "fiscal_naics_code": "541330"}]
    )

    context = build_asset_context()

    with patch("src.assets.fiscal_assets.get_config") as mock_get_config:
        from tests.utils.config_mocks import create_mock_pipeline_config

        mock_config = create_mock_pipeline_config()
        mock_get_config.return_value = mock_config

        result = fiscal_prepared_sbir_awards(context, raw_awards)

    assert isinstance(result, Output)
    enriched = result.value
    assert isinstance(enriched, pd.DataFrame)
    assert len(enriched) == 1
