# sbir-etl/src/assets/cet_neo4j_loading_assets.py
"""
Dagster assets for loading CET (Critical & Emerging Technologies) nodes and enrichment
properties into Neo4j.

Implements Section 12 (Neo4j CET Graph Model - Nodes) tasks:

12.1 Create CETArea node schema
12.2 Add uniqueness constraints for CETArea
12.3 Add CETArea properties (id, name, keywords, taxonomy_version)
12.4 Create Company node CET enrichment properties
12.5 Create Award node CET enrichment properties
12.6 Add batching + idempotent merges
12.7 Unit tests (mocked Neo4j) — to be added in tests

Assets:
- neo4j_cetarea_nodes
    Loads CET taxonomy into Neo4j as CETArea nodes. Supports constraints/index creation.

- neo4j_award_cet_enrichment
    Upserts CET classification properties onto Award nodes (primary/supporting CETs).

- neo4j_company_cet_enrichment
    Upserts CET enrichment properties onto Company nodes (dominant CET, specialization).

Notes:
- Uses CETLoader (src/loaders/cet_loader.py) and Neo4jClient under the hood.
- Input assets:
    - cet_taxonomy (writes data/processed/cet_taxonomy.parquet with NDJSON fallback .json)
    - cet_award_classifications (writes data/processed/cet_award_classifications.parquet or .json)
    - cet_company_profiles (writes data/processed/cet_company_profiles.parquet or .json)
- Import-safe: gracefully degrades if optional deps are unavailable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from loguru import logger

# Dagster (import-safe wrappers)
try:
    from dagster import AssetExecutionContext, AssetIn, asset
except Exception:  # pragma: no cover - fallback stubs
    AssetExecutionContext = object  # type: ignore

    def asset(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap

    def AssetIn(*args, **kwargs):  # type: ignore
        return None


# Neo4j loader imports (import-safe)
try:
    from src.loaders.neo4j_client import Neo4jClient, Neo4jConfig, LoadMetrics  # type: ignore
except Exception:  # pragma: no cover
    Neo4jClient = None  # type: ignore
    Neo4jConfig = None  # type: ignore
    LoadMetrics = None  # type: ignore

try:
    from src.loaders.cet_loader import CETLoader, CETLoaderConfig  # type: ignore
except Exception:  # pragma: no cover
    CETLoader = None  # type: ignore
    CETLoaderConfig = None  # type: ignore

# pandas is optional for parquet reads
try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore


# ---------------------------------------------------------------------------
# Configuration Defaults
# ---------------------------------------------------------------------------

DEFAULT_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
DEFAULT_NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_TAXONOMY_PARQUET = DEFAULT_PROCESSED_DIR / "cet_taxonomy.parquet"
DEFAULT_TAXONOMY_JSON = DEFAULT_PROCESSED_DIR / "cet_taxonomy.json"

DEFAULT_AWARD_CLASS_PARQUET = DEFAULT_PROCESSED_DIR / "cet_award_classifications.parquet"
DEFAULT_AWARD_CLASS_JSON = DEFAULT_PROCESSED_DIR / "cet_award_classifications.json"

DEFAULT_COMPANY_PROFILES_PARQUET = DEFAULT_PROCESSED_DIR / "cet_company_profiles.parquet"
DEFAULT_COMPANY_PROFILES_JSON = DEFAULT_PROCESSED_DIR / "cet_company_profiles.json"

DEFAULT_OUTPUT_DIR = Path(os.environ.get("SBIR_ETL__CET__NEO4J_OUTPUT_DIR", "data/loaded/neo4j"))
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_neo4j_client() -> Optional[Neo4jClient]:
    """Create a Neo4j client if available; return None otherwise."""
    if Neo4jClient is None or Neo4jConfig is None:
        logger.warning("Neo4j loader unavailable; skipping Neo4j operations")
        return None
    try:
        config = Neo4jConfig(
            uri=DEFAULT_NEO4J_URI,
            username=DEFAULT_NEO4J_USER,
            password=DEFAULT_NEO4J_PASSWORD,
            database=DEFAULT_NEO4J_DATABASE,
        )
        return Neo4jClient(config)
    except Exception as exc:
        logger.exception("Failed to create Neo4j client: {}", exc)
        return None


def _read_parquet_or_ndjson(
    parquet_path: Path, json_path: Path, expected_columns: Optional[Iterable[str]] = None
) -> List[Dict[str, Any]]:
    """
    Read a DataFrame from parquet if possible; fallback to NDJSON (.json) lines.

    Returns list of dicts (records). If neither file exists, returns [].
    """
    records: List[Dict[str, Any]] = []

    # Prefer parquet
    if parquet_path.exists() and pd is not None:
        try:
            df = pd.read_parquet(parquet_path)
            # Filter to expected columns if provided (best-effort)
            if expected_columns and isinstance(df, pd.DataFrame):
                cols = [c for c in expected_columns if c in df.columns]
                if cols:
                    df = df[cols]
            return df.fillna(value=pd.NA).replace({pd.NA: None}).to_dict(orient="records")  # type: ignore
        except Exception as exc:
            logger.warning(
                "Failed to read parquet {}; trying NDJSON fallback: {}", parquet_path, exc
            )

    # Fallback: NDJSON (.json lines)
    if json_path.exists():
        try:
            with json_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if expected_columns:
                            obj = {k: obj.get(k) for k in expected_columns}
                        records.append(obj)
                    except Exception:
                        # ignore malformed lines
                        continue
            return records
        except Exception as exc:
            logger.exception("Failed to read NDJSON {}: {}", json_path, exc)

    return records


def _flatten_award_class_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a single row from cet_award_classifications into an award CET enrichment dict.

    Expected fields in row:
        - award_id: str
        - primary_cet: str (cet_id)
        - primary_score: float
        - supporting_cets: list[{'cet_id': str, 'score': float, 'classification': str}]
        - classified_at: ISO str
        - taxonomy_version: str
    """
    award_id = str(row.get("award_id") or "").strip()
    primary_id = str(row.get("primary_cet") or "").strip()
    primary_score = row.get("primary_score")
    classified_at = row.get("classified_at")
    taxonomy_version = row.get("taxonomy_version")

    supporting_ids: List[str] = []
    supp = row.get("supporting_cets")
    if isinstance(supp, list):
        for s in supp:
            try:
                cid = str((s or {}).get("cet_id") or "").strip()
                if cid:
                    supporting_ids.append(cid)
            except Exception:
                continue

    out = {
        "award_id": award_id,
        "cet_primary_id": primary_id if primary_id else None,
        "cet_primary_score": float(primary_score) if primary_score is not None else None,
        "cet_supporting_ids": supporting_ids,
        "cet_classified_at": str(classified_at) if classified_at else None,
        "cet_taxonomy_version": str(taxonomy_version) if taxonomy_version else None,
    }
    return out


