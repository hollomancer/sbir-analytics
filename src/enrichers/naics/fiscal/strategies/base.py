"""Base strategy for NAICS enrichment."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass
class NAICSEnrichmentResult:
    """Result of NAICS enrichment with confidence and source tracking."""

    naics_code: str | None
    confidence: float
    source: str
    method: str
    timestamp: datetime
    metadata: dict[str, Any]


class EnrichmentStrategy(ABC):
    """Abstract base class for NAICS enrichment strategies."""

    @abstractmethod
    def enrich(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Attempt to enrich the award with NAICS code.

        Args:
            award_row: SBIR award row data

        Returns:
            NAICSEnrichmentResult if successful, None otherwise
        """
        pass

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Return the name of this strategy."""
        pass

    @property
    @abstractmethod
    def confidence_level(self) -> float:
        """Return the confidence level for this strategy."""
        pass
