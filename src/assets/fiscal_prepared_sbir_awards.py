from typing import Optional
from dagster import asset

import json
from pathlib import Path
import importlib.util
import sys


def _load_naics_module():
    p = Path(__file__).resolve().parent
    # repo root
    root = p.parent.parent
    mod_path = root / "src" / "enrichers" / "naics_enricher.py"
    spec = importlib.util.spec_from_file_location("naics_enricher_mod", str(mod_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@asset
def fiscal_prepared_sbir_awards(raw_awards) -> Optional[dict]:
    """Dagster asset: enrich raw_awards with NAICS using the persisted usaspending index.

    Expects `raw_awards` to be a pandas DataFrame-like object with columns `award_id` and `recipient_uei`.
    Returns the enriched DataFrame (dict representation) or None if index not available.
    """
    try:
        naics_mod = _load_naics_module()
    except Exception:
        # can't load enricher module
        return None

    NAICSEnricher = naics_mod.NAICSEnricher
    NAICSEnricherConfig = naics_mod.NAICSEnricherConfig

    cache_path = Path("data/processed/usaspending/naics_index.parquet")
    cfg = NAICSEnricherConfig(zip_path="data/raw/usaspending/usaspending-db-subset_20251006.zip",
                              cache_path=str(cache_path), sample_only=True)
    enr = NAICSEnricher(cfg)
    try:
        enr.load_usaspending_index(force=False)
    except FileNotFoundError:
        return None

    enriched = enr.enrich_awards(raw_awards)
    # return a lightweight serializable form
    return enriched.to_dict(orient="records")
