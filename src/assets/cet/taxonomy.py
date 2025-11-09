"""CET taxonomy assets and checks.

This module contains:
- raw_cet_taxonomy: Primary asset that loads and validates the CET taxonomy
- cet_taxonomy_completeness_check: Asset check for taxonomy validation
- Helper functions for taxonomy data processing
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
from loguru import logger

from src.ml.config.taxonomy_loader import TaxonomyLoader
from src.models.cet_models import CETArea
from typing import Any

from .utils import (

    AssetCheckResult,
    AssetCheckSeverity,
    Output,
    asset,
    asset_check,
    save_dataframe_parquet,
)


# Default output location for processed taxonomy
DEFAULT_OUTPUT_PATH = Path("data/processed/cet_taxonomy.parquet")


def taxonomy_to_dataframe(cet_areas: Iterable[CETArea]) -> pd.DataFrame:
    """
    Convert an iterable of `CETArea` Pydantic models to a flattened DataFrame.

    Each CETArea becomes one row with columns:
      - cet_id, name, definition, keywords (comma-separated), parent_cet_id, taxonomy_version

    Args:
        cet_areas: Iterable of CETArea objects

    Returns:
        pd.DataFrame: Flattened table suitable for writing to Parquet / DuckDB ingestion.
    """
    rows: list[dict] = []
    for area in cet_areas:
        # CETArea is a Pydantic model, use attribute access to be safe
        row = {
            "cet_id": area.cet_id,
            "name": area.name,
            "definition": area.definition,
            # store keywords as list; pandas/parquet can preserve lists when using pyarrow,
            # but to be maximally portable, also include a joined string.
            "keywords": area.keywords if isinstance(area.keywords, list) else list(area.keywords),
            "keywords_joined": ", ".join(area.keywords) if area.keywords else "",
            "parent_cet_id": area.parent_cet_id,
            "taxonomy_version": area.taxonomy_version,
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    # Ensure deterministic column order
    ordered_cols = [
        "cet_id",
        "name",
        "definition",
        "keywords",
        "keywords_joined",
        "parent_cet_id",
        "taxonomy_version",
    ]
    df = df.reindex(columns=ordered_cols)
    return df


@asset_check(
    asset="raw_cet_taxonomy",
    description="CET taxonomy completeness and schema validity based on companion checks JSON",
)
def cet_taxonomy_completeness_check(context: Any) -> AssetCheckResult:
    """
    Verify CET taxonomy was materialized and validated successfully.
    Consumes data/processed/cet_taxonomy.checks.json written by the asset.
    """
    import json
    from pathlib import Path

    checks_path = Path("data/processed/cet_taxonomy.checks.json")
    if not checks_path.exists():
        desc = "Missing taxonomy checks JSON; taxonomy asset may not have run."
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), "reason": "missing_checks"},
        )

    try:
        with checks_path.open("r", encoding="utf-8") as fh:
            checks = json.load(fh)
    except Exception as exc:
        desc = f"Failed to read taxonomy checks JSON: {exc}"
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path)},
        )

    ok = bool(checks.get("ok", False))
    desc = (
        "CET taxonomy completeness checks passed"
        if ok
        else "CET taxonomy completeness checks failed"
    )
    severity = AssetCheckSeverity.WARN if ok else AssetCheckSeverity.ERROR
    return AssetCheckResult(
        passed=ok,
        severity=severity,
        description=desc,
        metadata={"checks_path": str(checks_path), **checks},
    )


@asset(
    name="raw_cet_taxonomy",
    key_prefix=["ml"],
    description=(
        "Load CET taxonomy from `config/cet/taxonomy.yaml`, validate via Pydantic, "
        "persist to `data/processed/cet_taxonomy.parquet`, and emit a companion checks JSON "
        "for automated asset checks."
    ),
)
def raw_cet_taxonomy() -> Output:
    """
    Dagster asset that materializes the CET taxonomy as a Parquet file and writes
    lightweight completeness checks to a companion JSON file.

    Behavior:
    - Initializes `TaxonomyLoader` which reads `config/cet/taxonomy.yaml` and
      `config/cet/classification.yaml`.
    - Validates taxonomy using Pydantic models defined in `src.models.cet_models`.
    - Produces a parquet file at `data/processed/cet_taxonomy.parquet`.
    - Produces a checks JSON at `data/processed/cet_taxonomy.checks.json`.
    - Emits an Output containing the parquet path and metadata (row count, version, checks path).

    Returns:
        dagster.Output: value is the Path to the parquet file; metadata contains version/rows/checks.
    """
    logger.info("Starting cet_taxonomy asset")

    # Initialize loader (defaults to project config/cet)
    loader = TaxonomyLoader()
    taxonomy = loader.load_taxonomy()

    # Convert taxonomy CET areas to DataFrame
    df = taxonomy_to_dataframe(taxonomy.cet_areas)

    # Persist DataFrame to parquet
    output_path = DEFAULT_OUTPUT_PATH
    save_dataframe_parquet(df, output_path)

    # Run completeness checks via the loader helper (non-fatal)
    completeness = {}
    try:
        completeness = loader.validate_taxonomy_completeness(taxonomy)
    except Exception as exc:
        # In case validation helper raises unexpectedly, capture the exception into checks
        completeness = {"ok": False, "exception": str(exc)}

    # Write companion checks JSON next to parquet for CI/asset checks to consume
    checks_path = Path(str(output_path)).with_suffix(".checks.json")
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(completeness, fh, indent=2, ensure_ascii=False)
        logger.info("Wrote taxonomy checks JSON", path=str(checks_path))
    except Exception:
        logger.exception("Failed to write taxonomy checks JSON", path=str(checks_path))
        raise

    # Build metadata for Dagster (structured metadata is easier for asset checks)
    metadata = {
        "path": str(output_path),
        "rows": len(df),
        "taxonomy_version": taxonomy.version,
        "last_updated": taxonomy.last_updated,
        "description": taxonomy.description,
        "checks_path": str(checks_path),
        "cet_count": len(df),
    }

    logger.info(
        "Completed cet_taxonomy asset",
        version=taxonomy.version,
        rows=len(df),
        output=str(output_path),
        checks=str(checks_path),
    )

    # Return Output with structured metadata for downstream asset checks and lineage
    return Output(value=str(output_path), metadata=metadata)


# Alias for backward compatibility and simpler test interface
cet_taxonomy = raw_cet_taxonomy
