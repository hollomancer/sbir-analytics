"""Dagster assets for Transition Detection Neo4j loading stage (Tasks 13, 14).

This module provides Dagster assets for loading transition detection results into
Neo4j graph database, including:
- Transition nodes with detection metadata
- Relationships: TRANSITIONED_TO (Award→Transition), RESULTED_IN (Transition→Contract),
  ENABLED_BY (Transition→Patent), INVOLVES_TECHNOLOGY (Transition→CETArea)

Assets:
- neo4j_transitions: Load Transition nodes
- transition_node_count_check: Verify transition node load success (13.6)
- neo4j_transition_relationships: Create transition relationships (14.8)
- transition_relationships_check: Verify relationship creation (14.8)
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import pandas as pd
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    Output,
    asset,
    asset_check,
)
from loguru import logger

# Optional imports – degrade gracefully if heavy modules unavailable at import time
try:  # pragma: no cover
    from neo4j import Driver
    from ..loaders.neo4j_client import Neo4jClient, Neo4jConfig
except Exception:  # pragma: no cover
    Driver = None  # type: ignore
    Neo4jClient = None  # type: ignore
    Neo4jConfig = None  # type: ignore

try:  # pragma: no cover
    from ..loaders.transition_loader import TransitionLoader, TransitionProfileLoader
except Exception:  # pragma: no cover
    TransitionLoader = None  # type: ignore
    TransitionProfileLoader = None  # type: ignore


# Configuration
DEFAULT_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
DEFAULT_NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

DEFAULT_NEO4J_OUTPUT_DIR = Path(
    os.environ.get("SBIR_ETL__TRANSITION__NEO4J_OUTPUT_DIR", "data/loaded/neo4j")
)

TRANSITION_LOAD_SUCCESS_THRESHOLD = float(
    os.environ.get("SBIR_ETL__TRANSITION__NEO4J_LOAD_SUCCESS_THRESHOLD", "0.99")
)
TRANSITION_MIN_NODE_COUNT = int(os.environ.get("SBIR_ETL__TRANSITION__NEO4J_MIN_NODES", "1"))


def _get_neo4j_driver() -> Driver | None:
    """Create and return a Neo4j driver, or None if unavailable."""
    if Driver is None or Neo4jClient is None:
        logger.warning("Neo4j driver unavailable; skipping Neo4j operations")
        return None

    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            DEFAULT_NEO4J_URI,
            auth=(DEFAULT_NEO4J_USER, DEFAULT_NEO4J_PASSWORD),
        )
        driver.verify_connectivity()
        logger.info("✓ Connected to Neo4j")
        return driver
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        raise


def _prepare_transition_dataframe(transitions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare transition DataFrame for loading into Neo4j.

    Ensures required columns exist and generates transition_id if missing.
    """
    df = transitions_df.copy()

    # Ensure transition_id column exists
    if "transition_id" not in df.columns:
        df["transition_id"] = [f"TRANS-{uuid4().hex[:12].upper()}" for _ in range(len(df))]

    # Ensure required columns exist with sensible defaults
    required_cols = [
        "transition_id",
        "award_id",
        "contract_id",
        "score",
        "method",
        "computed_at",
    ]
    for col in required_cols:
        if col not in df.columns:
            if col == "computed_at":
                df[col] = datetime.utcnow().isoformat()
            elif col == "score":
                df[col] = 0.5
            else:
                df[col] = None

    # Normalize column names for Neo4j
    df["likelihood_score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0.5)

    # Add confidence level based on score
    def _confidence_level(score: float) -> str:
        try:
            s = float(score)
            if s >= 0.75:
                return "high"
            elif s >= 0.60:
                return "likely"
            else:
                return "possible"
        except Exception:
            return "possible"

    df["confidence"] = df["likelihood_score"].apply(_confidence_level)

    # Ensure detection_date
    if "detection_date" not in df.columns:
        if "computed_at" in df.columns:
            df["detection_date"] = df["computed_at"]
        else:
            df["detection_date"] = datetime.utcnow().isoformat()

    return df[
        [
            "transition_id",
            "award_id",
            "contract_id",
            "likelihood_score",
            "confidence",
            "detection_date",
            "method",
        ]
    ]


@asset(
    name="neo4j_transitions",
    description="Load transition detections as Transition nodes in Neo4j (Task 13.3-13.5)",
)
def neo4j_transitions(
    context: AssetExecutionContext,
    transition_detections: pd.DataFrame,
) -> Output[Dict[str, Any]]:
    """
    Load transition detections as Transition nodes in Neo4j.

    Creates:
    - Transition nodes with properties: transition_id, award_id, contract_id,
      likelihood_score, confidence, detection_date, method
    - Indexes on transition_id, confidence, likelihood_score, detection_date

    Args:
        transition_detections: DataFrame with transition detection results

    Returns:
        Output with statistics and metadata
    """
    if TransitionLoader is None:
        context.log.warning("TransitionLoader unavailable; skipping Neo4j load")
        return Output(
            {"skipped": True, "reason": "TransitionLoader unavailable"},
            metadata={"status": "skipped"},
        )

    if transition_detections.empty:
        context.log.warning("No transition detections to load")
        return Output(
            {"nodes_created": 0, "errors": 1},
            metadata={"status": "empty", "rows": 0},
        )

    driver = _get_neo4j_driver()
    if driver is None:
        context.log.warning("Neo4j driver unavailable; skipping load")
        return Output(
            {"skipped": True, "reason": "Neo4j driver unavailable"},
            metadata={"status": "skipped"},
        )

    try:
        # Prepare data
        prep_df = _prepare_transition_dataframe(transition_detections)
        context.log.info(f"Prepared {len(prep_df)} transitions for loading")

        # Load transitions
        loader = TransitionLoader(driver=driver)
        start_time = time.time()

        # Ensure indexes
        loader.ensure_indexes()

        # Load Transition nodes
        nodes_created = loader.load_transition_nodes(prep_df)
        duration = time.time() - start_time

        stats = loader.get_stats()
        stats["duration_seconds"] = duration
        stats["prepared_rows"] = len(prep_df)

        context.log.info(f"✓ Loaded {nodes_created} transition nodes in {duration:.1f}s")

        metadata = {
            "nodes_created": nodes_created,
            "duration_seconds": duration,
            "prepared_rows": len(prep_df),
            "transitions_created": stats.get("transitions_created", 0),
            "transitions_updated": stats.get("transitions_updated", 0),
        }

        return Output(stats, metadata=metadata)

    except Exception as e:
        context.log.error(f"Failed to load transitions: {e}")
        raise
    finally:
        if driver:
            driver.close()


@asset_check(
    asset="neo4j_transitions",
    description="Verify transition node load success rate (Task 13.6)",
)
def transition_node_count_check(
    context: AssetExecutionContext,
    transition_detections: pd.DataFrame,
) -> AssetCheckResult:
    """
    Verify that transition nodes were successfully loaded into Neo4j.

    Checks:
    - At least TRANSITION_MIN_NODE_COUNT nodes exist
    - Load success rate >= threshold
    """
    if transition_detections.empty:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="✗ No transition detections to verify",
            metadata={"expected_nodes": 0, "error": "empty_input"},
        )

    driver = _get_neo4j_driver()
    if driver is None:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            description="⚠ Neo4j driver unavailable for verification",
            metadata={"status": "skipped"},
        )

    try:
        with driver.session(database=DEFAULT_NEO4J_DATABASE) as session:
            # Count Transition nodes
            result = session.run("MATCH (t:Transition) RETURN count(t) as n")
            actual_count = result.single()["n"]

        expected_count = len(transition_detections)
        success_rate = actual_count / expected_count if expected_count > 0 else 0.0
        passed = (
            actual_count >= TRANSITION_MIN_NODE_COUNT
            and success_rate >= TRANSITION_LOAD_SUCCESS_THRESHOLD
        )

        return AssetCheckResult(
            passed=passed,
            severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
            description=(
                f"{'✓' if passed else '✗'} Transition nodes: "
                f"loaded={actual_count}, expected={expected_count}, "
                f"rate={success_rate:.1%} (min {TRANSITION_LOAD_SUCCESS_THRESHOLD:.1%})"
            ),
            metadata={
                "actual_nodes": actual_count,
                "expected_nodes": expected_count,
                "success_rate": f"{success_rate:.1%}",
                "threshold": f"{TRANSITION_LOAD_SUCCESS_THRESHOLD:.1%}",
            },
        )

    except Exception as e:
        context.log.error(f"Failed to verify transition nodes: {e}")
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=f"✗ Verification failed: {e}",
            metadata={"error": str(e)},
        )
    finally:
        if driver:
            driver.close()


