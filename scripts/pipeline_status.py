#!/usr/bin/env python3
"""Check pipeline status: asset health, Neo4j connectivity, and recent runs.

Usage:
    python scripts/pipeline_status.py                # Full status summary
    python scripts/pipeline_status.py --assets       # Asset status only
    python scripts/pipeline_status.py --neo4j        # Neo4j health only
    python scripts/pipeline_status.py --runs         # Recent Dagster runs
"""

from __future__ import annotations

import argparse
import json
import sys

from loguru import logger

from sbir_etl.config.loader import get_config


def check_assets(config) -> dict:
    """List assets and their last materialization status."""
    from sbir_analytics.clients import DagsterClient

    client = DagsterClient(config)
    assets = client.list_assets()
    results = []
    for asset in assets:
        status = client.get_asset_status(asset["key"])
        results.append(
            {
                "key": asset["key"],
                "group": asset["group"],
                "status": status.status,
                "last_run": status.last_run.isoformat() if status.last_run else None,
                "records_processed": status.records_processed,
            }
        )
    return {"assets": results, "total": len(results)}


def check_neo4j(config) -> dict:
    """Check Neo4j connection health."""
    from sbir_analytics.clients import Neo4jClient

    client = Neo4jClient(config)
    health = client.health_check()
    result = {
        "connected": health.connected,
        "uri": health.uri,
        "version": health.version,
        "error": health.error,
    }
    if health.connected:
        stats = client.get_statistics()
        if stats:
            result["statistics"] = {
                "total_nodes": stats.total_nodes,
                "total_relationships": stats.total_relationships,
                "node_counts": stats.node_counts,
                "relationship_counts": stats.relationship_counts,
            }
    client.close()
    return result


def list_runs(config, limit: int = 10) -> list:
    """List recent Dagster runs."""
    from sbir_analytics.clients import DagsterClient

    client = DagsterClient(config)
    return client.list_recent_runs(limit=limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check pipeline status")
    parser.add_argument("--assets", action="store_true", help="Show asset status")
    parser.add_argument("--neo4j", action="store_true", help="Check Neo4j health")
    parser.add_argument("--runs", action="store_true", help="List recent Dagster runs")
    parser.add_argument("--limit", type=int, default=10, help="Number of recent runs to show")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    config = get_config()
    show_all = not (args.assets or args.neo4j or args.runs)
    output = {}

    if args.assets or show_all:
        try:
            output["assets"] = check_assets(config)
        except Exception as e:
            logger.error(f"Failed to check assets: {e}")
            output["assets"] = {"error": str(e)}

    if args.neo4j or show_all:
        try:
            output["neo4j"] = check_neo4j(config)
        except Exception as e:
            logger.error(f"Failed to check Neo4j: {e}")
            output["neo4j"] = {"error": str(e)}

    if args.runs or show_all:
        try:
            output["recent_runs"] = list_runs(config, limit=args.limit)
        except Exception as e:
            logger.error(f"Failed to list runs: {e}")
            output["recent_runs"] = {"error": str(e)}

    if args.json:
        print(json.dumps(output, indent=2, default=str))
    else:
        for section, data in output.items():
            print(f"\n{'='*60}")
            print(f"  {section.upper()}")
            print(f"{'='*60}")
            print(json.dumps(data, indent=2, default=str))

    # Exit non-zero if Neo4j is down
    neo4j_data = output.get("neo4j", {})
    if isinstance(neo4j_data, dict) and neo4j_data.get("connected") is False:
        sys.exit(1)


if __name__ == "__main__":
    main()
