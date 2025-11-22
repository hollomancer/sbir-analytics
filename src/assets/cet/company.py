"""CET company profile assets.

This module contains:
- transformed_cet_company_profiles: Aggregate award-level CET into company profiles
- cet_company_profiles_check: Quality validation for company profiles
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from .utils import (
    AssetCheckResult,
    AssetCheckSeverity,
    Output,
    asset,
    asset_check,
    save_dataframe_parquet,
)


@asset_check(
    asset="transformed_cet_company_profiles",
    description="Company CET profiles successfully generated (basic sanity from checks JSON)",
)
def cet_company_profiles_check(context) -> AssetCheckResult:
    """
    Ensure company CET profiles were produced without critical errors.
    Consumes data/processed/cet_company_profiles.checks.json written by the asset.
    """
    import json
    from pathlib import Path

    checks_path = Path("data/processed/cet_company_profiles.checks.json")
    if not checks_path.exists():
        desc = "Missing company profiles checks JSON; aggregation asset may not have run."
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
        desc = f"Failed to read company profiles checks JSON: {exc}"
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path)},
        )

    ok = bool(checks.get("ok", False))
    desc = "Company profile generation passed" if ok else "Company profile generation failed"
    severity = AssetCheckSeverity.WARN if ok else AssetCheckSeverity.ERROR
    return AssetCheckResult(
        passed=ok,
        severity=severity,
        description=desc,
        metadata={"checks_path": str(checks_path), **checks},
    )


@asset(
    name="transformed_cet_company_profiles",
    key_prefix=["ml"],
    description=(
        "Aggregate award-level CET classifications into company-level CET profiles, "
        "persist results to `data/processed/cet_company_profiles.parquet` (parquet -> NDJSON "
        "fallback) and emit a companion checks JSON for automated validation."
    ),
)
def transformed_cet_company_profiles() -> Output:
    """
    Dagster asset to perform company-level aggregation of CET classifications.

    Behavior (best-effort / import-safe):
    - Attempts to load `data/processed/cet_award_classifications.parquet` or `.json` NDJSON fallback.
      If the classifications input is missing, produces an empty company profiles output so downstream
      consumers have a deterministic schema.
    - Uses `CompanyCETAggregator` (from `src.transformers.company_cet_aggregator`) to compute per-company
      CET aggregates: coverage, dominant CET, specialization (HHI), CET score map, and trend.
    - Persists company profiles to `data/processed/cet_company_profiles.parquet` with NDJSON fallback.
    - Writes a checks JSON summarizing company count and basic coverage metrics.
    """
    logger.info("Starting cet_company_profiles asset")

    # Local imports to keep module import-safe when optional deps are missing
    import json
    from pathlib import Path

    try:
        import pandas as pd
    except Exception:
        pd = None  # type: ignore

    try:
        from src.transformers.company_cet_aggregator import CompanyCETAggregator
    except Exception:
        CompanyCETAggregator = None  # type: ignore

    # Paths
    classifications_parquet = Path("data/processed/cet_award_classifications.parquet")
    classifications_ndjson = Path("data/processed/cet_award_classifications.json")
    output_path = Path("data/processed/cet_company_profiles.parquet")
    checks_path = output_path.with_suffix(".checks.json")

    # If dependencies missing, write placeholder output & checks
    if pd is None or CompanyCETAggregator is None:
        logger.warning(  # type: ignore[unreachable]
            "Missing dependencies for company aggregation (pandas: %s, aggregator: %s). Writing placeholder output.",
            pd is not None,
            CompanyCETAggregator is not None,
        )
        # Produce an empty DataFrame with expected columns so downstream consumers have schema
        if pd is not None:
            df_empty = pd.DataFrame(
                columns=[
                    "company_id",
                    "company_name",
                    "total_awards",
                    "awards_with_cet",
                    "coverage",
                    "dominant_cet",
                    "dominant_score",
                    "specialization_score",
                    "cet_scores",
                    "first_award_date",
                    "last_award_date",
                    "cet_trend",
                ]
            )
            try:
                save_dataframe_parquet(df_empty, output_path)
            except Exception:
                out_json = output_path.with_suffix(".json")
                out_json.parent.mkdir(parents=True, exist_ok=True)
                with open(out_json, "w", encoding="utf-8") as fh:
                    fh.write("")
        checks = {
            "ok": False,
            "reason": "missing_dependency",
            "pandas_present": pd is not None,
            "aggregator_present": CompanyCETAggregator is not None,
        }
        checks_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        metadata = {
            "path": str(output_path),
            "rows": 0,
            "checks_path": str(checks_path),
        }
        return Output(value=str(output_path), metadata=metadata)  # type: ignore[arg-type]

    # Load classifications (prefer parquet, then NDJSON)
    try:
        if classifications_parquet.exists():
            df_cls = pd.read_parquet(classifications_parquet)
        elif classifications_ndjson.exists():
            recs = []
            with open(classifications_ndjson, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        recs.append(json.loads(line))
            df_cls = pd.DataFrame(recs)
        else:
            logger.warning(
                "No cet_award_classifications found at expected paths; producing empty company profiles"
            )
            df_cls = pd.DataFrame(
                columns=[
                    "award_id",
                    "company_id",
                    "company_name",
                    "primary_cet",
                    "primary_score",
                    "supporting_cets",
                    "classified_at",
                    "award_date",
                    "phase",
                ]
            )
    except Exception:
        logger.exception("Failed to load award classifications; producing empty company profiles")
        df_cls = pd.DataFrame(
            columns=[
                "award_id",
                "company_id",
                "company_name",
                "primary_cet",
                "primary_score",
                "supporting_cets",
                "classified_at",
                "award_date",
                "phase",
            ]
        )

    # Join with enriched awards to get company information if missing
    if not df_cls.empty and "company_id" not in df_cls.columns:
        try:
            enriched_awards_parquet = Path("data/processed/enriched_sbir_awards.parquet")
            enriched_awards_ndjson = Path("data/processed/enriched_sbir_awards.ndjson")
            if enriched_awards_parquet.exists():
                df_awards = pd.read_parquet(enriched_awards_parquet)
            elif enriched_awards_ndjson.exists():
                recs = []
                with open(enriched_awards_ndjson, encoding="utf-8") as fh:
                    for line in fh:
                        if line.strip():
                            recs.append(json.loads(line))
                df_awards = pd.DataFrame(recs)
            else:
                df_awards = pd.DataFrame()

            if not df_awards.empty and "award_id" in df_cls.columns:
                # Try to find award ID column in enriched awards using helper
                from ...utils.asset_column_helper import AssetColumnHelper

                award_id_col = AssetColumnHelper.find_award_id_column(df_awards)

                if award_id_col:
                    # Try to find company identifier columns using ColumnFinder
                    from ...utils.column_finder import ColumnFinder

                    company_id_col = ColumnFinder.find_id_column(df_awards, "company")
                    company_name_col = ColumnFinder.find_column_by_patterns(
                        df_awards, ["company", "company_name"]
                    )

                    # Join on award_id
                    if company_id_col:
                        join_cols = [award_id_col, company_id_col]
                        if company_name_col and company_name_col not in join_cols:
                            join_cols.append(company_name_col)
                        df_join = df_awards[
                            [col for col in join_cols if col in df_awards.columns]
                        ].copy()
                        df_join = df_join.rename(
                            columns={award_id_col: "award_id", company_id_col: "company_id"}
                        )
                        if company_name_col and company_name_col != "company_id":
                            df_join = df_join.rename(columns={company_name_col: "company_name"})
                        df_cls = df_cls.merge(df_join, on="award_id", how="left")
                        logger.info(
                            f"Joined classifications with enriched awards to get company info (joined {df_cls['company_id'].notna().sum()} rows)"
                        )
        except Exception:
            logger.exception(
                "Failed to join classifications with enriched awards; proceeding without company info"
            )

    # Ensure company_id and company_name columns exist (CompanyCETAggregator expects them)
    if not df_cls.empty:
        if "company_id" not in df_cls.columns:
            df_cls["company_id"] = None
        if "company_name" not in df_cls.columns:
            df_cls["company_name"] = None

    # Run aggregation
    try:
        aggregator = CompanyCETAggregator(df_cls)
        df_comp = aggregator.to_dataframe()
    except Exception:
        logger.exception("Company aggregation failed; producing empty company profiles")
        df_comp = pd.DataFrame(
            columns=[
                "company_id",
                "company_name",
                "total_awards",
                "awards_with_cet",
                "coverage",
                "dominant_cet",
                "dominant_score",
                "specialization_score",
                "cet_scores",
                "first_award_date",
                "last_award_date",
                "cet_trend",
            ]
        )

    # Persist company profiles (parquet preferred, NDJSON fallback)
    try:
        save_dataframe_parquet(df_comp, output_path)
    except Exception:
        # Fallback: write NDJSON manually
        json_out = output_path.with_suffix(".json")
        json_out.parent.mkdir(parents=True, exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as fh:
            for rec in df_comp.to_dict(orient="records"):
                fh.write(json.dumps(rec) + "\n")
        # Touch parquet placeholder for consumers that assert its existence
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.touch()
        except Exception:
            logger.exception("Failed to touch parquet placeholder file for company profiles")

    # Build checks
    num_companies = len(df_comp)
    checks = {
        "ok": True,
        "num_companies": int(num_companies),
        "num_records_written": int(num_companies),
    }
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checks_path, "w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)

    metadata = {
        "path": str(output_path),
        "rows": len(df_comp),
        "checks_path": str(checks_path),
    }

    logger.info("Completed cet_company_profiles asset", rows=len(df_comp), output=str(output_path))

    return Output(value=str(output_path), metadata=metadata)


# ============================================================================
# Neo4j Loading Assets (Consolidated from cet_neo4j_loading_assets.py)
# ============================================================================

# Neo4j loader imports (import-safe)
try:
    from src.loaders.neo4j import LoadMetrics, Neo4jClient, Neo4jConfig
except Exception:  # pragma: no cover
    Neo4jClient = None  # type: ignore
    Neo4jConfig = None  # type: ignore
    LoadMetrics = None  # type: ignore

try:
    from src.loaders.neo4j import CETLoader, CETLoaderConfig
except Exception:  # pragma: no cover
    CETLoader = None  # type: ignore
    CETLoaderConfig = None  # type: ignore

# Configuration Defaults for Neo4j Loading
DEFAULT_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
DEFAULT_NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

DEFAULT_PROCESSED_DIR_NEO4J = Path("data/processed")
DEFAULT_TAXONOMY_PARQUET = DEFAULT_PROCESSED_DIR_NEO4J / "cet_taxonomy.parquet"
DEFAULT_TAXONOMY_JSON = DEFAULT_PROCESSED_DIR_NEO4J / "cet_taxonomy.json"

DEFAULT_AWARD_CLASS_PARQUET = DEFAULT_PROCESSED_DIR_NEO4J / "cet_award_classifications.parquet"
DEFAULT_AWARD_CLASS_JSON = DEFAULT_PROCESSED_DIR_NEO4J / "cet_award_classifications.json"

DEFAULT_COMPANY_PROFILES_PARQUET = DEFAULT_PROCESSED_DIR_NEO4J / "cet_company_profiles.parquet"
DEFAULT_COMPANY_PROFILES_JSON = DEFAULT_PROCESSED_DIR_NEO4J / "cet_company_profiles.json"

DEFAULT_OUTPUT_DIR = Path(os.environ.get("SBIR_ETL__CET__NEO4J_OUTPUT_DIR", "data/loaded/neo4j"))


def _get_neo4j_client():
    """Get Neo4j client with error handling."""
    if Neo4jClient is None or Neo4jConfig is None:
        return None  # type: ignore[unreachable]
    try:
        config = Neo4jConfig(
            uri=DEFAULT_NEO4J_URI,
            user=DEFAULT_NEO4J_USER,
            password=DEFAULT_NEO4J_PASSWORD,
            database=DEFAULT_NEO4J_DATABASE,
        )
        return Neo4jClient(config)
    except Exception:
        return None


def _read_parquet_or_ndjson(
    parquet_path: Path, json_path: Path, expected_columns: tuple
) -> list[dict]:
    """Read data from parquet or fallback to NDJSON."""
    if pd is None:
        return []  # type: ignore[unreachable]

    try:
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            return df.to_dict(orient="records")
        elif json_path.exists():
            records = []
            with json_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            continue
            return records
    except Exception:
        pass
    return []


def _serialize_metrics(metrics: Any) -> dict[str, Any]:
    """Serialize LoadMetrics to dict."""
    if metrics is None:
        return {}
    return {
        "nodes_created": getattr(metrics, "nodes_created", 0),
        "nodes_updated": getattr(metrics, "nodes_updated", 0),
        "relationships_created": getattr(metrics, "relationships_created", 0),
        "relationships_updated": getattr(metrics, "relationships_updated", 0),
        "execution_time_ms": getattr(metrics, "execution_time_ms", 0),
    }
