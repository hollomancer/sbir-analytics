import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.integration


def _load_naics_module():
    # locate module relative to repo
    p = Path(__file__).resolve().parent
    while p != p.parent:
        candidate = p / ".." / ".." / "src" / "enrichers" / "naics_enricher.py"
        candidate = candidate.resolve()
        if candidate.exists():
            spec = importlib.util.spec_from_file_location("naics_enricher_mod", str(candidate))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            return mod
        p = p.parent
    raise FileNotFoundError("naics_enricher.py not found")


PARQUET_PATH = Path("data/processed/usaspending/naics_index.parquet")
FIXTURE_PATH = Path("tests/fixtures/naics_index_fixture.parquet")


def test_index_and_enrich_roundtrip():
    # prefer a committed fixture to make this test hermetic in CI
    path = FIXTURE_PATH if FIXTURE_PATH.exists() else PARQUET_PATH
    if not path.exists():
        pytest.skip("naics index parquet not present; run sample builder or generate fixture first")

    naics_mod = _load_naics_module()
    NAICSEnricher = naics_mod.NAICSEnricher
    NAICSEnricherConfig = naics_mod.NAICSEnricherConfig

    # instantiate enricher pointing at existing parquet (use cache_path)
    cfg = NAICSEnricherConfig(
        zip_path="data/raw/usaspending/usaspending-db-subset_20251006.zip",
        cache_path=str(path),
        sample_only=True,
    )
    enr = NAICSEnricher(cfg)
    enr.load_usaspending_index(force=False)

    # pick a sample award id and recipient from the built maps
    if not enr.award_map and not enr.recipient_map:
        pytest.skip("index has no entries")

    # prefer an award with candidates
    sample_award = next(iter(enr.award_map.keys())) if enr.award_map else None
    sample_recipient = next(iter(enr.recipient_map.keys())) if enr.recipient_map else None

    # Create a DataFrame with both columns; if award present we expect award-level origin
    row = {"award_id": sample_award or "", "recipient_uei": sample_recipient or ""}
    df = pd.DataFrame([row])
    out = enr.enrich_awards(df)

    assert "naics_assigned" in out.columns
    assert "naics_origin" in out.columns

    origin = out.loc[0, "naics_origin"]
    # origin should be one of the known types
    assert origin in ("usaspending_award", "usaspending_recipient", "unknown")
