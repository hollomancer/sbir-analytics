from pathlib import Path
import shutil

import pandas as pd
import pytest

from src.assets.fiscal_prepared_sbir_awards import fiscal_prepared_sbir_awards


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

    # prepare a small raw_awards DataFrame
    raw_awards = pd.DataFrame([{"award_id": "A12345", "recipient_uei": "R-UEI-001"}])

    enriched = fiscal_prepared_sbir_awards(raw_awards)
    assert isinstance(enriched, list)
    assert len(enriched) == 1
    row = enriched[0]
    assert "naics_assigned" in row
    assert "naics_origin" in row
