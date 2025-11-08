"""Strategy for NAICS enrichment from text inference."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..utils import normalize_naics_code
from .base import EnrichmentStrategy, NAICSEnrichmentResult


class TextInferenceStrategy(EnrichmentStrategy):
    """Infer NAICS from award abstract/title text."""

    def __init__(self):
        """Initialize keyword patterns."""
        # Keyword patterns for text-based NAICS inference
        self.naics_keyword_patterns = {
            "5417": [  # Scientific R&D services
                "research",
                "development",
                "biomedical",
                "biotech",
                "pharmaceutical",
                "clinical trial",
                "drug",
                "therapeutic",
                "vaccine",
                "diagnostic",
                "genetic",
                "molecular",
                "protein",
                "enzyme",
                "antibody",
            ],
            "5415": [  # Computer systems design
                "software",
                "algorithm",
                "artificial intelligence",
                "machine learning",
                "data",
                "analytics",
                "cyber",
                "network",
                "database",
                "cloud",
                "computing",
                "system",
                "platform",
                "application",
                "digital",
            ],
            "3364": [  # Aerospace manufacturing
                "aerospace",
                "aircraft",
                "missile",
                "rocket",
                "propulsion",
                "engine",
                "satellite",
                "space",
                "defense",
                "military",
                "drone",
                "uav",
            ],
            "5416": [  # Management consulting
                "consulting",
                "management",
                "strategic",
                "planning",
                "analysis",
            ],
            "5413": [  # Architectural/engineering services
                "engineering",
                "design",
                "architectural",
                "technical",
            ],
        }

    @property
    def strategy_name(self) -> str:
        return "text_inference"

    @property
    def confidence_level(self) -> float:
        return 0.65

    def enrich(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Infer NAICS from text content.

        Args:
            award_row: SBIR award row

        Returns:
            NAICS enrichment result or None
        """
        # Collect text from common fields
        text_cols = ["Abstract", "abstract", "Title", "title", "Description", "description"]
        text_content = []

        for col in text_cols:
            if col in award_row.index and pd.notna(award_row[col]):
                text_content.append(str(award_row[col]).lower())

        if not text_content:
            return None

        combined_text = " ".join(text_content)

        # Score each NAICS code by keyword matches
        scores: dict[str, int] = {}

        for naics_code, keywords in self.naics_keyword_patterns.items():
            match_count = sum(1 for keyword in keywords if keyword.lower() in combined_text)
            if match_count > 0:
                scores[naics_code] = match_count

        if not scores:
            return None

        # Select NAICS with highest score
        best_naics = max(scores, key=scores.get)  # type: ignore
        match_count = scores[best_naics]

        # Require at least 2 keyword matches for confidence
        if match_count < 2:
            return None

        normalized = normalize_naics_code(best_naics)
        if normalized:
            return NAICSEnrichmentResult(
                naics_code=normalized,
                confidence=self.confidence_level,
                source=self.strategy_name,
                method="keyword_inference",
                timestamp=datetime.now(),
                metadata={
                    "keyword_matches": match_count,
                    "text_sources": [col for col in text_cols if col in award_row.index],
                },
            )

        return None
