"""Neo4j loading assets for SBIR awards."""

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import AssetCheckResult, AssetCheckSeverity, AssetExecutionContext, Output, asset, asset_check
from loguru import logger

from ..config.loader import get_config
from ..loaders.neo4j import LoadMetrics, Neo4jClient, Neo4jConfig
from ..models.award import Award


def _get_neo4j_client() -> Neo4jClient | None:
    """Get Neo4j client from configuration, or None if unavailable."""
    try:
        config = get_config()
        neo4j_config = config.neo4j

        client_config = Neo4jConfig(
            uri=neo4j_config.uri,
            username=neo4j_config.username,
            password=neo4j_config.password,
            database=neo4j_config.database,
            batch_size=neo4j_config.batch_size,
        )

        client = Neo4jClient(client_config)
        # Test connection
        with client.session() as session:
            session.run("RETURN 1")
        return client
    except Exception as e:
        logger.warning(f"Neo4j unavailable: {e}")
        return None


@asset(
    description="Load validated SBIR awards into Neo4j as Award nodes",
    group_name="neo4j_loading",
    compute_kind="neo4j",
)
def neo4j_sbir_awards(
    context: AssetExecutionContext, validated_sbir_awards: pd.DataFrame
) -> Output[dict[str, Any]]:
    """
    Load validated SBIR awards into Neo4j.

    Creates Award nodes with properties from the validated DataFrame.
    Also creates Company nodes and AWARDS relationships.

    Args:
        validated_sbir_awards: Validated SBIR awards DataFrame

    Returns:
        Dictionary with load metrics and status
    """
    client = _get_neo4j_client()
    if client is None:
        return Output(
            value={"status": "skipped", "reason": "neo4j_unavailable"},
            metadata={"skipped": True, "reason": "Neo4j client unavailable"},
        )

    start_time = time.time()
    metrics = LoadMetrics()

    try:
        # Ensure constraints exist
        client.create_constraints()
        client.create_indexes()

        # Convert DataFrame rows to Award models, then to Neo4j node properties
        award_nodes = []
        company_nodes_map: dict[str, dict[str, Any]] = {}
        award_company_rels: list[tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]] = []

        for _, row in validated_sbir_awards.iterrows():
            try:
                # Convert row dict to Award model
                row_dict = row.to_dict()
                award = Award.from_sbir_csv(row_dict)

                # Create Award node properties
                award_props = {
                    "award_id": award.award_id,
                    "company_name": award.company_name,
                    "award_amount": award.award_amount,
                    "award_date": award.award_date.isoformat() if award.award_date else None,
                    "program": award.program,
                    "phase": award.phase,
                    "agency": award.agency,
                    "branch": award.branch,
                    "contract": award.contract,
                    "award_year": award.award_year,
                    "award_title": award.award_title,
                    "abstract": award.abstract,
                }

                # Add optional fields if present
                if award.company_uei:
                    award_props["company_uei"] = award.company_uei
                if award.company_duns:
                    award_props["company_duns"] = award.company_duns
                if award.principal_investigator:
                    award_props["principal_investigator"] = award.principal_investigator
                if award.research_institution:
                    award_props["research_institution"] = award.research_institution

                award_nodes.append(award_props)

                # Create Company node if UEI available
                if award.company_uei:
                    if award.company_uei not in company_nodes_map:
                        company_props = {
                            "uei": award.company_uei,
                            "name": award.company_name,
                        }
                        if award.company_duns:
                            company_props["duns"] = award.company_duns
                        if award.company_city:
                            company_props["city"] = award.company_city
                        if award.company_state:
                            company_props["state"] = award.company_state
                        if award.company_zip:
                            company_props["zip"] = award.company_zip
                        company_nodes_map[award.company_uei] = company_props

                    # Create AWARDS relationship
                    award_company_rels.append(
                        (
                            "Award",
                            "award_id",
                            award.award_id,
                            "Company",
                            "uei",
                            award.company_uei,
                            "AWARDS",
                            None,
                        )
                    )

            except Exception as e:
                logger.warning(f"Failed to process award row: {e}")
                metrics.errors += 1

        # Load Company nodes first
        if company_nodes_map:
            company_nodes_list = list(company_nodes_map.values())
            company_metrics = client.batch_upsert_nodes(
                label="Company", key_property="uei", nodes=company_nodes_list, metrics=metrics
            )
            metrics = company_metrics
            context.log.info(f"Loaded {len(company_nodes_list)} Company nodes")

        # Load Award nodes
        if award_nodes:
            award_metrics = client.batch_upsert_nodes(
                label="Award", key_property="award_id", nodes=award_nodes, metrics=metrics
            )
            metrics = award_metrics
            context.log.info(f"Loaded {len(award_nodes)} Award nodes")

        # Create AWARDS relationships
        if award_company_rels:
            rel_metrics = client.batch_create_relationships(award_company_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(f"Created {len(award_company_rels)} AWARDS relationships")

        duration = time.time() - start_time

        result = {
            "status": "success",
            "awards_loaded": metrics.nodes_created.get("Award", 0),
            "awards_updated": metrics.nodes_updated.get("Award", 0),
            "companies_loaded": metrics.nodes_created.get("Company", 0),
            "companies_updated": metrics.nodes_updated.get("Company", 0),
            "relationships_created": sum(metrics.relationships_created.values()),
            "errors": metrics.errors,
            "duration_seconds": duration,
            "metrics": {
                "nodes_created": metrics.nodes_created,
                "nodes_updated": metrics.nodes_updated,
                "relationships_created": metrics.relationships_created,
                "errors": metrics.errors,
            },
        }

        # Write metrics to file
        output_dir = Path("data/loaded/neo4j")
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics_file = output_dir / f"neo4j_sbir_awards_metrics_{int(time.time())}.json"
        with metrics_file.open("w") as f:
            json.dump(result, f, indent=2)

        context.log.info(
            "Neo4j SBIR awards load complete",
            extra={
                "awards_loaded": result["awards_loaded"],
                "companies_loaded": result["companies_loaded"],
                "relationships_created": result["relationships_created"],
                "errors": result["errors"],
                "duration_seconds": duration,
            },
        )

        return Output(
            value=result,
            metadata={
                "awards_loaded": result["awards_loaded"],
                "companies_loaded": result["companies_loaded"],
                "relationships_created": result["relationships_created"],
                "errors": result["errors"],
                "duration_seconds": round(duration, 2),
                "metrics_file": str(metrics_file),
            },
        )

    except Exception as e:
        logger.error(f"Failed to load SBIR awards to Neo4j: {e}")
        return Output(
            value={"status": "error", "error": str(e)},
            metadata={"error": str(e)},
        )
    finally:
        client.close()


@asset_check(
    asset=neo4j_sbir_awards,
    description="Verify SBIR awards were loaded successfully into Neo4j",
)
def neo4j_sbir_awards_load_check(neo4j_sbir_awards: dict[str, Any]) -> AssetCheckResult:
    """
    Check that SBIR awards were loaded successfully into Neo4j.

    Fails if load status is not "success" or if error count is too high.
    """
    status = neo4j_sbir_awards.get("status")
    errors = neo4j_sbir_awards.get("errors", 0)
    awards_loaded = neo4j_sbir_awards.get("awards_loaded", 0)

    if status != "success":
        reason = neo4j_sbir_awards.get("reason") or neo4j_sbir_awards.get("error", "unknown")
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=f"✗ Neo4j load failed: {reason}",
            metadata={"status": status, "reason": reason},
        )

    # Allow some errors but fail if too many
    error_threshold = 100
    if errors > error_threshold:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=f"✗ Too many load errors: {errors} (threshold: {error_threshold})",
            metadata={"errors": errors, "threshold": error_threshold},
        )

    if awards_loaded == 0:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="✗ No awards were loaded",
            metadata={"awards_loaded": 0},
        )

    return AssetCheckResult(
        passed=True,
        severity=AssetCheckSeverity.WARN,
        description=f"✓ Neo4j load successful: {awards_loaded} awards loaded, {errors} errors",
        metadata={
            "awards_loaded": awards_loaded,
            "companies_loaded": neo4j_sbir_awards.get("companies_loaded", 0),
            "relationships_created": neo4j_sbir_awards.get("relationships_created", 0),
            "errors": errors,
        },
    )