@asset(
    name="neo4j_transition_relationships",
    description="Create transition relationships in Neo4j (Task 14.1-14.7, 14.8)",
)
def neo4j_transition_relationships(
    context: AssetExecutionContext,
    neo4j_transitions: Dict[str, Any],
    transition_detections: pd.DataFrame,
) -> Output[Dict[str, Any]]:
    """
    Create transition relationships in Neo4j.

    Creates:
    - TRANSITIONED_TO (Award→Transition) (14.1-14.3)
    - RESULTED_IN (Transition→Contract) (14.4)
    - ENABLED_BY (Transition→Patent) for patent-backed (14.5)
    - INVOLVES_TECHNOLOGY (Transition→CETArea) (14.6)

    Args:
        neo4j_transitions: Stats from neo4j_transitions asset
        transition_detections: DataFrame with transition data

    Returns:
        Output with relationship statistics
    """
    if TransitionLoader is None:
        context.log.warning("TransitionLoader unavailable; skipping relationships")
        return Output(
            {"skipped": True, "reason": "TransitionLoader unavailable"},
            metadata={"status": "skipped"},
        )

    if transition_detections.empty:
        context.log.warning("No transitions for relationship creation")
        return Output(
            {"relationships_created": 0},
            metadata={"status": "empty"},
        )

    driver = _get_neo4j_driver()
    if driver is None:
        context.log.warning("Neo4j driver unavailable; skipping relationships")
        return Output(
            {"skipped": True, "reason": "Neo4j driver unavailable"},
            metadata={"status": "skipped"},
        )

    try:
        # Prepare data
        prep_df = _prepare_transition_dataframe(transition_detections)

        loader = TransitionLoader(driver=driver)
        start_time = time.time()

        # Create relationships (14.1-14.7)
        loader.create_transitioned_to_relationships(prep_df)
        context.log.info("✓ Created TRANSITIONED_TO relationships")

        loader.create_resulted_in_relationships(prep_df)
        context.log.info("✓ Created RESULTED_IN relationships")

        loader.create_enabled_by_relationships(prep_df)
        context.log.info("✓ Created ENABLED_BY relationships")

        loader.create_involves_technology_relationships(prep_df)
        context.log.info("✓ Created INVOLVES_TECHNOLOGY relationships")

        duration = time.time() - start_time
        stats = loader.get_stats()
        stats["duration_seconds"] = duration

        context.log.info(
            f"✓ Created relationships in {duration:.1f}s: {stats.get('relationships_created', 0)} total"
        )

        return Output(stats, metadata=stats)

    except Exception as e:
        context.log.error(f"Failed to create relationships: {e}")
        raise
    finally:
        if driver:
            driver.close()


