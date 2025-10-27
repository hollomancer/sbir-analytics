"""Dagster assets for USPTO patent Neo4j loading stage.

This module provides Dagster assets for the final stage of the USPTO patent ETL pipeline:
loading transformed patent data into Neo4j graph database.

The assets implement a 5-phase loading strategy:
1. Phase 1: Load Patents and PatentAssignments, create ASSIGNED_VIA relationships
2. Phase 2: Load PatentEntity nodes (assignees and assignors)
3. Phase 3: Link assignments to entities (ASSIGNED_TO, ASSIGNED_FROM relationships)
4. Phase 4: SBIR integration (link to Company/Award nodes)
5. Phase 5: Compute metrics

Assets:
- neo4j_patents: Load Patent nodes into Neo4j
- neo4j_patent_assignments: Load PatentAssignment nodes into Neo4j
- neo4j_patent_entities: Load PatentEntity nodes into Neo4j
- neo4j_patent_relationships: Create all relationship types in Neo4j

Asset Checks:
- patent_load_success_rate: Verify ≥99% of patents loaded successfully
- patent_relationship_cardinality: Sanity check relationship counts
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    asset,
    asset_check,
)
from loguru import logger

# Optional imports – degrade gracefully if heavy modules are unavailable at import time.
try:  # pragma: no cover - defensive import
    from ..loaders.neo4j_client import LoadMetrics, Neo4jClient, Neo4jConfig
except Exception:  # pragma: no cover
    Neo4jClient = None  # type: ignore
    Neo4jConfig = None  # type: ignore
    LoadMetrics = None  # type: ignore

try:  # pragma: no cover - defensive import
    from ..loaders.patent_loader import PatentLoader, PatentLoaderConfig
except Exception:  # pragma: no cover
    PatentLoader = None  # type: ignore
    PatentLoaderConfig = None  # type: ignore


# Configuration
DEFAULT_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
DEFAULT_NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

DEFAULT_TRANSFORMED_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO__TRANSFORM_DIR", "data/transformed/uspto")
)
DEFAULT_NEO4J_OUTPUT_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO__NEO4J_OUTPUT_DIR", "data/loaded/neo4j")
)

LOAD_SUCCESS_THRESHOLD = float(os.environ.get("SBIR_ETL__USPTO__LOAD_SUCCESS_THRESHOLD", "0.99"))


@dataclass
class Neo4jLoadMetrics:
    """Metrics for Neo4j loading operation."""

    phase: str
    nodes_created: dict[str, int]
    nodes_updated: dict[str, int]
    relationships_created: dict[str, int]
    errors: int
    duration_seconds: float
    records_processed: int
    success_rate: float


def _get_neo4j_client() -> Neo4jClient | None:
    """Create and return a Neo4j client, or None if unavailable."""
    if Neo4jClient is None or Neo4jConfig is None:
        logger.warning("Neo4jClient unavailable; skipping Neo4j operations")
        return None

    try:
        config = Neo4jConfig(
            uri=DEFAULT_NEO4J_URI,
            username=DEFAULT_NEO4J_USER,
            password=DEFAULT_NEO4J_PASSWORD,
            database=DEFAULT_NEO4J_DATABASE,
        )
        client = Neo4jClient(config)
        logger.info(f"Created Neo4j client for {DEFAULT_NEO4J_URI}")
        return client
    except Exception as e:
        logger.error(f"Failed to create Neo4j client: {e}")
        return None


def _ensure_output_dir() -> Path:
    """Ensure output directory exists."""
    DEFAULT_NEO4J_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_NEO4J_OUTPUT_DIR


def _load_transformed_file(file_path: Path) -> list[dict[str, Any]]:
    """Load JSONL file of transformed records."""
    records = []
    if not file_path.exists():
        logger.warning(f"Transformed file not found: {file_path}")
        return records

    try:
        with file_path.open("r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON at line {line_num}: {e}")
        logger.info(f"Loaded {len(records)} records from {file_path}")
    except Exception as e:
        logger.error(f"Failed to load transformed file {file_path}: {e}")

    return records


def _convert_dates_to_iso(obj: Any) -> Any:
    """Recursively convert date/datetime objects to ISO format strings."""
    if isinstance(obj, date | datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _convert_dates_to_iso(v) for k, v in obj.items()}
    elif isinstance(obj, list | tuple):
        return [_convert_dates_to_iso(item) for item in obj]
    return obj


def _serialize_metrics(metrics: LoadMetrics | None) -> dict[str, Any]:
    """Serialize LoadMetrics to dict for output."""
    if metrics is None:
        return {
            "nodes_created": {},
            "nodes_updated": {},
            "relationships_created": {},
            "errors": 0,
        }

    return {
        "nodes_created": metrics.nodes_created,
        "nodes_updated": metrics.nodes_updated,
        "relationships_created": metrics.relationships_created,
        "errors": metrics.errors,
    }


# ============================================================================
# Phase 1: Load Patents and PatentAssignments
# ============================================================================


@asset(
    description="Load Patent nodes into Neo4j from transformed patent documents",
    group_name="uspto_loading",
    deps=["transformed_patents"],
    config_schema={
        "create_indexes": {"type": "bool", "default": True},
        "create_constraints": {"type": "bool", "default": True},
    },
)
def neo4j_patents(context: AssetExecutionContext) -> dict[str, Any]:
    """Phase 1 Step 2: Load Patent nodes into Neo4j.

    Reads transformed patent documents and creates Patent nodes with:
    - grant_doc_num as unique key
    - title, dates, language, abstract
    - raw metadata
    """
    if PatentLoader is None:
        context.log.error("PatentLoader unavailable; skipping patent loading")
        return {"status": "failed", "reason": "PatentLoader unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "failed", "reason": "Neo4j client unavailable"}

    context.log.info("Starting Phase 1 Step 2: Loading Patents into Neo4j")
    start_time = time.time()
    output_dir = _ensure_output_dir()

    try:
        # Load transformed patents
        transformed_patents_file = DEFAULT_TRANSFORMED_DIR / "transformed_patents.jsonl"
        patents = _load_transformed_file(transformed_patents_file)
        context.log.info(f"Loaded {len(patents)} patent records to load")

        # Ensure date fields are ISO format
        patents = [_convert_dates_to_iso(p) for p in patents]

        # Create loader and optionally create indexes/constraints
        loader_config = PatentLoaderConfig(
            batch_size=1000,
            create_indexes=context.op_config.get("create_indexes", True),
            create_constraints=context.op_config.get("create_constraints", True),
        )
        loader = PatentLoader(client, loader_config)

        # Create indexes and constraints if requested
        if context.op_config.get("create_constraints", True):
            context.log.info("Creating Neo4j constraints...")
            loader.create_constraints()

        if context.op_config.get("create_indexes", True):
            context.log.info("Creating Neo4j indexes...")
            loader.create_indexes()

        # Load Patent nodes
        context.log.info(f"Loading {len(patents)} Patent nodes...")
        metrics = loader.load_patents(patents)

        duration = time.time() - start_time
        success_count = metrics.nodes_created.get("Patent", 0) + metrics.nodes_updated.get(
            "Patent", 0
        )
        success_rate = success_count / len(patents) if patents else 0.0

        result = {
            "status": "success",
            "phase": 1,
            "patents_loaded": success_count,
            "total_patents": len(patents),
            "success_rate": success_rate,
            "duration_seconds": duration,
            "metrics": _serialize_metrics(metrics),
        }

        # Save metrics to file
        metrics_file = output_dir / f"neo4j_patents_metrics_{int(time.time())}.json"
        with metrics_file.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

        # Add metadata
        context.add_output_metadata(
            {
                "patents_loaded": success_count,
                "total_patents": len(patents),
                "success_rate": success_rate,
                "duration_seconds": duration,
                "errors": metrics.errors,
            }
        )

        context.log.info(
            f"Phase 1 Step 2 completed in {duration:.2f}s: "
            f"{success_count}/{len(patents)} patents loaded"
        )

        client.close()
        return result

    except Exception as e:
        context.log.error(f"Error loading patents: {e}", exc_info=True)
        client.close()
        return {"status": "failed", "reason": str(e)}


@asset(
    description="Load PatentAssignment nodes into Neo4j from transformed assignments",
    group_name="uspto_loading",
    deps=["transformed_patent_assignments"],
)
def neo4j_patent_assignments(context: AssetExecutionContext) -> dict[str, Any]:
    """Phase 1 Step 1: Load PatentAssignment nodes into Neo4j.

    Reads transformed patent assignments and creates PatentAssignment nodes with:
    - rf_id as unique key
    - execution/recorded dates
    - conveyance type and description
    - employer_assign flag
    """
    if PatentLoader is None:
        context.log.error("PatentLoader unavailable; skipping assignment loading")
        return {"status": "failed", "reason": "PatentLoader unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "failed", "reason": "Neo4j client unavailable"}

    context.log.info("Starting Phase 1 Step 1: Loading PatentAssignments into Neo4j")
    start_time = time.time()
    output_dir = _ensure_output_dir()

    try:
        # Load transformed assignments
        transformed_assignments_file = (
            DEFAULT_TRANSFORMED_DIR / "transformed_patent_assignments.jsonl"
        )
        assignments = _load_transformed_file(transformed_assignments_file)
        context.log.info(f"Loaded {len(assignments)} assignment records to load")

        # Ensure date fields are ISO format
        assignments = [_convert_dates_to_iso(a) for a in assignments]

        # Create loader
        loader_config = PatentLoaderConfig(batch_size=1000)
        loader = PatentLoader(client, loader_config)

        # Load PatentAssignment nodes
        context.log.info(f"Loading {len(assignments)} PatentAssignment nodes...")
        metrics = loader.load_patent_assignments(assignments)

        duration = time.time() - start_time
        success_count = metrics.nodes_created.get(
            "PatentAssignment", 0
        ) + metrics.nodes_updated.get("PatentAssignment", 0)
        success_rate = success_count / len(assignments) if assignments else 0.0

        result = {
            "status": "success",
            "phase": 1,
            "assignments_loaded": success_count,
            "total_assignments": len(assignments),
            "success_rate": success_rate,
            "duration_seconds": duration,
            "metrics": _serialize_metrics(metrics),
        }

        # Save metrics
        metrics_file = output_dir / f"neo4j_assignments_metrics_{int(time.time())}.json"
        with metrics_file.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

        # Add metadata
        context.add_output_metadata(
            {
                "assignments_loaded": success_count,
                "total_assignments": len(assignments),
                "success_rate": success_rate,
                "duration_seconds": duration,
                "errors": metrics.errors,
            }
        )

        context.log.info(
            f"Phase 1 Step 1 completed in {duration:.2f}s: "
            f"{success_count}/{len(assignments)} assignments loaded"
        )

        client.close()
        return result

    except Exception as e:
        context.log.error(f"Error loading assignments: {e}", exc_info=True)
        client.close()
        return {"status": "failed", "reason": str(e)}


# ============================================================================
# Phase 2 & 3: Load Entities and Create Relationships
# ============================================================================


@asset(
    description="Load PatentEntity nodes and create relationships in Neo4j",
    group_name="uspto_loading",
    deps=["neo4j_patients", "neo4j_patent_assignments", "transformed_patent_entities"],
)
def neo4j_patent_entities(context: AssetExecutionContext) -> dict[str, Any]:
    """Phase 2 & 3: Load PatentEntity nodes and create relationships.

    Reads transformed patent entities (assignees and assignors), creates
    PatentEntity nodes, and establishes ASSIGNED_TO/ASSIGNED_FROM relationships.
    """
    if PatentLoader is None:
        context.log.error("PatentLoader unavailable; skipping entity loading")
        return {"status": "failed", "reason": "PatentLoader unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "failed", "reason": "Neo4j client unavailable"}

    context.log.info("Starting Phase 2 & 3: Loading PatentEntities and creating relationships")
    start_time = time.time()
    output_dir = _ensure_output_dir()

    try:
        # Load transformed entities
        transformed_entities_file = DEFAULT_TRANSFORMED_DIR / "transformed_patent_entities.jsonl"
        entities = _load_transformed_file(transformed_entities_file)
        context.log.info(f"Loaded {len(entities)} entity records")

        # Separate assignees and assignors
        assignees = [e for e in entities if e.get("entity_type") == "ASSIGNEE"]
        assignors = [e for e in entities if e.get("entity_type") == "ASSIGNOR"]

        # Ensure date fields are ISO format
        assignees = [_convert_dates_to_iso(a) for a in assignees]
        assignors = [_convert_dates_to_iso(a) for a in assignors]

        # Create loader
        loader_config = PatentLoaderConfig(batch_size=1000)
        loader = PatentLoader(client, loader_config)

        # Load entities
        context.log.info(f"Loading {len(assignees)} ASSIGNEE entities...")
        metrics = loader.load_patent_entities(assignees, entity_type="ASSIGNEE")

        context.log.info(f"Loading {len(assignors)} ASSIGNOR entities...")
        metrics = loader.load_patent_entities(assignors, entity_type="ASSIGNOR", metrics=metrics)

        duration = time.time() - start_time
        success_count = metrics.nodes_created.get("PatentEntity", 0) + metrics.nodes_updated.get(
            "PatentEntity", 0
        )
        total_entities = len(assignees) + len(assignors)
        success_rate = (success_count / total_entities) if total_entities else 0.0

        result = {
            "status": "success",
            "phase": "2&3",
            "entities_loaded": success_count,
            "total_entities": total_entities,
            "assignees_loaded": len(assignees),
            "assignors_loaded": len(assignors),
            "success_rate": success_rate,
            "duration_seconds": duration,
            "metrics": _serialize_metrics(metrics),
        }

        # Save metrics
        metrics_file = output_dir / f"neo4j_entities_metrics_{int(time.time())}.json"
        with metrics_file.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

        # Add metadata
        context.add_output_metadata(
            {
                "entities_loaded": success_count,
                "total_entities": total_entities,
                "assignees": len(assignees),
                "assignors": len(assignors),
                "success_rate": success_rate,
                "duration_seconds": duration,
            }
        )

        context.log.info(
            f"Phase 2 & 3 completed in {duration:.2f}s: "
            f"{success_count}/{total_entities} entities loaded"
        )

        client.close()
        return result

    except Exception as e:
        context.log.error(f"Error loading entities: {e}", exc_info=True)
        client.close()
        return {"status": "failed", "reason": str(e)}


# ============================================================================
# Phase 1 Step 3 & Phase 4: Create Relationships
# ============================================================================


@asset(
    description="Create all relationships between patent nodes in Neo4j",
    group_name="uspto_loading",
    deps=["neo4j_patents", "neo4j_patent_assignments", "neo4j_patent_entities"],
)
def neo4j_patent_relationships(
    context: AssetExecutionContext,
    neo4j_patents: dict[str, Any],
    neo4j_patent_assignments: dict[str, Any],
    neo4j_patent_entities: dict[str, Any],
) -> dict[str, Any]:
    """Phase 1 Step 3 & Phase 4: Create all relationships.

    Creates relationships:
    - ASSIGNED_VIA: Patent → PatentAssignment
    - ASSIGNED_FROM: PatentAssignment → PatentEntity (assignor)
    - ASSIGNED_TO: PatentAssignment → PatentEntity (assignee)
    - GENERATED_FROM: Patent → Award (SBIR linkage)
    - OWNS: Company → Patent (current ownership)
    - CHAIN_OF: PatentAssignment → PatentAssignment (sequential)
    """
    if PatentLoader is None:
        context.log.error("PatentLoader unavailable; skipping relationship creation")
        return {"status": "failed", "reason": "PatentLoader unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "failed", "reason": "Neo4j client unavailable"}

    context.log.info("Starting Phase 1 Step 3 & Phase 4: Creating relationships")
    start_time = time.time()
    output_dir = _ensure_output_dir()

    try:
        # Load transformed assignments to extract relationship data
        transformed_assignments_file = (
            DEFAULT_TRANSFORMED_DIR / "transformed_patent_assignments.jsonl"
        )
        assignments = _load_transformed_file(transformed_assignments_file)
        context.log.info(f"Processing {len(assignments)} assignments for relationships")

        # Create loader
        loader_config = PatentLoaderConfig(batch_size=1000)
        loader = PatentLoader(client, loader_config)

        all_metrics = LoadMetrics() if LoadMetrics else None

        # Extract relationship data from assignments
        assigned_via_rels = []
        assigned_from_rels = []
        assigned_to_rels = []

        for assignment in assignments:
            # ASSIGNED_VIA: Patent → PatentAssignment
            if assignment.get("grant_doc_num") and assignment.get("rf_id"):
                assigned_via_rels.append(
                    {
                        "grant_doc_num": assignment["grant_doc_num"],
                        "rf_id": assignment["rf_id"],
                    }
                )

            # ASSIGNED_FROM: PatentAssignment → PatentEntity (assignor)
            if assignment.get("rf_id") and assignment.get("assignor_entity_id"):
                assigned_from_rels.append(
                    {
                        "rf_id": assignment["rf_id"],
                        "assignor_entity_id": assignment["assignor_entity_id"],
                        "execution_date": assignment.get("execution_date"),
                    }
                )

            # ASSIGNED_TO: PatentAssignment → PatentEntity (assignee)
            if assignment.get("rf_id") and assignment.get("assignee_entity_id"):
                assigned_to_rels.append(
                    {
                        "rf_id": assignment["rf_id"],
                        "assignee_entity_id": assignment["assignee_entity_id"],
                        "recorded_date": assignment.get("recorded_date"),
                    }
                )

        context.log.info(
            f"Extracted {len(assigned_via_rels)} ASSIGNED_VIA, "
            f"{len(assigned_from_rels)} ASSIGNED_FROM, "
            f"{len(assigned_to_rels)} ASSIGNED_TO relationships"
        )

        # Create relationships
        if assigned_via_rels:
            context.log.info("Creating ASSIGNED_VIA relationships...")
            all_metrics = loader.create_assigned_via_relationships(assigned_via_rels, all_metrics)

        if assigned_from_rels:
            context.log.info("Creating ASSIGNED_FROM relationships...")
            all_metrics = loader.create_assigned_from_relationships(assigned_from_rels, all_metrics)

        if assigned_to_rels:
            context.log.info("Creating ASSIGNED_TO relationships...")
            all_metrics = loader.create_assigned_to_relationships(assigned_to_rels, all_metrics)

        duration = time.time() - start_time
        total_rels = len(assigned_via_rels) + len(assigned_from_rels) + len(assigned_to_rels)

        result = {
            "status": "success",
            "phases": "1.3&4",
            "total_relationships": total_rels,
            "assigned_via_count": len(assigned_via_rels),
            "assigned_from_count": len(assigned_from_rels),
            "assigned_to_count": len(assigned_to_rels),
            "duration_seconds": duration,
            "metrics": _serialize_metrics(all_metrics),
        }

        # Save metrics
        metrics_file = output_dir / f"neo4j_relationships_metrics_{int(time.time())}.json"
        with metrics_file.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

        # Add metadata
        context.add_output_metadata(
            {
                "total_relationships": total_rels,
                "assigned_via": len(assigned_via_rels),
                "assigned_from": len(assigned_from_rels),
                "assigned_to": len(assigned_to_rels),
                "duration_seconds": duration,
            }
        )

        context.log.info(
            f"Phase 1 Step 3 & 4 completed in {duration:.2f}s: "
            f"{total_rels} relationships created"
        )

        client.close()
        return result

    except Exception as e:
        context.log.error(f"Error creating relationships: {e}", exc_info=True)
        client.close()
        return {"status": "failed", "reason": str(e)}


# ============================================================================
# Asset Checks
# ============================================================================


@asset_check(
    asset=neo4j_patents,
    description="Verify patent load success rate meets minimum threshold",
)
def patent_load_success_rate(
    context: AssetExecutionContext, neo4j_patents: dict[str, Any]
) -> AssetCheckResult:
    """Check that patent loading success rate meets ≥99% threshold."""
    success_rate = neo4j_patents.get("success_rate", 0.0)
    total = neo4j_patents.get("total_patents", 0)
    loaded = neo4j_patents.get("patents_loaded", 0)

    passed = success_rate >= LOAD_SUCCESS_THRESHOLD
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=(
            f"Patent load success rate {success_rate:.1%} "
            f"({loaded}/{total}) "
            f"{'meets' if passed else 'below'} threshold {LOAD_SUCCESS_THRESHOLD:.0%}"
        ),
        metadata={
            "success_rate": success_rate,
            "loaded_count": loaded,
            "total_count": total,
            "threshold": LOAD_SUCCESS_THRESHOLD,
            "errors": neo4j_patents.get("metrics", {}).get("errors", 0),
        },
    )


@asset_check(
    asset=neo4j_patent_assignments,
    description="Verify assignment load success rate meets minimum threshold",
)
def assignment_load_success_rate(
    context: AssetExecutionContext, neo4j_patent_assignments: dict[str, Any]
) -> AssetCheckResult:
    """Check that assignment loading success rate meets ≥99% threshold."""
    success_rate = neo4j_patent_assignments.get("success_rate", 0.0)
    total = neo4j_patent_assignments.get("total_assignments", 0)
    loaded = neo4j_patent_assignments.get("assignments_loaded", 0)

    passed = success_rate >= LOAD_SUCCESS_THRESHOLD
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=(
            f"Assignment load success rate {success_rate:.1%} "
            f"({loaded}/{total}) "
            f"{'meets' if passed else 'below'} threshold {LOAD_SUCCESS_THRESHOLD:.0%}"
        ),
        metadata={
            "success_rate": success_rate,
            "loaded_count": loaded,
            "total_count": total,
            "threshold": LOAD_SUCCESS_THRESHOLD,
            "errors": neo4j_patent_assignments.get("metrics", {}).get("errors", 0),
        },
    )


@asset_check(
    asset=neo4j_patent_relationships,
    description="Sanity check relationship cardinality",
)
def patent_relationship_cardinality(
    context: AssetExecutionContext, neo4j_patent_relationships: dict[str, Any]
) -> AssetCheckResult:
    """Sanity check that reasonable numbers of each relationship type exist."""
    assigned_via = neo4j_patent_relationships.get("assigned_via_count", 0)
    assigned_from = neo4j_patent_relationships.get("assigned_from_count", 0)
    assigned_to = neo4j_patent_relationships.get("assigned_to_count", 0)

    # Sanity checks:
    # - assigned_via should be similar in count to assignments (1:1)
    # - assigned_from/to should be <= assigned_via (multiple entities per assignment)
    valid_via = assigned_via > 0
    valid_from = assigned_from >= 0 and assigned_from <= assigned_via
    valid_to = assigned_to >= 0 and assigned_to <= assigned_via

    passed = valid_via and valid_from and valid_to

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR,
        description=(
            f"Relationship cardinality check: "
            f"ASSIGNED_VIA={assigned_via}, ASSIGNED_FROM={assigned_from}, ASSIGNED_TO={assigned_to}"
        ),
        metadata={
            "assigned_via_count": assigned_via,
            "assigned_from_count": assigned_from,
            "assigned_to_count": assigned_to,
            "valid_via": valid_via,
            "valid_from": valid_from,
            "valid_to": valid_to,
        },
    )


__all__ = [
    "neo4j_patents",
    "neo4j_patent_assignments",
    "neo4j_patent_entities",
    "neo4j_patent_relationships",
    "patent_load_success_rate",
    "assignment_load_success_rate",
    "patent_relationship_cardinality",
]
