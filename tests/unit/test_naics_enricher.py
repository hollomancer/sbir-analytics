import os
import pandas as pd
import pytest

from src.enrichers.naics_enricher import NAICSEnricher, NAICSEnricherConfig


USASPENDING_ZIP = os.path.join("data", "raw", "usaspending", "usaspending-db-subset_20251006.zip")


def test_build_index_sampled(tmp_path):
    if not os.path.exists(USASPENDING_ZIP):
        pytest.skip("usaspending zip not present")

    cache = tmp_path / "naics_index.parquet"
    cfg = NAICSEnricherConfig(zip_path=USASPENDING_ZIP, cache_path=str(cache), sample_only=True, max_files=2, max_lines_per_file=200)
    enr = NAICSEnricher(cfg)
    enr.load_usaspending_index(force=True)
    # after build, expect some entries in award_map or recipient_map
    assert isinstance(enr.award_map, dict)
    assert isinstance(enr.recipient_map, dict)
    assert (len(enr.award_map) + len(enr.recipient_map)) > 0


def test_enrich_awards_with_index(tmp_path):
    if not os.path.exists(USASPENDING_ZIP):
        pytest.skip("usaspending zip not present")

    cache = tmp_path / "naics_index.parquet"
    cfg = NAICSEnricherConfig(zip_path=USASPENDING_ZIP, cache_path=str(cache), sample_only=True, max_files=2, max_lines_per_file=200)
    enr = NAICSEnricher(cfg)
    enr.load_usaspending_index(force=True)

    # craft a synthetic awards df using a known award_id from the index if available
    sample_award_id = next(iter(enr.award_map.keys())) if enr.award_map else None
    if sample_award_id is None:
        pytest.skip("no award ids discovered during index build")

    df = pd.DataFrame([{"award_id": sample_award_id, "recipient_uei": ""}])
    out = enr.enrich_awards(df)
    assert "naics_assigned" in out.columns
    # assigned NAICS may be present
    assert out.loc[0, "naics_origin"] in ("usaspending_award", "usaspending_recipient", "unknown")
