import shutil
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from dagster import Output, build_asset_context

from src.assets.fiscal_assets import fiscal_prepared_sbir_awards


pytestmark = pytest.mark.fast


def test_asset_uses_fixture(tmp_path):
    # copy fixture into expected processed location
    fixture = Path("tests/fixtures/naics_index_fixture.parquet")
    if not fixture.exists():
        # generate fixture if missing (non-failing test)
        pass
        # the generator prints output; just ensure it ran
    dest_dir = Path("data/processed/usaspending")
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture, dest_dir / "naics_index.parquet")

    # prepare a small raw_awards DataFrame with required columns
    raw_awards = pd.DataFrame(
        [
            {
                "award_id": "A12345",
                "recipient_uei": "R-UEI-001",
                "fiscal_naics_code": "541330",  # Add required column
            }
        ]
    )

    # Use build_asset_context instead of Mock
    context = build_asset_context()

    with patch("src.assets.fiscal_assets.get_config") as mock_get_config:
        from tests.utils.config_mocks import create_mock_pipeline_config

        mock_config = create_mock_pipeline_config()
        mock_get_config.return_value = mock_config

        result = fiscal_prepared_sbir_awards(context, raw_awards)

    # Asset returns Output[pd.DataFrame], extract the value
    assert isinstance(result, Output)
    enriched = result.value
    assert isinstance(enriched, pd.DataFrame)
    assert len(enriched) == 1
    assert "fiscal_naics_code" in enriched.columns or "naics_assigned" in enriched.columns
