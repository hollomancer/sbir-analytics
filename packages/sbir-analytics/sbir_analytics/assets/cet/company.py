"""CET company profile assets.

This module contains:
- transformed_cet_company_profiles: Aggregate award-level CET into company profiles
- cet_company_profiles_check: Quality validation for company profiles
"""

from __future__ import annotations

import pandas as pd
from loguru import logger

from sbir_etl.utils.identifiers import normalize_uei

from .utils import (
    AssetCheckResult,
    AssetCheckSeverity,
    Output,
    asset,
    asset_check,
    save_dataframe_parquet,
)


_COMPANY_UEI_COLUMNS = ("company_uei", "uei", "recipient_uei")


def _find_exact_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    columns = {str(column).lower(): str(column) for column in df.columns}
    return next(
        (columns[candidate.lower()] for candidate in candidates if candidate.lower() in columns),
        None,
    )


def _attach_company_uei(df_cls: pd.DataFrame, df_awards: pd.DataFrame) -> pd.DataFrame:
    """Attach an explicit UEI and use it as the aggregator's compatibility company key."""
    result = df_cls.copy()
    classification_uei_col = _find_exact_column(result, _COMPANY_UEI_COLUMNS)
    if classification_uei_col:
        result["company_uei"] = result[classification_uei_col].map(normalize_uei)
    else:
        result["company_uei"] = None

    if not df_awards.empty and "award_id" in result.columns:
        from sbir_etl.utils.asset_column_helper import AssetColumnHelper
        from sbir_etl.utils.column_finder import ColumnFinder

        award_id_col = AssetColumnHelper.find_award_id_column(df_awards)
        uei_col = _find_exact_column(df_awards, _COMPANY_UEI_COLUMNS)
        company_name_col = ColumnFinder.find_column_by_patterns(
            df_awards, ["company_name", "company"]
        )

        if award_id_col and uei_col:
            join_cols = [award_id_col, uei_col]
            selected_company_name_col = (
                company_name_col
                if company_name_col and "company_name" not in result.columns
                else None
            )
            if selected_company_name_col and selected_company_name_col not in join_cols:
                join_cols.append(selected_company_name_col)

            df_join = df_awards[join_cols].copy()
            rename_columns = {
                award_id_col: "award_id",
                uei_col: "_enriched_company_uei",
            }
            if selected_company_name_col:
                rename_columns[selected_company_name_col] = "company_name"
            df_join = df_join.rename(columns=rename_columns)
            df_join["_enriched_company_uei"] = df_join["_enriched_company_uei"].map(normalize_uei)
            result = result.merge(df_join, on="award_id", how="left")
            result["company_uei"] = result["_enriched_company_uei"].combine_first(
                result["company_uei"]
            )
            result = result.drop(columns="_enriched_company_uei")

    # CompanyCETAggregator still groups on company_id. Keep that internal alias tied
    # strictly to a typed UEI so DUNS or arbitrary legacy IDs cannot reach a UEI match.
    result["company_id"] = result["company_uei"]
    return result


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

    Behavior:
    - Attempts to load `data/processed/cet_award_classifications.parquet` or `.ndjson` fallback.
      Missing or unreadable classification inputs fail the materialization.
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
        from sbir_etl.transformers.company_cet_aggregator import CompanyCETAggregator
    except Exception as exc:
        raise RuntimeError("CET company aggregation dependency is unavailable") from exc

    # Paths
    classifications_parquet = Path("data/processed/cet_award_classifications.parquet")
    classifications_ndjson = Path("data/processed/cet_award_classifications.ndjson")
    output_path = Path("data/processed/cet_company_profiles.parquet")
    checks_path = output_path.with_suffix(".checks.json")

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
            raise FileNotFoundError(
                "No CET award classifications found at "
                f"{classifications_parquet} or {classifications_ndjson}"
            )
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise RuntimeError("Failed to load CET award classifications") from exc

    if df_cls.empty:
        raise ValueError("CET award classification input is empty; no companies can be aggregated")

    # Join with enriched awards to attach a typed UEI. The classification artifact does
    # not normally carry company identity, and generic company IDs are not graph keys.
    if not df_cls.empty:
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
            df_cls = _attach_company_uei(df_cls, df_awards)
            logger.info(
                "Joined classifications with explicit company UEIs "
                f"(joined {df_cls['company_uei'].notna().sum()} rows)"
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to join CET classifications with enriched award company data"
            ) from exc

    if "company_id" not in df_cls.columns or not df_cls["company_id"].notna().any():
        raise ValueError("CET award classifications contain no usable company identifiers")
    if "company_name" not in df_cls.columns:
        df_cls["company_name"] = None

    # Run aggregation
    try:
        aggregator = CompanyCETAggregator(df_cls)
        df_comp = aggregator.to_dataframe()
    except Exception as exc:
        raise RuntimeError("CET company aggregation failed") from exc

    if df_comp.empty:
        raise ValueError("CET company aggregation produced no company profiles")

    # Preserve the semantic identity alongside CompanyCETAggregator's compatibility field.
    df_comp["company_uei"] = df_comp["company_id"]

    # Persist company profiles (parquet preferred, NDJSON fallback)
    artifact_path = save_dataframe_parquet(df_comp, output_path)

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
        "path": str(artifact_path),
        "rows": len(df_comp),
        "checks_path": str(checks_path),
    }

    logger.info(
        "Completed cet_company_profiles asset", rows=len(df_comp), output=str(artifact_path)
    )

    return Output(value=str(artifact_path), metadata=metadata)  # type: ignore[arg-type]
