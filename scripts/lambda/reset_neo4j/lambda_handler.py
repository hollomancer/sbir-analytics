"""Lambda function to reset Neo4j database."""

import json
import os
from typing import Any

import boto3
from neo4j import GraphDatabase

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


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Reset Neo4j database by deleting SBIR-related nodes.

    Event structure:
    {
        "neo4j_secret_name": "sbir-analytics/neo4j-aura",  # pragma: allowlist secret  # Optional, uses env var if not provided
        "dry_run": false
    }
    """
    try:
        secret_name = event.get("neo4j_secret_name") or os.environ.get(
            "NEO4J_SECRET_NAME", "sbir-analytics/neo4j-aura"
        )
        dry_run = event.get("dry_run", False)

        # Get credentials
        creds = get_neo4j_credentials(secret_name)
        driver = GraphDatabase.driver(creds["uri"], auth=(creds["username"], creds["password"]))

        try:
            with driver.session(database=creds["database"]) as session:
                if dry_run:
                    # Count what would be deleted
                    award_count = session.run("MATCH (a:Award) RETURN count(a) as count").single()[
                        "count"
                    ]
                    company_count = session.run(
                        "MATCH (c:Company) RETURN count(c) as count"
                    ).single()["count"]
                    rel_count = session.run(
                        "MATCH (a:Award)-[r:AWARDS]->(c:Company) RETURN count(r) as count"
                    ).single()["count"]
                    return {
                        "statusCode": 200,
                        "body": {
                            "status": "success",
                            "dry_run": True,
                            "would_delete": {
                                "awards": award_count,
                                "companies": company_count,
                                "relationships": rel_count,
                            },
                        },
                    }

                # Delete AWARDS relationships first
                rel_result = session.run(
                    """
                    MATCH (a:Award)-[r:AWARDS]->(c:Company)
                    DELETE r
                    RETURN count(r) as deleted
                    """
                )
                rel_deleted = rel_result.single()["deleted"]

                # Delete Award nodes
                award_result = session.run(
                    """
                    MATCH (a:Award)
                    DELETE a
                    RETURN count(a) as deleted
                    """
                )
                awards_deleted = award_result.single()["deleted"]

                # Delete Company nodes (only unconnected ones)
                company_result = session.run(
                    """
                    MATCH (c:Company)
                    WHERE NOT (c)<-[:AWARDS]-()
                    DELETE c
                    RETURN count(c) as deleted
                    """
                )
                companies_deleted = company_result.single()["deleted"]

                return {
                    "statusCode": 200,
                    "body": {
                        "status": "success",
                        "deleted": {
                            "awards": awards_deleted,
                            "companies": companies_deleted,
                            "relationships": rel_deleted,
                        },
                    },
                }

        finally:
            driver.close()

    except Exception as e:
        print(f"Error resetting Neo4j: {e}")
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }
