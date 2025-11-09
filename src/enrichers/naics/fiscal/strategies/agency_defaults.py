"""Strategy for NAICS enrichment from agency defaults."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..utils import normalize_naics_code
from .base import EnrichmentStrategy, NAICSEnrichmentResult


class AgencyDefaultsStrategy(EnrichmentStrategy):
    """Use default NAICS codes based on funding agency."""

    def __init__(self) -> None:
        """Initialize agency default mappings."""
        # Agency default NAICS mappings
        self.agency_defaults = {
            "DOD": "3364",  # Aerospace product and parts manufacturing
            "ARMY": "3364",
            "NAVY": "3364",
            "AIR FORCE": "3364",
            "HHS": "5417",  # Scientific research and development services
            "NIH": "5417",
            "CDC": "5417",
            "DOE": "5417",  # Energy research and development
            "NASA": "5417",  # Space research and development
            "NSF": "5417",  # Scientific research
            "EPA": "5417",  # Environmental research
            "USDA": "5417",  # Agricultural research
            "DHS": "5415",  # Computer systems design services
            "DOT": "5415",  # Transportation research
            "DOC": "5415",  # Commerce and technology research
            "NIST": "5415",  # Standards and technology research
        }

    @property
    def strategy_name(self) -> str:
        return "agency_defaults"

    @property
    def confidence_level(self) -> float:
        return 0.50

    def enrich(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Map agency to default NAICS code.

        Args:
            award_row: SBIR award row

        Returns:
            NAICS enrichment result or None
        """
        # Try to extract agency from common columns
        agency_cols = ["Agency", "agency", "Funding_Agency", "funding_agency", "Awarding_Agency"]

        for col in agency_cols:
            if col not in award_row.index or pd.isna(award_row[col]):
                continue

            agency_value = str(award_row[col]).strip().upper()

            # Check for exact match
            if agency_value in self.agency_defaults:
                naics_code = self.agency_defaults[agency_value]
                normalized = normalize_naics_code(naics_code)
                if normalized:
                    return NAICSEnrichmentResult(
                        naics_code=normalized,
                        confidence=self.confidence_level,
                        source=self.strategy_name,
                        method="agency_default",
                        timestamp=datetime.now(),
                        metadata={"agency": agency_value, "column": col},
                    )

            # Check for partial match (e.g., "Department of Defense" contains "DOD")
            for agency_key, naics_code in self.agency_defaults.items():
                if agency_key in agency_value:
                    normalized = normalize_naics_code(naics_code)
                    if normalized:
                        return NAICSEnrichmentResult(
                            naics_code=normalized,
                            confidence=self.confidence_level,
                            source=self.strategy_name,
                            method="agency_default_partial",
                            timestamp=datetime.now(),
                            metadata={
                                "agency": agency_value,
                                "matched_key": agency_key,
                                "column": col,
                            },
                        )

        return None
