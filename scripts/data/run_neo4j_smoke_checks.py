#!/usr/bin/env python3
"""Run Cypher smoke checks against Neo4j after SBIR award loading."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from src.config.loader import get_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Neo4j smoke checks after SBIR award loading.")
    parser.add_argument(
        "--output-json",
        required=True,
        type=Path,
        help="Path to write smoke check results JSON.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        help="Optional path to write markdown summary.",
    )
    parser.add_argument(
        "--gha-output",
        type=Path,
        help="Optional path to $GITHUB_OUTPUT for exposing artifact locations.",
    )
    return parser.parse_args()


def run_smoke_checks(uri: str, username: str, password: str, database: str) -> dict[str, Any]:
    """Run Cypher smoke checks against Neo4j."""
    driver = GraphDatabase.driver(uri, auth=(username, password))
    results: dict[str, Any] = {"checks": [], "passed": True, "summary": {}}

    try:
        with driver.session(database=database) as session:
            # Check 1: Award node count
            award_count_result = session.run("MATCH (a:Award) RETURN count(a) as count")
            award_count = award_count_result.single()["count"]
            results["checks"].append(
                {
                    "name": "award_node_count",
                    "passed": award_count > 0,
                    "value": award_count,
                    "message": f"Found {award_count} Award nodes",
                }
            )
            results["summary"]["award_count"] = award_count

            # Check 2: Company node count
            company_count_result = session.run("MATCH (c:Company) RETURN count(c) as count")
            company_count = company_count_result.single()["count"]
            results["checks"].append(
                {
                    "name": "company_node_count",
                    "passed": company_count > 0,
                    "value": company_count,
                    "message": f"Found {company_count} Company nodes",
                }
            )
            results["summary"]["company_count"] = company_count

            # Check 3: AWARDS relationship count
            awards_rel_result = session.run(
                "MATCH (a:Award)-[r:AWARDS]->(c:Company) RETURN count(r) as count"
            )
            awards_rel_count = awards_rel_result.single()["count"]
            results["checks"].append(
                {
                    "name": "awards_relationship_count",
                    "passed": awards_rel_count > 0,
                    "value": awards_rel_count,
                    "message": f"Found {awards_rel_count} AWARDS relationships",
                }
            )
            results["summary"]["awards_relationship_count"] = awards_rel_count

            # Check 4: Sample award properties
            sample_award_result = session.run(
                """
                MATCH (a:Award)
                WHERE a.award_id IS NOT NULL
                RETURN a.award_id, a.company_name, a.award_amount, a.program, a.phase
                LIMIT 5
                """
            )
            sample_awards = [dict(record) for record in sample_award_result]
            results["checks"].append(
                {
                    "name": "sample_award_properties",
                    "passed": len(sample_awards) > 0,
                    "value": len(sample_awards),
                    "message": f"Retrieved {len(sample_awards)} sample awards",
                    "samples": sample_awards,
                }
            )
            results["summary"]["sample_awards"] = len(sample_awards)

            # Check 5: Award-Company connectivity
            connected_count_result = session.run(
                """
                MATCH (a:Award)-[:AWARDS]->(c:Company)
                RETURN count(DISTINCT a) as connected_awards
                """
            )
            connected_awards = connected_count_result.single()["connected_awards"]
            results["checks"].append(
                {
                    "name": "award_company_connectivity",
                    "passed": connected_awards > 0,
                    "value": connected_awards,
                    "message": f"{connected_awards} awards are connected to companies",
                }
            )
            results["summary"]["connected_awards"] = connected_awards

            # Determine overall pass status
            results["passed"] = all(check["passed"] for check in results["checks"])

    except Exception as e:
        results["passed"] = False
        results["error"] = str(e)
        results["checks"].append(
            {
                "name": "connection_check",
                "passed": False,
                "message": f"Failed to connect to Neo4j: {e}",
            }
        )
    finally:
        driver.close()

    return results


def render_markdown_summary(results: dict[str, Any]) -> str:
    """Render smoke check results as markdown."""
    lines = [
        "# Neo4j Smoke Checks",
        "",
        f"**Status:** {'✅ PASSED' if results.get('passed') else '❌ FAILED'}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]

    summary = results.get("summary", {})
    for key, value in summary.items():
        if key != "sample_awards":
            lines.append(f"| {key.replace('_', ' ').title()} | {value} |")

    lines.append("")
    lines.append("## Checks")
    lines.append("")

    for check in results.get("checks", []):
        status = "✅" if check.get("passed") else "❌"
        lines.append(f"- {status} **{check['name']}**: {check.get('message', 'N/A')}")

    if results.get("error"):
        lines.append("")
        lines.append(f"**Error:** {results['error']}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    config = get_config()
    neo4j_config = config.neo4j

    results = run_smoke_checks(
        uri=neo4j_config.uri,
        username=neo4j_config.username,
        password=neo4j_config.password,
        database=neo4j_config.database,
    )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        f.write("\n")

    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        summary_md = render_markdown_summary(results)
        args.output_md.write_text(summary_md, encoding="utf-8")

    if args.gha_output:
        with args.gha_output.open("a", encoding="utf-8") as f:
            f.write(f"smoke_check_json={args.output_json}\n")
            if args.output_md:
                f.write(f"smoke_check_md={args.output_md}\n")
            f.write(f"smoke_check_passed={'true' if results.get('passed') else 'false'}\n")

    if not results.get("passed"):
        print("Smoke checks failed", file=sys.stderr)
        json.dump(results, sys.stderr, indent=2)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
