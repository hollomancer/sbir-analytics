"""CET Neo4j loading assets.

This module contains:
- loaded_cet_areas: Load CETArea nodes into Neo4j
- loaded_award_cet_enrichment: Upsert CET enrichment onto Award nodes
- loaded_company_cet_enrichment: Upsert CET enrichment onto Company nodes
- loaded_award_cet_relationships: Create Award -> CETArea relationships
- loaded_company_cet_relationships: Create Company -> CETArea relationships
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .company import (
    DEFAULT_AWARD_CLASS_JSON,
    DEFAULT_AWARD_CLASS_PARQUET,
    DEFAULT_COMPANY_PROFILES_JSON,
    DEFAULT_COMPANY_PROFILES_PARQUET,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TAXONOMY_JSON,
    DEFAULT_TAXONOMY_PARQUET,
    _get_neo4j_client,
)
from .utils import (
    AssetIn,
    _read_parquet_or_ndjson,
    _serialize_metrics,
    asset,
    neo4j_skip_requested,
)


# Neo4j loader imports
try:
    from sbir_graph.loaders.neo4j.cet import CETLoader, CETLoaderConfig
except Exception:
    CETLoader = None
    CETLoaderConfig = None


def _skip_requested(context, operation: str) -> bool:
    """Return True when SKIP_NEO4J_LOADING requests skipping this load.

    Delegates to the shared predicate so this gate cannot drift from the client
    factory in ``company.py``; see ``SKIP_NEO4J_VALUES`` for the accepted values.
    """
    if not neo4j_skip_requested():
        return False
    context.log.warning(f"Skipping {operation}: SKIP_NEO4J_LOADING is enabled")
    return True


def _require_loader() -> None:
    if CETLoader is None or CETLoaderConfig is None:
        raise RuntimeError("CET Neo4j loader dependencies are unavailable")


def _connected_client():
    client = _get_neo4j_client()
    if client is None:
        raise RuntimeError("Neo4j loading was not skipped, but no client was created")
    return client


def _close_client(client, context) -> None:
    try:
        client.close()
    except Exception as exc:  # pragma: no cover - defensive cleanup
        context.log.warning(f"Failed to close Neo4j client cleanly: {exc}")


def _metric_count(metrics, field: str, key: str) -> int:
    values = getattr(metrics, field, {}) or {}
    if not isinstance(values, dict):
        return int(values)
    return int(values.get(key, 0) or 0)


def _complete_load(
    *,
    filename: str,
    operation: str,
    count_field: str,
    submitted: int,
    processed: int,
    metrics,
    reported_count: int | None = None,
) -> dict[str, Any]:
    """Persist an auditable load summary and fail unless every submitted item was processed."""
    errors = int(getattr(metrics, "errors", 0) or 0)
    match_rate = processed / submitted if submitted else 0.0
    successful = submitted > 0 and processed == submitted and errors == 0
    result = {
        "status": "success" if successful else "error",
        count_field: submitted if reported_count is None else reported_count,
        "submitted": submitted,
        "processed": processed,
        "match_rate": match_rate,
        "errors": errors,
        "metrics": _serialize_metrics(metrics),
    }
    _write_summary(filename, result)
    if errors:
        raise RuntimeError(f"{operation} completed with {errors} loader error(s)")
    if not submitted:
        raise RuntimeError(f"{operation} received no records")
    if processed != submitted:
        raise RuntimeError(
            f"{operation} processed {processed}/{submitted} submitted item(s) ({match_rate:.1%})"
        )
    return result


def _expected_award_relationships(classifications: list[dict]) -> int:
    expected = 0
    for row in classifications:
        if row.get("primary_cet"):
            expected += 1
        supporting = row.get("supporting_cets") or []
        if isinstance(supporting, list):
            expected += sum(
                1 for item in supporting if isinstance(item, dict) and item.get("cet_id")
            )
    return expected


def _write_summary(filename: str, result: dict[str, Any]) -> None:
    out_path = DEFAULT_OUTPUT_DIR / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)


def _award_enrichments(classifications: list[dict]) -> list[dict]:
    enrichments = []
    for row in classifications:
        supporting = row.get("supporting_cets") or []
        enrichments.append(
            {
                "award_id": row["award_id"],
                "cet_primary_id": row.get("primary_cet"),
                "cet_primary_score": row.get("primary_score"),
                "cet_supporting_ids": [
                    item.get("cet_id") for item in supporting if isinstance(item, dict)
                ],
                "cet_taxonomy_version": row.get("taxonomy_version"),
                "cet_classified_at": row.get("classified_at"),
                "cet_model_version": row.get("model_version"),
            }
        )
    return enrichments


def _company_enrichments(profiles: list[dict]) -> list[dict]:
    enrichments = []
    for row in profiles:
        cet_scores = row.get("cet_scores") or {}
        enrichments.append(
            {
                "company_id": row["company_id"],
                "cet_dominant_id": row.get("dominant_cet"),
                "cet_dominant_score": row.get("dominant_score"),
                "cet_specialization_score": row.get("specialization_score"),
                "cet_areas": list(cet_scores) if isinstance(cet_scores, dict) else [],
                "cet_taxonomy_version": row.get("taxonomy_version"),
            }
        )
    return enrichments


@asset(
    name="loaded_cet_areas",
    description="Load CETArea nodes into Neo4j from CET taxonomy artifact.",
    group_name="neo4j_cet",
    ins={"cet_taxonomy": AssetIn(key=["ml", "raw_cet_taxonomy"])},
    config_schema={
        "create_constraints": bool,
        "create_indexes": bool,
        "taxonomy_parquet": str,
        "taxonomy_json": str,
        "batch_size": int,
    },
)
def loaded_cet_areas(context, cet_taxonomy) -> dict[str, Any]:
    """Upsert CETArea nodes based on taxonomy output."""
    if _skip_requested(context, "CETArea loading"):
        return {"status": "skipped", "reason": "explicit_skip"}
    _require_loader()

    # Config
    taxonomy_parquet = Path(
        context.op_config.get("taxonomy_parquet") or str(DEFAULT_TAXONOMY_PARQUET)
    )
    taxonomy_json = Path(context.op_config.get("taxonomy_json") or str(DEFAULT_TAXONOMY_JSON))
    create_constraints = bool(context.op_config.get("create_constraints", True))
    create_indexes = bool(context.op_config.get("create_indexes", True))
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read taxonomy (expect: cet_id, name, definition, keywords, taxonomy_version)
    expected_cols = ("cet_id", "name", "taxonomy_version")
    areas = _read_parquet_or_ndjson(taxonomy_parquet, taxonomy_json, expected_columns=expected_cols)
    context.log.info(f"Loaded CET taxonomy records for Neo4j: {len(areas)}")

    client = _connected_client()
    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        if create_constraints:
            loader.create_constraints()
        if create_indexes:
            loader.create_indexes()

        metrics = loader.load_cet_areas(areas)
        # The upsert metrics intentionally exclude content-identical matches, so successful
        # processing is the submitted row count minus rows recorded as loader errors.
        processed = max(0, len(areas) - int(getattr(metrics, "errors", 0) or 0))
        return _complete_load(
            filename="neo4j_cetarea_nodes.checks.json",
            operation="CETArea loading",
            count_field="areas",
            submitted=len(areas),
            processed=processed,
            metrics=metrics,
        )
    except Exception as exc:
        context.log.exception(f"CETArea loading failed: {exc}")
        raise
    finally:
        _close_client(client, context)


@asset(
    name="loaded_award_cet_enrichment",
    description="Upsert CET enrichment properties onto Award nodes from award classifications artifact.",
    group_name="neo4j_cet",
    ins={
        "enriched_cet_award_classifications": AssetIn(
            key=["ml", "enriched_cet_award_classifications"]
        ),
        "loaded_cet_areas": AssetIn(),
    },
    config_schema={
        "award_class_parquet": str,
        "award_class_json": str,
        "batch_size": int,
    },
)
def loaded_award_cet_enrichment(
    context, enriched_cet_award_classifications, loaded_cet_areas
) -> dict[str, Any]:
    """Upsert CET enrichment properties onto Award nodes."""
    if _skip_requested(context, "Award CET enrichment"):
        return {"status": "skipped", "reason": "explicit_skip"}
    _require_loader()

    # Config
    award_class_parquet = Path(
        context.op_config.get("award_class_parquet") or str(DEFAULT_AWARD_CLASS_PARQUET)
    )
    award_class_json = Path(
        context.op_config.get("award_class_json") or str(DEFAULT_AWARD_CLASS_JSON)
    )
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read award classifications
    expected_cols = ("award_id", "primary_cet")
    classifications = _read_parquet_or_ndjson(
        award_class_parquet, award_class_json, expected_columns=expected_cols
    )
    context.log.info(f"Loaded award classifications for Neo4j: {len(classifications)}")

    client = _connected_client()
    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.upsert_award_cet_enrichment(_award_enrichments(classifications))
        return _complete_load(
            filename="neo4j_award_cet_enrichment.checks.json",
            operation="Award CET enrichment",
            count_field="awards",
            submitted=len(classifications),
            processed=_metric_count(metrics, "nodes_updated", "FinancialTransaction"),
            metrics=metrics,
        )
    except Exception as exc:
        context.log.exception(f"Award CET enrichment failed: {exc}")
        raise
    finally:
        _close_client(client, context)


@asset(
    name="loaded_company_cet_enrichment",
    description="Upsert CET enrichment properties onto Company nodes from company CET profiles.",
    group_name="neo4j_cet",
    ins={
        "transformed_cet_company_profiles": AssetIn(key=["ml", "transformed_cet_company_profiles"]),
        "loaded_cet_areas": AssetIn(),
    },
    config_schema={
        "company_profiles_parquet": str,
        "company_profiles_json": str,
        "batch_size": int,
    },
)
def loaded_company_cet_enrichment(
    context, transformed_cet_company_profiles, loaded_cet_areas
) -> dict[str, Any]:
    """Upsert CET enrichment properties onto Company nodes."""
    if _skip_requested(context, "Company CET enrichment"):
        return {"status": "skipped", "reason": "explicit_skip"}
    _require_loader()

    # Config
    company_profiles_parquet = Path(
        context.op_config.get("company_profiles_parquet") or str(DEFAULT_COMPANY_PROFILES_PARQUET)
    )
    company_profiles_json = Path(
        context.op_config.get("company_profiles_json") or str(DEFAULT_COMPANY_PROFILES_JSON)
    )
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read company profiles
    expected_cols = ("company_id", "dominant_cet", "specialization_score")
    profiles = _read_parquet_or_ndjson(
        company_profiles_parquet, company_profiles_json, expected_columns=expected_cols
    )
    context.log.info(f"Loaded company profiles for Neo4j: {len(profiles)}")

    client = _connected_client()
    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.upsert_company_cet_enrichment(
            _company_enrichments(profiles), key_property="company_id"
        )
        return _complete_load(
            filename="neo4j_company_cet_enrichment.checks.json",
            operation="Company CET enrichment",
            count_field="companies",
            submitted=len(profiles),
            processed=_metric_count(metrics, "nodes_updated", "Organization"),
            metrics=metrics,
        )
    except Exception as exc:
        context.log.exception(f"Company CET enrichment failed: {exc}")
        raise
    finally:
        _close_client(client, context)


@asset(
    name="loaded_award_cet_relationships",
    description="Create Award -> CETArea relationships from award classifications.",
    group_name="neo4j_cet",
    ins={
        "enriched_cet_award_classifications": AssetIn(
            key=["ml", "enriched_cet_award_classifications"]
        ),
        "loaded_cet_areas": AssetIn(),
        "loaded_award_cet_enrichment": AssetIn(),
    },
    config_schema={
        "award_class_parquet": str,
        "award_class_json": str,
        "batch_size": int,
    },
)
def loaded_award_cet_relationships(
    context, enriched_cet_award_classifications, loaded_cet_areas, loaded_award_cet_enrichment
) -> dict[str, Any]:
    """Create Award -> CETArea relationships."""
    if _skip_requested(context, "Award CET relationships"):
        return {"status": "skipped", "reason": "explicit_skip"}
    _require_loader()

    # Config
    award_class_parquet = Path(
        context.op_config.get("award_class_parquet") or str(DEFAULT_AWARD_CLASS_PARQUET)
    )
    award_class_json = Path(
        context.op_config.get("award_class_json") or str(DEFAULT_AWARD_CLASS_JSON)
    )
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read award classifications
    expected_cols = ("award_id", "primary_cet")
    classifications = _read_parquet_or_ndjson(
        award_class_parquet, award_class_json, expected_columns=expected_cols
    )
    context.log.info(f"Creating Award->CETArea relationships for {len(classifications)} awards")

    client = _connected_client()
    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.create_award_cet_relationships(classifications)
        expected = _expected_award_relationships(classifications)
        return _complete_load(
            filename="neo4j_award_cet_relationships.checks.json",
            operation="Award CET relationship loading",
            count_field="awards",
            submitted=expected,
            processed=_metric_count(metrics, "relationships_created", "APPLICABLE_TO"),
            metrics=metrics,
            reported_count=len(classifications),
        )
    except Exception as exc:
        context.log.exception(f"Award CET relationships failed: {exc}")
        raise
    finally:
        _close_client(client, context)


@asset(
    name="loaded_company_cet_relationships",
    description="Create Company -> CETArea relationships from company CET profiles or enrichment.",
    group_name="neo4j_cet",
    ins={
        "transformed_cet_company_profiles": AssetIn(key=["ml", "transformed_cet_company_profiles"]),
        "loaded_cet_areas": AssetIn(),
        "loaded_company_cet_enrichment": AssetIn(),
    },
    config_schema={
        "company_profiles_parquet": str,
        "company_profiles_json": str,
        "batch_size": int,
    },
)
def loaded_company_cet_relationships(
    context, transformed_cet_company_profiles, loaded_cet_areas, loaded_company_cet_enrichment
) -> dict[str, Any]:
    """Create Company -> CETArea relationships."""
    if _skip_requested(context, "Company CET relationships"):
        return {"status": "skipped", "reason": "explicit_skip"}
    _require_loader()

    # Config
    company_profiles_parquet = Path(
        context.op_config.get("company_profiles_parquet") or str(DEFAULT_COMPANY_PROFILES_PARQUET)
    )
    company_profiles_json = Path(
        context.op_config.get("company_profiles_json") or str(DEFAULT_COMPANY_PROFILES_JSON)
    )
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read company profiles
    expected_cols = ("company_id", "dominant_cet", "specialization_score")
    profiles = _read_parquet_or_ndjson(
        company_profiles_parquet, company_profiles_json, expected_columns=expected_cols
    )
    context.log.info(f"Creating Company->CETArea relationships for {len(profiles)} companies")

    client = _connected_client()
    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.create_company_cet_relationships(profiles, key_property="company_id")
        return _complete_load(
            filename="neo4j_company_cet_relationships.checks.json",
            operation="Company CET relationship loading",
            count_field="companies",
            submitted=len(profiles),
            processed=_metric_count(metrics, "relationships_created", "SPECIALIZES_IN"),
            metrics=metrics,
        )
    except Exception as exc:
        context.log.exception(f"Company CET relationships failed: {exc}")
        raise
    finally:
        _close_client(client, context)


# ============================================================================
# Asset Aliases for Backward Compatibility
# ============================================================================

# Aliases for assets expected by __init__.py and other modules
neo4j_cetarea_nodes = loaded_cet_areas
neo4j_award_cet_enrichment = loaded_award_cet_enrichment
neo4j_company_cet_enrichment = loaded_company_cet_enrichment
neo4j_award_cet_relationships = loaded_award_cet_relationships
neo4j_company_cet_relationships = loaded_company_cet_relationships