def _flatten_company_profile(row: Dict[str, Any], key_property: str) -> Dict[str, Any]:
    """
    Convert a single row from cet_company_profiles into a company CET enrichment dict.

    Common fields in row:
        - company_id: str (internal id)
        - company_name: str
        - dominant_cet: str
        - dominant_score: float
        - specialization_score: float (0..1)
        - cet_scores: dict[str->float] (ignored in enrichment)
        - first_award_date, last_award_date (ignored)
    """
    key_val = str(row.get(key_property) or "").strip()
    out = {
        key_property: key_val if key_val else None,
        "cet_dominant_id": (str(row.get("dominant_cet")) or "").strip() or None,
        "cet_dominant_score": float(row.get("dominant_score"))
        if row.get("dominant_score") is not None
        else None,
        "cet_specialization_score": float(row.get("specialization_score"))
        if row.get("specialization_score") is not None
        else None,
        # If taxonomy version is present in profile rows, propagate (optional)
        "cet_taxonomy_version": str(row.get("taxonomy_version"))
        if row.get("taxonomy_version")
        else None,
    }
    return out


def _serialize_metrics(metrics: Optional[LoadMetrics]) -> Dict[str, Any]:
    if metrics is None:
        return {"nodes_created": {}, "nodes_updated": {}, "relationships_created": {}, "errors": 0}
    return {
        "nodes_created": getattr(metrics, "nodes_created", {}),
        "nodes_updated": getattr(metrics, "nodes_updated", {}),
        "relationships_created": getattr(metrics, "relationships_created", {}),
        "errors": getattr(metrics, "errors", 0),
    }


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


