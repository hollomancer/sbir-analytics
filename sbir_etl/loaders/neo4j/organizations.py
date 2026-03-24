"""Neo4j loader for Organization relationships."""

from typing import Any

from loguru import logger

from .base import BaseNeo4jLoader
from .client import LoadMetrics


class OrganizationLoader(BaseNeo4jLoader):
    """Loader for Organization-to-Organization relationships.

    Extends BaseNeo4jLoader to provide simplified relationship creation
    with consistent logging and metrics tracking.
    """

    def create_subsidiary_relationships(
        self,
        subsidiary_pairs: list[tuple[str, str, str, str]],
        source: str = "UNKNOWN",
    ) -> LoadMetrics:
        """Create SUBSIDIARY_OF relationships between Organizations.

        Relationship: (child:Organization)-[SUBSIDIARY_OF]->(parent:Organization)

        Args:
            subsidiary_pairs: List of tuples (child_key, child_value, parent_key, parent_value)
                where keys are property names (e.g., "uei", "organization_id") and values are
                the actual values to match on.
            source: Source of the relationship data (e.g., "CONTRACT_PARENT_UEI", "AGENCY_HIERARCHY")

        Returns:
            LoadMetrics with counts of created relationships

        Example:
            >>> loader = OrganizationLoader(client)
            >>> metrics = loader.create_subsidiary_relationships(
            ...     subsidiary_pairs=[
            ...         ("uei", "ABC123", "uei", "PARENT456"),
            ...         ("organization_id", "ORG-001", "organization_id", "ORG-PARENT"),
            ...     ],
            ...     source="CONTRACT_PARENT_UEI"
            ... )
        """
        if not subsidiary_pairs:
            logger.info(f"{self.loader_name}: No SUBSIDIARY_OF relationships to create")
            return self.metrics

        logger.info(
            f"{self.loader_name}: Creating {len(subsidiary_pairs)} SUBSIDIARY_OF relationships "
            f"(source: {source})"
        )

        # Build relationship list in simplified format
        relationships: list[tuple[Any, Any, dict[str, Any] | None]] = []
        for _child_key, child_value, _parent_key, parent_value in subsidiary_pairs:
            if not child_value or not parent_value:
                logger.warning(
                    f"Skipping SUBSIDIARY_OF relationship with missing values: "
                    f"child={child_value}, parent={parent_value}"
                )
                self.metrics.errors += 1
                continue

            # Note: We're creating relationships between organizations potentially
            # matched on different keys (e.g., child by organization_id, parent by UEI)
            # This requires a more complex query than the base method supports
            # So we'll use the client directly for this special case
            from datetime import datetime

            relationships.append(
                (
                    str(child_value).strip(),
                    str(parent_value).strip(),
                    {
                        "source": source,
                        "created_at": datetime.utcnow().isoformat(),
                    },
                )
            )

        if not relationships:
            return self.metrics

        # For this special case where source and target might use different keys,
        # we need to use a custom query instead of the base class method
        full_relationships: list[
            tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]
        ] = []

        for i, (child_key, child_value, parent_key, parent_value) in enumerate(subsidiary_pairs):
            if i < len(relationships):  # Only include valid relationships
                _, _, properties = relationships[i - (len(subsidiary_pairs) - len(relationships))]
                full_relationships.append(
                    (
                        "Organization",
                        child_key,
                        str(child_value).strip() if child_value else None,
                        "Organization",
                        parent_key,
                        str(parent_value).strip() if parent_value else None,
                        "SUBSIDIARY_OF",
                        properties,
                    )
                )

        # Use client directly for complex relationship creation
        self.metrics = self.client.batch_create_relationships(
            relationships=full_relationships,
            metrics=self.metrics,
        )

        logger.info(
            f"{self.loader_name}: SUBSIDIARY_OF relationships created - "
            f"{self.metrics.relationships_created.get('SUBSIDIARY_OF', 0)} created"
        )

        return self.metrics
