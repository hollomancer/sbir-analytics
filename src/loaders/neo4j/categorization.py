"""Company Categorization Loader for Neo4j Graph Operations.

This module loads company categorization data into Neo4j, enriching existing
Company nodes with Product/Service/Mixed classification properties derived
from USAspending contract portfolio analysis.

Responsibilities:
  - Add categorization properties to existing Company nodes
  - Create idempotent updates using MERGE operations
  - Track classification metadata (confidence, award counts, etc.)
  - Support batch operations for performance

The loader updates Company nodes with:
  - classification: Product-leaning, Service-leaning, Mixed, or Uncertain
  - product_pct: Percentage of dollars from product contracts
  - service_pct: Percentage of dollars from service/R&D contracts
  - categorization_confidence: Low, Medium, or High
  - categorization_award_count: Total contracts analyzed
  - categorization_psc_family_count: Number of distinct PSC families
  - categorization_total_dollars: Total contract dollars
  - categorization_updated_at: Timestamp of categorization
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from loguru import logger
from pydantic import Field

from .base import BaseLoaderConfig, BaseNeo4jLoader
from .client import LoadMetrics, Neo4jClient


class CompanyCategorizationLoaderConfig(BaseLoaderConfig):
    """Configuration for company categorization loading operations."""

    update_existing_only: bool = Field(
        default=True,
        description="Only update existing Company nodes (do not create new ones)",
    )


class CompanyCategorizationLoader(BaseNeo4jLoader):
    """Loads company categorization data into Neo4j Company nodes.

    Enriches existing Company nodes with classification properties based on
    USAspending contract portfolio analysis. Uses idempotent MERGE operations
    to support reprocessing and updates.

    Refactored to inherit from BaseNeo4jLoader for consistency.

    Attributes:
        client: Neo4jClient for graph operations
        config: CompanyCategorizationLoaderConfig with batch size and flags
        metrics: LoadMetrics for tracking operations (from base class)
    """

    def __init__(
        self,
        client: Neo4jClient,
        config: CompanyCategorizationLoaderConfig | None = None,
    ) -> None:
        """Initialize categorization loader.

        Args:
            client: Neo4j client for database operations
            config: Optional configuration (uses defaults if not provided)
        """
        super().__init__(client)
        self.config = config or CompanyCategorizationLoaderConfig()
        logger.info(
            "CompanyCategorizationLoader initialized with batch_size={}, "
            "create_indexes={}, update_existing_only={}",
            self.config.batch_size,
            self.config.create_indexes,
            self.config.update_existing_only,
        )

    # -------------------------------------------------------------------------
    # Schema management
    # -------------------------------------------------------------------------

    def create_indexes(self, indexes: list[str] | None = None) -> None:  # type: ignore[override]
        """Create indexes for categorization properties on Company nodes."""
        if indexes is None:
            indexes = [
            # Index on classification for filtering queries
            "CREATE INDEX company_classification_idx IF NOT EXISTS "
            "FOR (c:Company) ON (c.classification)",
            # Index on confidence for quality filtering
            "CREATE INDEX company_categorization_confidence_idx IF NOT EXISTS "
            "FOR (c:Company) ON (c.categorization_confidence)",
            # Composite index for classification + confidence queries
            "CREATE INDEX company_classification_confidence_idx IF NOT EXISTS "
            "FOR (c:Company) ON (c.classification, c.categorization_confidence)",
        ]
        super().create_indexes(indexes)

    # -------------------------------------------------------------------------
    # Company categorization enrichment
    # -------------------------------------------------------------------------

    def load_categorizations(
        self,
        categorizations: Iterable[dict[str, Any]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Enrich Company nodes with categorization properties.

        Each categorization dict should include:
          - company_uei (required): UEI to match Company node
          - classification (required): Product-leaning, Service-leaning, Mixed, Uncertain
          - product_pct (required): Percentage of product dollars
          - service_pct (required): Percentage of service dollars
          - confidence (required): Low, Medium, High
          - award_count (required): Number of contracts analyzed
          - psc_family_count (optional): Number of distinct PSC families
          - total_dollars (optional): Total contract dollars
          - product_dollars (optional): Product contract dollars
          - service_dollars (optional): Service contract dollars
          - agency_breakdown (optional): Dictionary of agency name -> percentage
          - override_reason (optional): Reason for classification override

        Args:
            categorizations: Iterable of categorization dictionaries
            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with nodes_updated count
        """
        metrics = metrics or LoadMetrics()

        # Collect categorization data for batch processing
        categorization_data: list[dict[str, Any]] = []

        for raw in categorizations:
            uei = _as_str(raw.get("company_uei"))
            classification = _as_str(raw.get("classification"))
            confidence = _as_str(raw.get("confidence"))

            # Validate required fields
            if not uei:
                logger.warning("Skipping categorization missing company_uei: {}", raw)
                metrics.errors += 1
                continue

            if not classification or not confidence:
                logger.warning(
                    "Skipping categorization for {} missing classification or confidence",
                    uei,
                )
                metrics.errors += 1
                continue

            # Build properties dict with only non-null values
            props: dict[str, Any] = {
                "classification": classification,
                "product_pct": _as_float(raw.get("product_pct")),
                "service_pct": _as_float(raw.get("service_pct")),
                "categorization_confidence": confidence,
                "categorization_award_count": _as_int(raw.get("award_count")),
                "categorization_updated_at": datetime.utcnow().isoformat(),
            }

            # Add optional fields if present
            if "psc_family_count" in raw:
                props["categorization_psc_family_count"] = _as_int(raw.get("psc_family_count"))

            if "total_dollars" in raw:
                props["categorization_total_dollars"] = _as_float(raw.get("total_dollars"))

            if "product_dollars" in raw:
                props["categorization_product_dollars"] = _as_float(raw.get("product_dollars"))

            if "service_dollars" in raw:
                props["categorization_service_dollars"] = _as_float(raw.get("service_dollars"))

            if "agency_breakdown" in raw:
                agency_breakdown = raw.get("agency_breakdown")
                if isinstance(agency_breakdown, dict):
                    props["categorization_agency_breakdown"] = agency_breakdown

            if raw.get("override_reason"):
                props["categorization_override_reason"] = _as_str(raw.get("override_reason"))

            categorization_data.append({"uei": uei, "props": props})

        if not categorization_data:
            logger.info("No valid categorizations to load")
            return metrics

        # Batch update Company nodes
        logger.info(
            "Loading {} company categorizations in batches of {}",
            len(categorization_data),
            self.config.batch_size,
        )

        # Process in batches
        for i in range(0, len(categorization_data), self.config.batch_size):
            batch = categorization_data[i : i + self.config.batch_size]

            # Build Cypher query for batch update using query builder
            from ..query_builder import Neo4jQueryBuilder

            if self.config.update_existing_only:
                # Only update existing Company nodes (safer)
                query = Neo4jQueryBuilder.build_batch_match_update_query(
                    label="Company",
                    key_property="uei",
                    return_count=True,
                )
            else:
                # Create Company node if it doesn't exist (more permissive)
                query = Neo4jQueryBuilder.build_batch_merge_query(
                    label="Company",
                    key_property="uei",
                    include_hash_check=False,
                    return_counts=True,
                )

            try:
                with self.client.session() as session:
                    result = session.run(query, {"batch": batch})
                    record = result.single()
                    if record:
                        updated = record["updated_count"]
                        metrics.nodes_updated["Company"] = (
                            metrics.nodes_updated.get("Company", 0) + updated
                        )
                        logger.debug(
                            "Batch {}-{}: Updated {} Company nodes",
                            i,
                            i + len(batch),
                            updated,
                        )
            except Exception as exc:
                logger.error(
                    "Failed to update Company nodes in batch {}-{}: {}", i, i + len(batch), exc
                )
                metrics.errors += len(batch)

        logger.info(
            "Company categorization loading complete: {} companies updated, {} errors",
            metrics.nodes_updated.get("Company", 0),
            metrics.errors,
        )

        return metrics


# -------------------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------------------


def _as_str(val: Any) -> str | None:
    """Convert value to string or None."""
    if val is None or val == "":
        return None
    return str(val)


def _as_int(val: Any) -> int | None:
    """Convert value to int or None."""
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _as_float(val: Any) -> float | None:
    """Convert value to float or None."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