@asset(
    name="neo4j_cetarea_nodes",
    description="Load CETArea nodes into Neo4j from CET taxonomy artifact.",
    group_name="neo4j_cet",
    ins={"cet_taxonomy": AssetIn()},
    config_schema={
        "create_constraints": {"type": bool, "default": True},
        "create_indexes": {"type": bool, "default": True},
        "taxonomy_parquet": {"type": str, "default": str(DEFAULT_TAXONOMY_PARQUET)},
        "taxonomy_json": {"type": str, "default": str(DEFAULT_TAXONOMY_JSON)},
        "batch_size": {"type": int, "default": 1000},
    },
)
def neo4j_cetarea_nodes(context: AssetExecutionContext, cet_taxonomy) -> Dict[str, Any]:
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
        return {"status": "failed", "reason": str(exc)}


@asset(
    name="neo4j_award_cet_enrichment",
    description="Upsert CET enrichment properties onto Award nodes from award classifications artifact.",
    group_name="neo4j_cet",
    ins={
        "cet_award_classifications": AssetIn(),
        "neo4j_cetarea_nodes": AssetIn(),  # ensure taxonomy nodes exist first
    },
    config_schema={
        "classifications_parquet": {"type": str, "default": str(DEFAULT_AWARD_CLASS_PARQUET)},
        "classifications_json": {"type": str, "default": str(DEFAULT_AWARD_CLASS_JSON)},
        "batch_size": {"type": int, "default": 1000},
    },
)
def neo4j_award_cet_enrichment(
    context: AssetExecutionContext,
    cet_award_classifications,
    neo4j_cetarea_nodes,
) -> Dict[str, Any]:
    """Upsert Award.cet_* enrichment properties."""
    if CETLoader is None or CETLoaderConfig is None:
        context.log.warning("CETLoader unavailable; skipping Award CET enrichment")
        return {"status": "skipped", "reason": "loader_unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "skipped", "reason": "neo4j_unavailable"}

    classifications_parquet = Path(
        context.op_config.get("classifications_parquet") or str(DEFAULT_AWARD_CLASS_PARQUET)
    )
    classifications_json = Path(
        context.op_config.get("classifications_json") or str(DEFAULT_AWARD_CLASS_JSON)
    )
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read award classifications
    expected_cols = (
        "award_id",
        "primary_cet",
        "primary_score",
        "supporting_cets",
        "classified_at",
        "taxonomy_version",
    )
    rows = _read_parquet_or_ndjson(
        classifications_parquet, classifications_json, expected_columns=expected_cols
    )

    enrichments: List[Dict[str, Any]] = []
    for r in rows:
        e = _flatten_award_class_row(r)
        if e.get("award_id"):
            enrichments.append(e)

    context.log.info(f"Prepared Award CET enrichments: {len(enrichments)}")

    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.upsert_award_cet_enrichment(enrichments, key_property="award_id")
        result = {
            "status": "success",
            "awards": len(enrichments),
            "metrics": _serialize_metrics(metrics),
        }

        out_path = DEFAULT_OUTPUT_DIR / "neo4j_award_cet_enrichment.checks.json"
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
        return {"status": "failed", "reason": str(exc)}


@asset(
    name="neo4j_company_cet_enrichment",
    description="Upsert CET enrichment properties onto Company nodes from company CET profiles.",
    group_name="neo4j_cet",
    ins={
        "cet_company_profiles": AssetIn(),
        "neo4j_cetarea_nodes": AssetIn(),  # ensure taxonomy nodes exist first
    },
    config_schema={
        "profiles_parquet": {"type": str, "default": str(DEFAULT_COMPANY_PROFILES_PARQUET)},
        "profiles_json": {"type": str, "default": str(DEFAULT_COMPANY_PROFILES_JSON)},
        "key_property": {
            "type": str,
            "default": "uei",
            "description": "Company key to match on in Neo4j (e.g., 'uei' or 'company_id').",
        },
        "batch_size": {"type": int, "default": 1000},
    },
)
def neo4j_company_cet_enrichment(
    context: AssetExecutionContext,
    cet_company_profiles,
    neo4j_cetarea_nodes,
) -> Dict[str, Any]:
    """Upsert Company.cet_* enrichment properties."""
    if CETLoader is None or CETLoaderConfig is None:
        context.log.warning("CETLoader unavailable; skipping Company CET enrichment")
        return {"status": "skipped", "reason": "loader_unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "skipped", "reason": "neo4j_unavailable"}

    profiles_parquet = Path(
        context.op_config.get("profiles_parquet") or str(DEFAULT_COMPANY_PROFILES_PARQUET)
    )
    profiles_json = Path(
        context.op_config.get("profiles_json") or str(DEFAULT_COMPANY_PROFILES_JSON)
    )
    key_property = str(context.op_config.get("key_property") or "uei").strip() or "uei"
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read company profiles (beware key presence)
    expected_cols = (
        key_property,
        "company_id",
        "dominant_cet",
        "dominant_score",
        "specialization_score",
        "taxonomy_version",
    )
    rows = _read_parquet_or_ndjson(profiles_parquet, profiles_json, expected_columns=expected_cols)

    # If configured key_property not in rows, fallback to 'company_id' (best-effort)
    have_key = any((r.get(key_property) for r in rows))
    if not have_key:
        context.log.warning(
            f"No values found for key_property '{key_property}', falling back to 'company_id'"
        )
        key_property = "company_id"

    enrichments: List[Dict[str, Any]] = []
    for r in rows:
        e = _flatten_company_profile(r, key_property=key_property)
        if e.get(key_property):
            enrichments.append(e)

    context.log.info(f"Prepared Company CET enrichments: {len(enrichments)} (key={key_property})")

    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.upsert_company_cet_enrichment(enrichments, key_property=key_property)
        result = {
            "status": "success",
            "companies": len(enrichments),
            "key_property": key_property,
            "metrics": _serialize_metrics(metrics),
        }

        out_path = DEFAULT_OUTPUT_DIR / "neo4j_company_cet_enrichment.checks.json"
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
        return {"status": "failed", "reason": str(exc)}


@asset(
    name="neo4j_award_cet_relationships",
    description="Create Award -> CETArea relationships from award classifications.",
    group_name="neo4j_cet",
    ins={
        "cet_award_classifications": AssetIn(),
        "neo4j_cetarea_nodes": AssetIn(),  # ensure taxonomy nodes exist first
    },
    config_schema={
        "classifications_parquet": {"type": str, "default": str(DEFAULT_AWARD_CLASS_PARQUET)},
        "classifications_json": {"type": str, "default": str(DEFAULT_AWARD_CLASS_JSON)},
        "rel_type": {"type": str, "default": "APPLICABLE_TO"},
        "batch_size": {"type": int, "default": 1000},
    },
)
def neo4j_award_cet_relationships(
    context: AssetExecutionContext,
    cet_award_classifications,
    neo4j_cetarea_nodes,
) -> Dict[str, Any]:
    """
    Create Award -> CETArea relationships with MERGE semantics from cet_award_classifications.

    Relationship schema:
      (a:Award)-[:APPLICABLE_TO {
          score: FLOAT,
          primary: BOOLEAN,
          role: 'PRIMARY' | 'SUPPORTING',
          rationale: STRING,
          classified_at: STRING,
          taxonomy_version: STRING
      }]->(c:CETArea)
    """
    if CETLoader is None or CETLoaderConfig is None:
        context.log.warning("CETLoader unavailable; skipping Award->CET relationships")
        return {"status": "skipped", "reason": "loader_unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "skipped", "reason": "neo4j_unavailable"}

    classifications_parquet = Path(
        context.op_config.get("classifications_parquet") or str(DEFAULT_AWARD_CLASS_PARQUET)
    )
    classifications_json = Path(
        context.op_config.get("classifications_json") or str(DEFAULT_AWARD_CLASS_JSON)
    )
    rel_type = str(context.op_config.get("rel_type") or "APPLICABLE_TO").strip() or "APPLICABLE_TO"
    batch_size = int(context.op_config.get("batch_size", 1000))

    # Read award classifications including evidence for rationale extraction
    expected_cols = (
        "award_id",
        "primary_cet",
        "primary_score",
        "supporting_cets",
        "classified_at",
        "taxonomy_version",
        "evidence",
    )
    rows = _read_parquet_or_ndjson(
        classifications_parquet, classifications_json, expected_columns=expected_cols
    )

    context.log.info(f"Read {len(rows)} award classification rows for relationship creation")

    try:
        loader = CETLoader(client, CETLoaderConfig(batch_size=batch_size))
        metrics = loader.create_award_cet_relationships(rows, rel_type=rel_type)
        result = {
            "status": "success",
            "relationships_type": rel_type,
            "input_rows": len(rows),
            "metrics": _serialize_metrics(metrics),
        }

        out_path = DEFAULT_OUTPUT_DIR / "neo4j_award_cet_relationships.checks.json"
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
        context.log.exception(f"Award->CET relationships failed: {exc}")
        try:
            client.close()
        except Exception:
            pass
        return {"status": "failed", "reason": str(exc)}
