"""Neo4j loader for Organization relationships."""

from datetime import datetime
from typing import Any

from loguru import logger

from .client import LoadMetrics, Neo4jClient


class OrganizationLoader:
    """Loader for Organization-to-Organization relationships."""

    def __init__(self, client: Neo4jClient):
        """Initialize with Neo4j client."""
        self.client = client

    def create_subsidiary_relationships(
        self,
        subsidiary_pairs: list[tuple[str, str, str, str]],  # (child_key, child_value, parent_key, parent_value)
        source: str = "UNKNOWN",
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Create SUBSIDIARY_OF relationships between Organizations.

        Relationship: (child:Organization)-[SUBSIDIARY_OF]->(parent:Organization)

        Args:
            subsidiary_pairs: List of tuples (child_key, child_value, parent_key, parent_value)
                where keys are property names (e.g., "uei", "organization_id") and values are
                the actual values to match on.
            source: Source of the relationship data (e.g., "CONTRACT_PARENT_UEI", "AGENCY_HIERARCHY")
            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with counts of created relationships
        """
        if metrics is None:
            metrics = LoadMetrics()

        if not subsidiary_pairs:
            logger.info("No SUBSIDIARY_OF relationships to create")
            return metrics

        logger.info(f"Creating {len(subsidiary_pairs)} SUBSIDIARY_OF relationships (source: {source})")
        start_time = datetime.utcnow()

        relationships: list[tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]] = []
        for child_key, child_value, parent_key, parent_value in subsidiary_pairs:
            if not child_value or not parent_value:
                logger.warning(f"Skipping SUBSIDIARY_OF relationship with missing values: child={child_value}, parent={parent_value}")
                metrics.errors += 1
                continue

            relationships.append(
                (
                    "Organization",
                    child_key,
                    str(child_value).strip(),
                    "Organization",
                    parent_key,
                    str(parent_value).strip(),
                    "SUBSIDIARY_OF",
                    {
                        "source": source,
                        "created_at": datetime.utcnow().isoformat(),
                    },
                )
            )

        if relationships:
            metrics = self.client.batch_create_relationships(relationships=relationships, metrics=metrics)

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(
            f"SUBSIDIARY_OF relationship creation completed in {duration:.2f}s: "
            f"{metrics.relationships_created.get('SUBSIDIARY_OF', 0)} created"
        )

        return metrics

