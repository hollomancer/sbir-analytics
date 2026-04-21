"""SEC EDGAR Loader for Neo4j Graph Operations.

Enriches existing Company nodes with SEC EDGAR public filing data including
CIK identifiers, financial metrics, and M&A event signals.

Properties added to Company nodes:
  - sec_cik: Central Index Key (SEC identifier)
  - sec_is_publicly_traded: Boolean flag
  - sec_ticker: Stock ticker symbol
  - sec_sic_code: Standard Industrial Classification
  - sec_match_confidence: CIK resolution confidence (0-1)
  - sec_latest_revenue: Most recent annual revenue (USD)
  - sec_latest_rd_expense: Most recent R&D expense (USD)
  - sec_latest_total_assets: Most recent total assets (USD)
  - sec_latest_net_income: Most recent net income (USD)
  - sec_financials_as_of: Date of latest financial data
  - sec_ma_event_count: Number of M&A events detected
  - sec_total_filings: Total SEC filings found
  - sec_enriched_at: Timestamp of enrichment
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from loguru import logger
from pydantic import Field

from .base import BaseLoaderConfig, BaseNeo4jLoader
from .client import LoadMetrics, Neo4jClient


class SecEdgarLoaderConfig(BaseLoaderConfig):
    """Configuration for SEC EDGAR loading operations."""

    update_existing_only: bool = Field(
        default=True,
        description="Only update existing Company nodes (do not create new ones)",
    )


class SecEdgarLoader(BaseNeo4jLoader):
    """Loads SEC EDGAR enrichment data into Neo4j Company nodes.

    Enriches existing Company nodes with public filing data from SEC EDGAR.
    Uses idempotent MERGE operations for safe reprocessing.
    """

    def __init__(
        self,
        client: Neo4jClient,
        config: SecEdgarLoaderConfig | None = None,
    ) -> None:
        super().__init__(client)
        self.config = config or SecEdgarLoaderConfig()
        logger.info(
            "SecEdgarLoader initialized with batch_size={}, update_existing_only={}",
            self.config.batch_size,
            self.config.update_existing_only,
        )

    def create_indexes(self, indexes: list[str] | None = None) -> None:  # type: ignore[override]
        """Create indexes for SEC EDGAR properties on Company nodes."""
        if indexes is None:
            indexes = [
                "CREATE INDEX company_sec_cik_idx IF NOT EXISTS "
                "FOR (c:Company) ON (c.sec_cik)",
                "CREATE INDEX company_sec_publicly_traded_idx IF NOT EXISTS "
                "FOR (c:Company) ON (c.sec_is_publicly_traded)",
                "CREATE INDEX company_sec_ticker_idx IF NOT EXISTS "
                "FOR (c:Company) ON (c.sec_ticker)",
            ]
        super().create_indexes(indexes)

    def load_sec_edgar_data(
        self,
        enrichments: Iterable[dict[str, Any]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Enrich Company nodes with SEC EDGAR data.

        Each enrichment dict should include:
          - company_uei (required): UEI to match Company node
          - sec_cik: CIK identifier
          - sec_is_publicly_traded: Boolean
          - sec_ticker: Ticker symbol
          - sec_match_confidence: Match confidence (0-1)
          - sec_latest_revenue, sec_latest_rd_expense, etc.: Financial data

        Args:
            enrichments: Iterable of enrichment dicts.
            metrics: Optional existing LoadMetrics to accumulate into.

        Returns:
            LoadMetrics with update counts.
        """
        if metrics is not None:
            self.metrics = metrics

        enrichment_list = list(enrichments)
        if not enrichment_list:
            logger.info("SecEdgarLoader: No enrichments to load")
            return self.metrics

        def _has_sec_signal(record: dict[str, Any]) -> bool:
            """Return True when a record contains any meaningful SEC data.

            Filters out mention-only records with high noise scores
            (score >= 2 indicates likely false positives from generic names).
            """
            if record.get("sec_is_publicly_traded") or record.get("sec_cik"):
                return True
            if record.get("sec_has_form_d"):
                return True
            # Model field is mention_count, prefixed to sec_mention_count by enricher
            inbound = record.get("sec_mention_count")
            if isinstance(inbound, int | float) and inbound > 0:
                noise = record.get("sec_mention_noise_score", 0)
                if isinstance(noise, int | float) and noise >= 2:
                    return False
                return True
            return False

        # Keep records with any meaningful SEC signal, including private-company signals
        sec_records = [r for r in enrichment_list if _has_sec_signal(r)]

        logger.info(
            f"SecEdgarLoader: Loading SEC EDGAR data for {len(sec_records)} "
            f"companies with SEC signals (of {len(enrichment_list)} total)"
        )

        # Build enrichment tuples for base class method
        enrichment_tuples: list[tuple[str, dict[str, Any]]] = []
        for record in sec_records:
            # Accept both "uei" and "company_uei" as the UEI key
            uei = record.get("company_uei") or record.get("uei")
            if not uei:
                self.metrics.errors += 1
                continue

            props: dict[str, Any] = {
                "sec_enriched_at": datetime.now().isoformat(),
            }
            # Copy all sec_ prefixed properties
            for key, value in record.items():
                if key.startswith("sec_") and value is not None:
                    # Convert date objects to strings for Neo4j
                    if hasattr(value, "isoformat"):
                        props[key] = value.isoformat()
                    else:
                        props[key] = value

            enrichment_tuples.append((uei, props))

        if enrichment_tuples:
            self.enrich_node_properties(
                label="Company",
                key_property="uei",
                enrichments=enrichment_tuples,
            )

        return self.metrics
