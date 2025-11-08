"""Strategy for NAICS enrichment from USAspending DataFrame lookups."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..utils import normalize_naics_code
from .base import EnrichmentStrategy, NAICSEnrichmentResult


class USAspendingDataFrameStrategy(EnrichmentStrategy):
    """Enrich NAICS from USAspending DataFrame (non-API lookups)."""

    def __init__(self, usaspending_df: pd.DataFrame | None = None, confidence: float = 0.85):
        """Initialize with optional USAspending DataFrame.

        Args:
            usaspending_df: DataFrame with USAspending data
            confidence: Confidence level for this strategy
        """
        self.usaspending_df = usaspending_df
        self._confidence = confidence

    @property
    def strategy_name(self) -> str:
        return "usaspending_dataframe"

    @property
    def confidence_level(self) -> float:
        return self._confidence

    def enrich(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Enrich from USAspending DataFrame lookups.

        Args:
            award_row: SBIR award row

        Returns:
            NAICS enrichment result or None
        """
        if self.usaspending_df is None or self.usaspending_df.empty:
            return None

        # Try UEI match
        uei_cols = ["UEI", "uei", "recipient_uei", "Recipient_UEI"]
        for col in uei_cols:
            if col not in award_row.index or pd.isna(award_row[col]):
                continue

            uei = str(award_row[col]).strip()
            if not uei:
                continue

            # Look up in USAspending DataFrame
            matches = self.usaspending_df[
                self.usaspending_df.get("recipient_uei", pd.Series()).eq(uei)
            ]

            if not matches.empty:
                # Extract NAICS from first match
                naics_cols = ["naics_code", "primary_naics", "recipient_naics"]
                for naics_col in naics_cols:
                    if naics_col in matches.columns:
                        naics_value = matches.iloc[0][naics_col]
                        if pd.notna(naics_value):
                            normalized = normalize_naics_code(str(naics_value))
                            if normalized:
                                return NAICSEnrichmentResult(
                                    naics_code=normalized,
                                    confidence=self.confidence_level,
                                    source=self.strategy_name,
                                    method="uei_lookup",
                                    timestamp=datetime.now(),
                                    metadata={"uei": uei, "match_count": len(matches)},
                                )

        # Try DUNS match
        duns_cols = ["DUNS", "duns", "Duns", "recipient_duns"]
        for col in duns_cols:
            if col not in award_row.index or pd.isna(award_row[col]):
                continue

            duns = str(award_row[col]).strip()
            if not duns:
                continue

            # Look up in USAspending DataFrame
            matches = self.usaspending_df[
                self.usaspending_df.get("recipient_duns", pd.Series()).eq(duns)
            ]

            if not matches.empty:
                # Extract NAICS from first match
                naics_cols = ["naics_code", "primary_naics", "recipient_naics"]
                for naics_col in naics_cols:
                    if naics_col in matches.columns:
                        naics_value = matches.iloc[0][naics_col]
                        if pd.notna(naics_value):
                            normalized = normalize_naics_code(str(naics_value))
                            if normalized:
                                return NAICSEnrichmentResult(
                                    naics_code=normalized,
                                    confidence=self.confidence_level * 0.95,  # Slightly lower for DUNS
                                    source=self.strategy_name,
                                    method="duns_lookup",
                                    timestamp=datetime.now(),
                                    metadata={"duns": duns, "match_count": len(matches)},
                                )

        return None
