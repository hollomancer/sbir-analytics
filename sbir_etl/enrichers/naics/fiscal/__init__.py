"""
Fiscal NAICS enrichment with strategy pattern.

This module provides a refactored, strategy-based implementation of fiscal
NAICS enrichment. The enricher tries multiple strategies in order of confidence
until one succeeds.

Strategies (in order):
1. Original SBIR data (0.95 confidence)
2. USAspending DataFrame lookups (0.85 confidence)
3. Topic code mapping (0.75 confidence)
4. Text-based inference (0.65 confidence)
5. Agency defaults (0.50 confidence)
6. Sector fallback (0.30 confidence)

Public API:
- FiscalNAICSEnricher: Main orchestrator class
- enrich_sbir_awards_with_fiscal_naics: Convenience function
- NAICSEnrichmentResult: Result data class
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from .enricher import FiscalNAICSEnricher
from .strategies import NAICSEnrichmentResult


if TYPE_CHECKING:
    from .strategies.base import EnrichmentStrategy


__all__ = [
    "FiscalNAICSEnricher",
    "NAICSEnrichmentResult",
    "enrich_sbir_awards_with_fiscal_naics",
]


def enrich_sbir_awards_with_fiscal_naics(
    awards_df: pd.DataFrame,
    usaspending_df: pd.DataFrame | None = None,
    config: dict[str, Any] | None = None,
    strategies: list[EnrichmentStrategy] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Convenience function to enrich SBIR awards with fiscal NAICS codes.

    This function provides backward compatibility with the original module API.

    Args:
        awards_df: SBIR awards DataFrame
        usaspending_df: Optional USAspending data for enrichment
        config: Optional configuration override
        strategies: Optional explicit strategy chain. When omitted the enricher
            uses the deterministic pipelines default (no text inference);
            exploratory callers wanting keyword text inference pass
            ``fiscal_strategies_with_text_inference(...)`` from
            ``sbir_etl.enrichers.naics.fiscal.exploratory_strategies``.

    Returns:
        Tuple of (enriched DataFrame, quality metrics)
    """
    enricher = FiscalNAICSEnricher(
        config=config, usaspending_df=usaspending_df, strategies=strategies
    )
    enriched_df = enricher.enrich_awards_dataframe(awards_df, usaspending_df)
    quality_metrics = enricher.validate_enrichment_quality(enriched_df)

    return enriched_df, quality_metrics
