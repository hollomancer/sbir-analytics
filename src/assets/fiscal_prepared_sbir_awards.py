try:
    from dagster import asset
except Exception:
    # allow running tests where dagster isn't installed; provide a no-op decorator
    def asset(fn=None, **kwargs):  # type: ignore[no-redef]
        if fn is None:

            def _wrap(f):
                return f

            return _wrap
        return fn


from pathlib import Path
from typing import Any


# Import NAICS enricher from consolidated package
try:
    from src.enrichers.naics import NAICSEnricher, NAICSEnricherConfig
except ImportError:
    # Fallback for environments without enrichers installed
    NAICSEnricher = None  # type: ignore[assignment, misc, no-redef]
    NAICSEnricherConfig = None  # type: ignore[assignment, misc, no-redef]


@asset
def fiscal_prepared_sbir_awards(raw_awards: Any) -> list[dict] | None:
    """Dagster asset: enrich raw_awards with NAICS using the persisted usaspending index.

    Expects `raw_awards` to be a pandas DataFrame-like object with columns `award_id` and `recipient_uei`.
    Returns the enriched DataFrame (dict representation) or None if index not available.
    """
    if NAICSEnricher is None or NAICSEnricherConfig is None:
        # can't load enricher module
        return None  # type: ignore[unreachable]

    cache_path = Path("data/processed/usaspending/naics_index.parquet")
    cfg = NAICSEnricherConfig(
        zip_path="data/raw/usaspending/usaspending-db-subset_20251006.zip",
        cache_path=str(cache_path),
        sample_only=True,
    )
    enr = NAICSEnricher(cfg)
    try:
        enr.load_usaspending_index(force=False)
    except FileNotFoundError:
        return None

    enriched = enr.enrich_awards(raw_awards)
    # return a lightweight serializable form
    return enriched.to_dict(orient="records")