@asset_check(
    asset="neo4j_transition_relationships",
    description="Verify transition relationships were created (Task 14.8)",
)
def transition_relationships_check(
    context: AssetExecutionContext,
    transition_detections: pd.DataFrame,
) -> AssetCheckResult:
    """
    Verify that transition relationships were successfully created.

    Checks relationship counts for:
    - TRANSITIONED_TO relationships
    - RESULTED_IN relationships
    - ENABLED_BY relationships (optional)
    - INVOLVES_TECHNOLOGY relationships (optional)
    """
    if transition_detections.empty:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            description="⚠ No transitions for relationship verification",
            metadata={"expected_transitions": 0},
        )

    driver = _get_neo4j_driver()
    if driver is None:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            description="⚠ Neo4j driver unavailable for verification",
            metadata={"status": "skipped"},
        )

    try:
        with driver.session(database=DEFAULT_NEO4J_DATABASE) as session:
            # Count relationships
            tt_count = session.run(
                "MATCH (a:Award)-[r:TRANSITIONED_TO]->(t:Transition) RETURN count(r) as n"
            ).single()["n"]

            ri_count = session.run(
                "MATCH (t:Transition)-[r:RESULTED_IN]->(c:Contract) RETURN count(r) as n"
            ).single()["n"]

            eb_count = session.run(
                "MATCH (t:Transition)-[r:ENABLED_BY]->(p:Patent) RETURN count(r) as n"
            ).single()["n"]

            it_count = session.run(
                "MATCH (t:Transition)-[r:INVOLVES_TECHNOLOGY]->(c:CETArea) RETURN count(r) as n"
            ).single()["n"]

        expected_tt = len(transition_detections)
        tt_rate = tt_count / expected_tt if expected_tt > 0 else 0.0

        passed = tt_count > 0 and tt_rate >= TRANSITION_LOAD_SUCCESS_THRESHOLD

        return AssetCheckResult(
            passed=passed,
            severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
            description=(
                f"{'✓' if passed else '✗'} Transition relationships: "
                f"TRANSITIONED_TO={tt_count} ({tt_rate:.1%} expected), "
                f"RESULTED_IN={ri_count}, ENABLED_BY={eb_count}, INVOLVES_TECHNOLOGY={it_count}"
            ),
            metadata={
                "transitioned_to_count": tt_count,
                "resulted_in_count": ri_count,
                "enabled_by_count": eb_count,
                "involves_technology_count": it_count,
                "transitioned_to_expected": expected_tt,
                "transitioned_to_rate": f"{tt_rate:.1%}",
            },
        )

    except Exception as e:
        context.log.error(f"Failed to verify relationships: {e}")
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=f"✗ Verification failed: {e}",
            metadata={"error": str(e)},
        )
    finally:
        if driver:
            driver.close()


