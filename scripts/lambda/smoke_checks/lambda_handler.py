"""Lambda function to run Neo4j smoke checks."""

import json
import os
from typing import Any

import boto3
from neo4j import GraphDatabase
from datetime import UTC

s3_client = boto3.client("s3")
secrets_client = boto3.client("secretsmanager")


def get_neo4j_credentials(secret_name: str) -> dict[str, str]:
    """Get Neo4j credentials from Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    return {
        "uri": secret["uri"],
        "username": secret["username"],
        "password": secret["password"],
        "database": secret.get("database", "neo4j"),
    }


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


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Run Neo4j smoke checks after SBIR award loading.

    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "neo4j_secret_name": "sbir-analytics/neo4j-aura"  # pragma: allowlist secret
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        secret_name = event.get("neo4j_secret_name") or os.environ.get(
            "NEO4J_SECRET_NAME", "sbir-analytics/neo4j-aura"
        )

        # Get credentials
        creds = get_neo4j_credentials(secret_name)

        # Run smoke checks
        results = run_smoke_checks(
            creds["uri"], creds["username"], creds["password"], creds["database"]
        )

        # Upload results to S3
        from datetime import datetime

        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        smoke_check_json_key = f"artifacts/{date_str}/neo4j_smoke_check.json"
        smoke_check_md_key = f"artifacts/{date_str}/neo4j_smoke_check.md"

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=smoke_check_json_key,
            Body=json.dumps(results, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

        # Generate markdown summary
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

        markdown_content = "\n".join(lines)
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=smoke_check_md_key,
            Body=markdown_content.encode("utf-8"),
            ContentType="text/markdown",
        )

        return {
            "statusCode": 200,
            "body": {
                "status": "success" if results.get("passed") else "failed",
                "passed": results.get("passed", False),
                "smoke_check_json_s3_key": smoke_check_json_key,
                "smoke_check_md_s3_key": smoke_check_md_key,
                "results": results,
            },
        }

    except Exception as e:
        print(f"Error running smoke checks: {e}")
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }
