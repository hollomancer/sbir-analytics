#!/usr/bin/env python3
"""
scripts/neo4j/check_aura_usage.py

Check Neo4j database resource usage, particularly useful for Neo4j Aura Free
instances with hard limits (100K nodes, 200K properties, 200K relationships).

This script:
- Connects to Neo4j and counts nodes, relationships, and properties
- Displays usage against Aura Free limits
- Validates if planned operations will fit within limits
- Provides warnings and recommendations

Connection details are read from environment variables:
    SBIR_ETL__NEO4J__URI (or NEO4J_URI)
    SBIR_ETL__NEO4J__USERNAME (or NEO4J_USER)
    SBIR_ETL__NEO4J__PASSWORD (or NEO4J_PASSWORD)

Usage:
    # Check current usage
    python scripts/neo4j/check_aura_usage.py

    # Check if planned load will fit
    python scripts/neo4j/check_aura_usage.py --planned-nodes 5000

    # Get detailed breakdown by label
    python scripts/neo4j/check_aura_usage.py --detailed

    # Check with custom limits (e.g., paid tier)
    python scripts/neo4j/check_aura_usage.py --max-nodes 1000000
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError
except ImportError:
    print("Error: neo4j package not found. Install with: pip install neo4j")
    sys.exit(1)


# Neo4j Aura Free hard limits
AURA_FREE_LIMITS = {
    "nodes": 100_000,
    "relationships": 200_000,
    "properties": 200_000,
}

# Recommended safety margins (leave buffer for overhead)
SAFETY_MARGINS = {
    "nodes": 0.95,  # Use max 95% of limit
    "relationships": 0.95,
    "properties": 0.95,
}


class AuraUsageChecker:
    """Check and validate Neo4j Aura database usage."""

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        max_nodes: int | None = None,
        max_relationships: int | None = None,
        max_properties: int | None = None,
    ):
        """Initialize checker with connection details and limits.

        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password
            max_nodes: Maximum nodes allowed (default: Aura Free limit)
            max_relationships: Maximum relationships allowed (default: Aura Free limit)
            max_properties: Maximum properties allowed (default: Aura Free limit)
        """
        self.uri = uri
        self.username = username
        self.password = password
        self.driver = None

        # Set limits (default to Aura Free)
        self.max_nodes = max_nodes or AURA_FREE_LIMITS["nodes"]
        self.max_relationships = max_relationships or AURA_FREE_LIMITS["relationships"]
        self.max_properties = max_properties or AURA_FREE_LIMITS["properties"]

    def __enter__(self):
        """Context manager entry."""
        self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.driver:
            self.driver.close()

    def get_node_count(self) -> int:
        """Get total node count."""
        with self.driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) as count")
            return result.single()["count"]

    def get_relationship_count(self) -> int:
        """Get total relationship count."""
        with self.driver.session() as session:
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
            return result.single()["count"]

    def get_property_count(self) -> int:
        """Get total property count.

        Note: This counts all properties across all nodes and relationships.
        """
        with self.driver.session() as session:
            # Count node properties
            node_props = (
                session.run(
                    """
                MATCH (n)
                RETURN sum(size(keys(n))) as count
                """
                ).single()["count"]
                or 0
            )

            # Count relationship properties
            rel_props = (
                session.run(
                    """
                MATCH ()-[r]->()
                RETURN sum(size(keys(r))) as count
                """
                ).single()["count"]
                or 0
            )

            return node_props + rel_props

    def get_nodes_by_label(self) -> dict[str, int]:
        """Get node count breakdown by label."""
        with self.driver.session() as session:
            result = session.run(
                """
                CALL db.labels() YIELD label
                CALL apoc.cypher.run(
                    'MATCH (n:`' + label + '`) RETURN count(n) as count',
                    {}
                ) YIELD value
                RETURN label, value.count as count
                ORDER BY count DESC
                """
            )
            return {record["label"]: record["count"] for record in result}

    def get_nodes_by_label_simple(self) -> dict[str, int]:
        """Get node count breakdown by label (without APOC)."""
        with self.driver.session() as session:
            # Get all labels
            labels = session.run("CALL db.labels() YIELD label RETURN label").data()

            counts = {}
            for label_record in labels:
                label = label_record["label"]
                # Count nodes for this label
                count = session.run(f"MATCH (n:`{label}`) RETURN count(n) as count").single()[
                    "count"
                ]
                counts[label] = count

            return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def get_usage_stats(self) -> dict[str, Any]:
        """Get comprehensive usage statistics."""
        return {
            "nodes": self.get_node_count(),
            "relationships": self.get_relationship_count(),
            "properties": self.get_property_count(),
        }

    def check_capacity(
        self, planned_nodes: int = 0, planned_relationships: int = 0
    ) -> dict[str, Any]:
        """Check if planned additions will fit within limits.

        Args:
            planned_nodes: Number of nodes you plan to add
            planned_relationships: Number of relationships you plan to add

        Returns:
            Dictionary with capacity check results
        """
        stats = self.get_usage_stats()

        # Calculate totals after planned additions
        total_nodes = stats["nodes"] + planned_nodes
        total_relationships = stats["relationships"] + planned_relationships

        # Calculate safe limits (with safety margin)
        safe_node_limit = int(self.max_nodes * SAFETY_MARGINS["nodes"])
        safe_rel_limit = int(self.max_relationships * SAFETY_MARGINS["relationships"])

        # Check if within limits
        results = {
            "current": stats,
            "planned": {
                "nodes": planned_nodes,
                "relationships": planned_relationships,
            },
            "projected": {
                "nodes": total_nodes,
                "relationships": total_relationships,
            },
            "limits": {
                "nodes": self.max_nodes,
                "relationships": self.max_relationships,
                "properties": self.max_properties,
            },
            "safe_limits": {
                "nodes": safe_node_limit,
                "relationships": safe_rel_limit,
            },
            "within_limits": {
                "nodes": total_nodes <= safe_node_limit,
                "relationships": total_relationships <= safe_rel_limit,
            },
            "will_fit": (total_nodes <= safe_node_limit and total_relationships <= safe_rel_limit),
        }

        return results


def format_number(num: int) -> str:
    """Format number with thousand separators."""
    return f"{num:,}"


def format_percentage(value: int, max_value: int) -> str:
    """Format percentage with color coding."""
    pct = (value / max_value * 100) if max_value > 0 else 0
    return f"{pct:.1f}%"


def print_usage_report(stats: dict[str, int], limits: dict[str, int]):
    """Print formatted usage report."""
    print("\n" + "=" * 60)
    print("Neo4j Database Resource Usage")
    print("=" * 60)

    print(
        f"\nNodes:        {format_number(stats['nodes']):>12} / {format_number(limits['nodes']):>12} ({format_percentage(stats['nodes'], limits['nodes'])})"
    )
    print(
        f"Relationships:{format_number(stats['relationships']):>12} / {format_number(limits['relationships']):>12} ({format_percentage(stats['relationships'], limits['relationships'])})"
    )
    print(
        f"Properties:   {format_number(stats['properties']):>12} / {format_number(limits['properties']):>12} ({format_percentage(stats['properties'], limits['properties'])})"
    )

    # Status indicator
    max_pct = (
        max(
            stats["nodes"] / limits["nodes"],
            stats["relationships"] / limits["relationships"],
            stats["properties"] / limits["properties"],
        )
        * 100
    )

    print("\n" + "-" * 60)
    if max_pct < 80:
        print("Status: ✅ Within safe limits")
    elif max_pct < 95:
        print("Status: ⚠️  Warning - Approaching limits")
    else:
        print("Status: 🚨 Critical - Near or at limits")
    print("-" * 60 + "\n")


def print_capacity_check(results: dict[str, Any]):
    """Print capacity check results."""
    print("\n" + "=" * 60)
    print("Capacity Check")
    print("=" * 60)

    print("\nCurrent Usage:")
    print(f"  Nodes:        {format_number(results['current']['nodes'])}")
    print(f"  Relationships:{format_number(results['current']['relationships'])}")

    print("\nPlanned Additions:")
    print(f"  Nodes:        {format_number(results['planned']['nodes'])}")
    print(f"  Relationships:{format_number(results['planned']['relationships'])}")

    print("\nProjected Total:")
    print(
        f"  Nodes:        {format_number(results['projected']['nodes'])} / {format_number(results['safe_limits']['nodes'])} (safe limit)"
    )
    print(
        f"  Relationships:{format_number(results['projected']['relationships'])} / {format_number(results['safe_limits']['relationships'])} (safe limit)"
    )

    print("\n" + "-" * 60)
    if results["will_fit"]:
        print("Result: ✅ Planned additions will fit within safe limits")
    else:
        print("Result: ❌ Planned additions exceed safe limits")
        if not results["within_limits"]["nodes"]:
            overflow = results["projected"]["nodes"] - results["safe_limits"]["nodes"]
            print(f"  - Node overflow: {format_number(overflow)} nodes over safe limit")
        if not results["within_limits"]["relationships"]:
            overflow = (
                results["projected"]["relationships"] - results["safe_limits"]["relationships"]
            )
            print(f"  - Relationship overflow: {format_number(overflow)} over safe limit")
    print("-" * 60 + "\n")


def print_label_breakdown(labels: dict[str, int]):
    """Print node count by label."""
    print("\n" + "=" * 60)
    print("Node Count by Label")
    print("=" * 60 + "\n")

    if not labels:
        print("No labels found in database.\n")
        return

    # Print in table format
    print(f"{'Label':<30} {'Count':>15}")
    print("-" * 60)
    for label, count in labels.items():
        print(f"{label:<30} {format_number(count):>15}")
    print("-" * 60)
    print(f"{'TOTAL':<30} {format_number(sum(labels.values())):>15}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Check Neo4j Aura database resource usage")
    parser.add_argument(
        "--planned-nodes",
        type=int,
        default=0,
        help="Number of nodes you plan to add (for capacity check)",
    )
    parser.add_argument(
        "--planned-relationships",
        type=int,
        default=0,
        help="Number of relationships you plan to add (for capacity check)",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed breakdown by label",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=AURA_FREE_LIMITS["nodes"],
        help=f"Maximum nodes allowed (default: {AURA_FREE_LIMITS['nodes']} for Aura Free)",
    )
    parser.add_argument(
        "--max-relationships",
        type=int,
        default=AURA_FREE_LIMITS["relationships"],
        help=f"Maximum relationships allowed (default: {AURA_FREE_LIMITS['relationships']} for Aura Free)",
    )
    parser.add_argument(
        "--max-properties",
        type=int,
        default=AURA_FREE_LIMITS["properties"],
        help=f"Maximum properties allowed (default: {AURA_FREE_LIMITS['properties']} for Aura Free)",
    )

    args = parser.parse_args()

    # Get connection details from environment
    uri = os.getenv("SBIR_ETL__NEO4J__URI") or os.getenv("NEO4J_URI")
    username = os.getenv("SBIR_ETL__NEO4J__USERNAME") or os.getenv("NEO4J_USER")
    password = os.getenv("SBIR_ETL__NEO4J__PASSWORD") or os.getenv("NEO4J_PASSWORD")

    if not all([uri, username, password]):
        print("Error: Missing Neo4j connection details in environment variables")
        print("Required: SBIR_ETL__NEO4J__URI (or NEO4J_URI)")
        print("          SBIR_ETL__NEO4J__USERNAME (or NEO4J_USER)")
        print("          SBIR_ETL__NEO4J__PASSWORD (or NEO4J_PASSWORD)")
        sys.exit(1)

    try:
        with AuraUsageChecker(
            uri=uri,
            username=username,
            password=password,
            max_nodes=args.max_nodes,
            max_relationships=args.max_relationships,
            max_properties=args.max_properties,
        ) as checker:
            # Get and display current usage
            stats = checker.get_usage_stats()
            limits = {
                "nodes": args.max_nodes,
                "relationships": args.max_relationships,
                "properties": args.max_properties,
            }
            print_usage_report(stats, limits)

            # If planned additions specified, check capacity
            if args.planned_nodes > 0 or args.planned_relationships > 0:
                results = checker.check_capacity(
                    planned_nodes=args.planned_nodes,
                    planned_relationships=args.planned_relationships,
                )
                print_capacity_check(results)

                # Exit with error if won't fit
                if not results["will_fit"]:
                    sys.exit(1)

            # If detailed, show label breakdown
            if args.detailed:
                try:
                    labels = checker.get_nodes_by_label_simple()
                    print_label_breakdown(labels)
                except Exception as e:
                    print(f"Warning: Could not get label breakdown: {e}")

    except Neo4jError as e:
        print(f"Neo4j Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
