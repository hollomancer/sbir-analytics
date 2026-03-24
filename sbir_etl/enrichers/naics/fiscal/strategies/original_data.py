"""Strategy for extracting NAICS from original SBIR data."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..utils import normalize_naics_code
from .base import EnrichmentStrategy, NAICSEnrichmentResult


class OriginalDataStrategy(EnrichmentStrategy):
    """Extract NAICS from original SBIR award data fields."""

    @property
    def strategy_name(self) -> str:
        return "original_data"

    @property
    def confidence_level(self) -> float:
        return 0.95

    def enrich(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Extract NAICS from original SBIR data.

        Args:
            award_row: SBIR award row

        Returns:
            NAICS enrichment result or None
        """
        # Check common NAICS column names
        naics_columns = ["NAICS", "naics", "NAICS_Code", "naics_code", "Primary_NAICS"]

        for col in naics_columns:
            if col in award_row.index and pd.notna(award_row[col]):
                naics_code = normalize_naics_code(str(award_row[col]))
                if naics_code:
                    return NAICSEnrichmentResult(
                        naics_code=naics_code,
                        confidence=self.confidence_level,
                        source=self.strategy_name,
                        method="direct_field",
                        timestamp=datetime.now(),
                        metadata={"original_column": col, "original_value": str(award_row[col])},
                    )

        return None
