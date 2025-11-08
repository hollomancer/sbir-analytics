"""Strategy for NAICS enrichment with sector fallback."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..utils import normalize_naics_code
from .base import EnrichmentStrategy, NAICSEnrichmentResult


class SectorFallbackStrategy(EnrichmentStrategy):
    """Always returns a default sector NAICS code as last resort."""

    def __init__(self, fallback_code: str = "5415"):
        """Initialize with fallback code.

        Args:
            fallback_code: Default NAICS code (default: 5415 - Computer systems design)
        """
        self.fallback_code = fallback_code

    @property
    def strategy_name(self) -> str:
        return "sector_fallback"

    @property
    def confidence_level(self) -> float:
        return 0.30

    def enrich(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Return default sector NAICS code.

        Args:
            award_row: SBIR award row

        Returns:
            NAICS enrichment result (always succeeds)
        """
        normalized = normalize_naics_code(self.fallback_code)
        if normalized:
            return NAICSEnrichmentResult(
                naics_code=normalized,
                confidence=self.confidence_level,
                source=self.strategy_name,
                method="default_fallback",
                timestamp=datetime.now(),
                metadata={"fallback_code": self.fallback_code, "reason": "no_other_strategy_succeeded"},
            )

        # This should never happen unless fallback_code is invalid
        return None
