"""Company Categorization Loader for Neo4j Graph Operations.

This module loads company categorization data into Neo4j, enriching existing
``:Organization`` nodes with Product/Service/Mixed classification properties
derived from USAspending contract portfolio analysis.

Responsibilities:
  - Add categorization properties to existing Organization nodes (matched by ``uei``)
  - Update existing nodes only (MATCH-and-SET, never create)
  - Track classification metadata (confidence, award counts, etc.)
  - Support batch operations for performance

The loader updates Organization nodes with:
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

from .base import BaseLoaderConfig, BaseNeo4jLoader
from .client import LoadMetrics, Neo4jClient


class CompanyCategorizationLoaderConfig(BaseLoaderConfig):
    """Configuration for company categorization loading operations."""


class CompanyCategorizationLoader(BaseNeo4jLoader):
    """Loads company categorization data into Neo4j :Organization nodes.

    Enriches existing :Organization nodes with classification properties based
    on USAspending contract portfolio analysis. Uses MATCH-and-SET semantics
    (existing nodes only, matched by ``uei``) to support idempotent reprocessing.

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
            "CompanyCategorizationLoader initialized with batch_size={}, create_indexes={}",
            self.config.batch_size,
            self.config.create_indexes,
        )

    # -------------------------------------------------------------------------
    # Schema management
    # -------------------------------------------------------------------------

    def create_indexes(self, indexes: list[str] | None = None) -> None:  # type: ignore[override]
        """Create indexes for categorization properties on Organization nodes."""
        if indexes is None:
            indexes = [
                # Index on classification for filtering queries
                "CREATE INDEX org_classification_idx IF NOT EXISTS "
                "FOR (o:Organization) ON (o.classification)",
                # Index on confidence for quality filtering
                "CREATE INDEX org_categorization_confidence_idx IF NOT EXISTS "
                "FOR (o:Organization) ON (o.categorization_confidence)",
                # Composite index for classification + confidence queries
                "CREATE INDEX org_classification_confidence_idx IF NOT EXISTS "
                "FOR (o:Organization) ON (o.classification, o.categorization_confidence)",
            ]
        super().create_indexes(indexes)

    # -------------------------------------------------------------------------
    # Organization categorization enrichment
    # -------------------------------------------------------------------------

    def load_categorizations(
        self,
        categorizations: Iterable[dict[str, Any]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Enrich :Organization nodes with categorization properties.

        Each categorization dict should include:
          - company_uei (required): UEI to match the Organization node
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

            # Flatten props alongside the match key for MATCH-and-SET.
            categorization_data.append({"uei": uei, **props})

        if not categorization_data:
            logger.info("No valid categorizations to load")
            return metrics

        # Update existing :Organization nodes only (MATCH-and-SET, never create).
        # MATCHing on the non-key ``uei`` property is correct here: the firm's key is
        # ``organization_id``, so a MERGE on ``uei`` would mint a duplicate Organization.
        self.client.config.batch_size = self.config.batch_size
        metrics = self.client.batch_set_existing_node_properties(
            label="Organization",
            key_property="uei",
            nodes=categorization_data,
            metrics=metrics,
        )

        logger.info(
            "Organization categorization loading complete: {} organizations updated, {} errors",
            metrics.nodes_updated.get("Organization", 0),
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
