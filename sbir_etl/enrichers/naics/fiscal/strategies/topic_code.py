"""Strategy for NAICS enrichment from SBIR topic codes."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..utils import normalize_naics_code
from .base import EnrichmentStrategy, NAICSEnrichmentResult


class TopicCodeStrategy(EnrichmentStrategy):
    """Map SBIR topic codes to NAICS codes."""

    def __init__(self) -> None:
        """Initialize topic code mappings."""
        # Topic code to NAICS mappings (agency-specific)
        self.topic_code_naics_mappings = {
            # DoD/Air Force topics
            "AF": "3364",  # Aerospace
            "ARMY": "3364",  # Defense manufacturing
            "NAVY": "3364",  # Naval systems
            "DOD": "3364",
            # Health/Medical topics
            "NIH": "5417",  # Biomedical research
            "HHS": "5417",
            # Energy topics
            "DOE": "5417",  # Energy R&D
            # Technology/Software topics
            "ST": "5415",  # Software/tech
            "IT": "5415",  # Information technology
            "AI": "5415",  # Artificial intelligence
            "ML": "5415",  # Machine learning
        }

    @property
    def strategy_name(self) -> str:
        return "topic_code"

    @property
    def confidence_level(self) -> float:
        return 0.75

    def enrich(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Map topic code to NAICS code.

        Args:
            award_row: SBIR award row

        Returns:
            NAICS enrichment result or None
        """
        # Try to extract topic code from common columns
        topic_cols = ["Topic", "topic", "Topic_Code", "topic_code", "Program_Topic"]

        for col in topic_cols:
            if col not in award_row.index or pd.isna(award_row[col]):
                continue

            topic_value = str(award_row[col]).strip().upper()

            # Try direct topic code match
            for topic_prefix, naics_code in self.topic_code_naics_mappings.items():
                if topic_value.startswith(topic_prefix):
                    normalized = normalize_naics_code(naics_code)
                    if normalized:
                        return NAICSEnrichmentResult(
                            naics_code=normalized,
                            confidence=self.confidence_level,
                            source=self.strategy_name,
                            method="topic_code_mapping",
                            timestamp=datetime.now(),
                            metadata={"topic_code": topic_value, "matched_prefix": topic_prefix},
                        )

        return None
