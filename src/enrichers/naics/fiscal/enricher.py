"""Fiscal NAICS enricher using strategy pattern."""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from ....config.loader import get_config
from .strategies import (
    AgencyDefaultsStrategy,
    NAICSEnrichmentResult,
    OriginalDataStrategy,
    SectorFallbackStrategy,
    TextInferenceStrategy,
    TopicCodeStrategy,
    USAspendingDataFrameStrategy,
)


class FiscalNAICSEnricher:
    """NAICS enrichment service using pluggable strategy pattern.

    This orchestrator tries multiple enrichment strategies in order of
    confidence until one succeeds. Strategies can be easily added, removed,
    or reordered.

    Fallback chain (default):
    1. Original SBIR data (confidence: 0.95)
    2. USAspending DataFrame lookups (confidence: 0.85-0.90)
    3. Topic code mapping (confidence: 0.75)
    4. Text-based inference (confidence: 0.65)
    5. Agency defaults (confidence: 0.50)
    6. Sector fallback (confidence: 0.30)
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        usaspending_df: pd.DataFrame | None = None,
        api_client: Any | None = None,
    ):
        """Initialize the NAICS enricher with strategies.

        Args:
            config: Optional configuration override
            usaspending_df: Optional USAspending DataFrame for lookups
            api_client: Optional API client (for future API-based strategies)
        """
        from src.config.schemas.fiscal import FiscalAnalysisConfig

        config_obj = config or get_config().fiscal_analysis
        # Handle both dict and FiscalAnalysisConfig objects
        if isinstance(config_obj, dict):
            self.config = FiscalAnalysisConfig(**config_obj)
        else:
            self.config = config_obj
        self.quality_thresholds = self.config.quality_thresholds
        self.usaspending_df = usaspending_df
        self.api_client = api_client

        # Initialize strategies in order of confidence
        self.strategies = [
            OriginalDataStrategy(),
            USAspendingDataFrameStrategy(usaspending_df=usaspending_df, confidence=0.85),
            TopicCodeStrategy(),
            TextInferenceStrategy(),
            AgencyDefaultsStrategy(),
            SectorFallbackStrategy(fallback_code="5415"),
        ]

        logger.info(
            f"Initialized FiscalNAICSEnricher with {len(self.strategies)} strategies "
            f"(confidence range: 0.30-0.95)"
        )

    def enrich_single_award(
        self,
        award_row: pd.Series,
        min_confidence: float = 0.0,
    ) -> NAICSEnrichmentResult:
        """Enrich a single award using the strategy chain.

        Args:
            award_row: SBIR award row
            min_confidence: Minimum confidence threshold (default: 0.0 = accept all)

        Returns:
            NAICSEnrichmentResult from first successful strategy
        """
        for strategy in self.strategies:
            try:
                result = strategy.enrich(award_row)
                if result and result.confidence >= min_confidence:
                    return result
            except Exception as e:
                logger.warning(
                    f"Strategy {strategy.strategy_name} failed for award: {e}",
                    exc_info=False,
                )
                continue

        # If all strategies fail (should never happen with fallback), return a default
        return NAICSEnrichmentResult(
            naics_code=None,
            confidence=0.0,
            source="error",
            method="all_strategies_failed",
            timestamp=pd.Timestamp.now(),
            metadata={"error": "All enrichment strategies failed"},
        )

    def enrich_awards_dataframe(
        self,
        awards_df: pd.DataFrame,
        usaspending_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Enrich multiple awards with NAICS codes.

        Args:
            awards_df: DataFrame of SBIR awards
            usaspending_df: Optional USAspending data for enrichment

        Returns:
            Enriched DataFrame with NAICS columns
        """
        if awards_df.empty:
            logger.warning("Empty awards DataFrame provided to fiscal NAICS enricher")
            return pd.DataFrame()

        # Update USAspending DataFrame if provided
        if usaspending_df is not None:
            self.usaspending_df = usaspending_df
            # Update the USAspending strategy
            for i, strategy in enumerate(self.strategies):
                if isinstance(strategy, USAspendingDataFrameStrategy):
                    self.strategies[i] = USAspendingDataFrameStrategy(
                        usaspending_df=usaspending_df,
                        confidence=0.85,
                    )

        logger.info(f"Enriching {len(awards_df)} awards with fiscal NAICS codes")

        # Enrich each award
        results = []
        for _idx, row in awards_df.iterrows():
            result = self.enrich_single_award(row)
            results.append(
                {
                    "fiscal_naics_code": result.naics_code,
                    "fiscal_naics_source": result.source,
                    "fiscal_naics_method": result.method,
                    "fiscal_naics_confidence": result.confidence,
                    "fiscal_naics_metadata": result.metadata,
                }
            )

        # Combine with original DataFrame
        enriched_df = pd.concat([awards_df.reset_index(drop=True), pd.DataFrame(results)], axis=1)

        # Log statistics
        naics_coverage = enriched_df["fiscal_naics_code"].notna().sum()
        coverage_rate = naics_coverage / len(enriched_df) if len(enriched_df) > 0 else 0

        # Source distribution
        source_counts = enriched_df["fiscal_naics_source"].value_counts().to_dict()

        logger.info(
            f"Fiscal NAICS enrichment complete: {naics_coverage}/{len(enriched_df)} "
            f"({coverage_rate:.1%} coverage)",
            extra={"source_distribution": source_counts},
        )

        return enriched_df

    def validate_enrichment_quality(self, enriched_df: pd.DataFrame) -> dict[str, Any]:
        """Validate enrichment quality metrics.

        Args:
            enriched_df: Enriched DataFrame with NAICS columns

        Returns:
            Dictionary with quality metrics
        """
        if enriched_df.empty:
            return {
                "coverage_meets_threshold": False,
                "naics_coverage": 0.0,
                "error": "Empty DataFrame",
            }

        total_awards = len(enriched_df)
        naics_coverage = enriched_df["fiscal_naics_code"].notna().sum()
        coverage_rate = naics_coverage / total_awards if total_awards > 0 else 0.0

        # Get confidence statistics
        confidences = enriched_df["fiscal_naics_confidence"].dropna()
        avg_confidence = float(confidences.mean()) if not confidences.empty else 0.0

        # Count by confidence bands
        high_confidence_count = (confidences >= 0.80).sum() if not confidences.empty else 0
        medium_confidence_count = (
            ((confidences >= 0.60) & (confidences < 0.80)).sum() if not confidences.empty else 0
        )
        low_confidence_count = (confidences < 0.60).sum() if not confidences.empty else 0

        # Source distribution
        source_counts = enriched_df["fiscal_naics_source"].value_counts().to_dict()

        # Quality threshold check
        naics_coverage_threshold = getattr(
            self.quality_thresholds, "naics_coverage_threshold", 0.85
        )
        coverage_meets_threshold = coverage_rate >= naics_coverage_threshold

        return {
            "coverage_meets_threshold": coverage_meets_threshold,
            "naics_coverage": coverage_rate,
            "naics_coverage_threshold": naics_coverage_threshold,
            "total_awards": total_awards,
            "enriched_count": int(naics_coverage),
            "confidence_bands": {
                "high_confidence": int(high_confidence_count),
                "medium_confidence": int(medium_confidence_count),
                "low_confidence": int(low_confidence_count),
            },
            "source_distribution": source_counts,
            "average_confidence": avg_confidence,
            "fallback_usage_rate": source_counts.get("sector_fallback", 0) / total_awards
            if total_awards > 0
            else 0,
        }
