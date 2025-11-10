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

from .company import _get_neo4j_client
from .utils import (
    DEFAULT_AWARD_CLASS_JSON,
    DEFAULT_AWARD_CLASS_PARQUET,
    DEFAULT_COMPANY_PROFILES_JSON,
    DEFAULT_COMPANY_PROFILES_PARQUET,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TAXONOMY_JSON,
    DEFAULT_TAXONOMY_PARQUET,
    AssetIn,
    _read_parquet_or_ndjson,
    _serialize_metrics,
    asset,
)


# Neo4j loader imports
try:
    from src.loaders.neo4j.cet_loader import CETLoader, CETLoaderConfig
except Exception:
    CETLoader = None
    CETLoaderConfig = None


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
    if CETLoader is None or CETLoaderConfig is None:
        context.log.warning("CETLoader unavailable; skipping CETArea loading")
        return {"status": "skipped", "reason": "loader_unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "skipped", "reason": "neo4j_unavailable"}

    # Config
    taxonomy_parquet = Path(
        context.op_config.get("taxonomy_parquet") or str(DEFAULT_TAXONOMY_PARQUET)
    )
    taxonomy_json = Path(context.op_config.get("taxonomy_json") or str(DEFAULT_TAXONOMY_JSON))
    create_constraints = bool(context.op_config.get("create_constraints", True))
    create_indexes = bool(context.op_config.get("create_indexes", True))
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read taxonomy (expect: cet_id, name, definition, keywords, taxonomy_version)
    expected_cols = ("cet_id", "name", "definition", "keywords", "taxonomy_version")
    areas = _read_parquet_or_ndjson(taxonomy_parquet, taxonomy_json, expected_columns=expected_cols)
    context.log.info(f"Loaded CET taxonomy records for Neo4j: {len(areas)}")

    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        if create_constraints:
            loader.create_constraints()
        if create_indexes:
            loader.create_indexes()

        metrics = loader.load_cet_areas(areas)
        result = {
            "status": "success",
            "areas": len(areas),
            "metrics": _serialize_metrics(metrics),
        }

        # Persist a small run summary
        out_path = DEFAULT_OUTPUT_DIR / "neo4j_cetarea_nodes.checks.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with out_path.open("w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2)
        except Exception:
            pass

        try:
            client.close()
        except Exception:
            pass
        return result
    except Exception as exc:
        context.log.exception(f"CETArea loading failed: {exc}")
        try:
            client.close()
        except Exception:
            pass
        return {"status": "error", "error": str(exc)}


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
    if CETLoader is None or CETLoaderConfig is None:
        context.log.warning("CETLoader unavailable; skipping Award CET enrichment")
        return {"status": "skipped", "reason": "loader_unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "skipped", "reason": "neo4j_unavailable"}

    # Config
    award_class_parquet = Path(
        context.op_config.get("award_class_parquet") or str(DEFAULT_AWARD_CLASS_PARQUET)
    )
    award_class_json = Path(
        context.op_config.get("award_class_json") or str(DEFAULT_AWARD_CLASS_JSON)
    )
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read award classifications
    expected_cols = ("award_id", "primary_cet", "supporting_cets", "confidence", "evidence")
    classifications = _read_parquet_or_ndjson(
        award_class_parquet, award_class_json, expected_columns=expected_cols
    )
    context.log.info(f"Loaded award classifications for Neo4j: {len(classifications)}")

    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.load_award_cet_enrichment(classifications)
        result = {
            "status": "success",
            "awards": len(classifications),
            "metrics": _serialize_metrics(metrics),
        }

        # Persist a small run summary
        out_path = DEFAULT_OUTPUT_DIR / "neo4j_award_cet_enrichment.checks.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with out_path.open("w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2)
        except Exception:
            pass

        try:
            client.close()
        except Exception:
            pass
        return result
    except Exception as exc:
        context.log.exception(f"Award CET enrichment failed: {exc}")
        try:
            client.close()
        except Exception:
            pass
        return {"status": "error", "error": str(exc)}


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
    if CETLoader is None or CETLoaderConfig is None:
        context.log.warning("CETLoader unavailable; skipping Company CET enrichment")
        return {"status": "skipped", "reason": "loader_unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "skipped", "reason": "neo4j_unavailable"}

    # Config
    company_profiles_parquet = Path(
        context.op_config.get("company_profiles_parquet") or str(DEFAULT_COMPANY_PROFILES_PARQUET)
    )
    company_profiles_json = Path(
        context.op_config.get("company_profiles_json") or str(DEFAULT_COMPANY_PROFILES_JSON)
    )
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read company profiles
    expected_cols = (
        "company_uei",
        "dominant_cet",
        "specialization_score",
        "award_count",
        "total_funding",
    )
    profiles = _read_parquet_or_ndjson(
        company_profiles_parquet, company_profiles_json, expected_columns=expected_cols
    )
    context.log.info(f"Loaded company profiles for Neo4j: {len(profiles)}")

    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.load_company_cet_enrichment(profiles)
        result = {
            "status": "success",
            "companies": len(profiles),
            "metrics": _serialize_metrics(metrics),
        }

        # Persist a small run summary
        out_path = DEFAULT_OUTPUT_DIR / "neo4j_company_cet_enrichment.checks.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with out_path.open("w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2)
        except Exception:
            pass

        try:
            client.close()
        except Exception:
            pass
        return result
    except Exception as exc:
        context.log.exception(f"Company CET enrichment failed: {exc}")
        try:
            client.close()
        except Exception:
            pass
        return {"status": "error", "error": str(exc)}


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
    if CETLoader is None or CETLoaderConfig is None:
        context.log.warning("CETLoader unavailable; skipping Award CET relationships")
        return {"status": "skipped", "reason": "loader_unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "skipped", "reason": "neo4j_unavailable"}

    # Config
    award_class_parquet = Path(
        context.op_config.get("award_class_parquet") or str(DEFAULT_AWARD_CLASS_PARQUET)
    )
    award_class_json = Path(
        context.op_config.get("award_class_json") or str(DEFAULT_AWARD_CLASS_JSON)
    )
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read award classifications
    expected_cols = ("award_id", "primary_cet", "supporting_cets", "confidence", "evidence")
    classifications = _read_parquet_or_ndjson(
        award_class_parquet, award_class_json, expected_columns=expected_cols
    )
    context.log.info(f"Creating Award->CETArea relationships for {len(classifications)} awards")

    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.load_award_cet_relationships(classifications)
        result = {
            "status": "success",
            "awards": len(classifications),
            "metrics": _serialize_metrics(metrics),
        }

        # Persist a small run summary
        out_path = DEFAULT_OUTPUT_DIR / "neo4j_award_cet_relationships.checks.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with out_path.open("w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2)
        except Exception:
            pass

        try:
            client.close()
        except Exception:
            pass
        return result
    except Exception as exc:
        context.log.exception(f"Award CET relationships failed: {exc}")
        try:
            client.close()
        except Exception:
            pass
        return {"status": "error", "error": str(exc)}


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
    if CETLoader is None or CETLoaderConfig is None:
        context.log.warning("CETLoader unavailable; skipping Company CET relationships")
        return {"status": "skipped", "reason": "loader_unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "skipped", "reason": "neo4j_unavailable"}

    # Config
    company_profiles_parquet = Path(
        context.op_config.get("company_profiles_parquet") or str(DEFAULT_COMPANY_PROFILES_PARQUET)
    )
    company_profiles_json = Path(
        context.op_config.get("company_profiles_json") or str(DEFAULT_COMPANY_PROFILES_JSON)
    )
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read company profiles
    expected_cols = (
        "company_uei",
        "dominant_cet",
        "specialization_score",
        "award_count",
        "total_funding",
    )
    profiles = _read_parquet_or_ndjson(
        company_profiles_parquet, company_profiles_json, expected_columns=expected_cols
    )
    context.log.info(f"Creating Company->CETArea relationships for {len(profiles)} companies")

    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.load_company_cet_relationships(profiles)
        result = {
            "status": "success",
            "companies": len(profiles),
            "metrics": _serialize_metrics(metrics),
        }

        # Persist a small run summary
        out_path = DEFAULT_OUTPUT_DIR / "neo4j_company_cet_relationships.checks.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with out_path.open("w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2)
        except Exception:
            pass

        try:
            client.close()
        except Exception:
            pass
        return result
    except Exception as exc:
        context.log.exception(f"Company CET relationships failed: {exc}")
        try:
            client.close()
        except Exception:
            pass
        return {"status": "error", "error": str(exc)}


# ============================================================================
# Asset Aliases for Backward Compatibility
# ============================================================================

# Aliases for assets expected by __init__.py and other modules
neo4j_cetarea_nodes = loaded_cet_areas
neo4j_award_cet_enrichment = loaded_award_cet_enrichment
neo4j_company_cet_enrichment = loaded_company_cet_enrichment
neo4j_award_cet_relationships = loaded_award_cet_relationships
neo4j_company_cet_relationships = loaded_company_cet_relationships