@asset(
    name="neo4j_transition_profiles",
    description="Create company transition profile nodes in Neo4j (Task 15)",
)
def neo4j_transition_profiles(
    context: AssetExecutionContext,
    neo4j_transition_relationships: Dict[str, Any],
    transition_detections: pd.DataFrame,
    enriched_sbir_awards: Optional[pd.DataFrame] = None,
) -> Output[Dict[str, Any]]:
    """
    Create company-level transition profile nodes in Neo4j (Task 15).

    Creates:
    - TransitionProfile nodes with aggregated company-level metrics
    - ACHIEVED relationships (Company → TransitionProfile)

    Properties on TransitionProfile:
    - profile_id: Unique identifier
    - company_id: Associated company
    - total_awards: Total awards for company
    - total_transitions: Successful transitions
    - success_rate: transitions / awards
    - avg_likelihood_score: Average transition score
    - created_date: ISO datetime of profile creation

    Args:
        neo4j_transition_relationships: Stats from relationship creation
        transition_detections: DataFrame with transition data
        enriched_sbir_awards: Optional DataFrame with award details

    Returns:
        Output with profile statistics and metadata
    """
    if TransitionProfileLoader is None:
        context.log.warning("TransitionProfileLoader unavailable; skipping profile creation")
        return Output(
            {"skipped": True, "reason": "TransitionProfileLoader unavailable"},
            metadata={"status": "skipped"},
        )

    if transition_detections.empty:
        context.log.warning("No transitions for profile creation")
        return Output(
            {"profiles_created": 0},
            metadata={"status": "empty"},
        )

    driver = _get_neo4j_driver()
    if driver is None:
        context.log.warning("Neo4j driver unavailable; skipping profile creation")
        return Output(
            {"skipped": True, "reason": "Neo4j driver unavailable"},
            metadata={"status": "skipped"},
        )

    try:
        loader = TransitionProfileLoader(driver=driver)
        start_time = time.time()

        # Create transition profiles (Task 15.1-15.4)
        stats = loader.load_transition_profiles(
            transitions_df=transition_detections,
            awards_df=enriched_sbir_awards,
        )

        duration = time.time() - start_time
        stats["duration_seconds"] = duration

        context.log.info(
            f"✓ Created {stats.get('profiles_created', 0)} profiles in {duration:.1f}s"
        )

        metadata = {
            "profiles_created": stats.get("profiles_created", 0),
            "achieved_relationships": stats.get("achieved_relationships", 0),
            "duration_seconds": duration,
        }

        return Output(stats, metadata=metadata)

    except Exception as e:
        context.log.error(f"Failed to create transition profiles: {e}")
        raise
    finally:
        if driver:
            driver.close()
