"""Simple NAICS enrichment strategies based on static lookups.

Contains strategies that use direct field extraction, topic code mappings,
agency defaults, and sector fallback — all based on static data without
external dependencies.
"""

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


class TopicCodeStrategy(EnrichmentStrategy):
    """Map SBIR topic codes to NAICS codes."""

    # Topic code prefix to NAICS mappings
    TOPIC_CODE_NAICS_MAPPINGS = {
        "AF": "3364",  # Aerospace
        "ARMY": "3364",  # Defense manufacturing
        "NAVY": "3364",  # Naval systems
        "DOD": "3364",
        "NIH": "5417",  # Biomedical research
        "HHS": "5417",
        "DOE": "5417",  # Energy R&D
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
        topic_cols = ["Topic", "topic", "Topic_Code", "topic_code", "Program_Topic"]

        for col in topic_cols:
            if col not in award_row.index or pd.isna(award_row[col]):
                continue

            topic_value = str(award_row[col]).strip().upper()

            for topic_prefix, naics_code in self.TOPIC_CODE_NAICS_MAPPINGS.items():
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


class AgencyDefaultsStrategy(EnrichmentStrategy):
    """Use default NAICS codes based on funding agency."""

    AGENCY_DEFAULTS = {
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

    # Patterns for partial agency name matching (longer/more specific first)
    AGENCY_PATTERNS = [
        ("DEPARTMENT OF DEFENSE", "DOD"),
        ("HUMAN SERVICES", "HHS"),
        ("SCIENCE FOUNDATION", "NSF"),
        ("HOMELAND SECURITY", "DHS"),
        ("DEFENSE", "DOD"),
        ("HEALTH", "HHS"),
        ("ENERGY", "DOE"),
        ("AERONAUTICS", "NASA"),
        ("SPACE", "NASA"),
        ("AGRICULTURE", "USDA"),
        ("TRANSPORTATION", "DOT"),
        ("COMMERCE", "DOC"),
    ]

    @property
    def strategy_name(self) -> str:
        return "agency_defaults"

    @property
    def confidence_level(self) -> float:
        return 0.50

    def enrich(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        agency_cols = ["Agency", "agency", "Funding_Agency", "funding_agency", "Awarding_Agency"]

        for col in agency_cols:
            if col not in award_row.index or pd.isna(award_row[col]):
                continue

            agency_value = str(award_row[col]).strip().upper()

            # Exact match
            if agency_value in self.AGENCY_DEFAULTS:
                naics_code = self.AGENCY_DEFAULTS[agency_value]
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

            # Pattern match
            for pattern, agency_key in self.AGENCY_PATTERNS:
                if pattern in agency_value and agency_key in self.AGENCY_DEFAULTS:
                    naics_code = self.AGENCY_DEFAULTS[agency_key]
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

            # Substring match
            for agency_key, naics_code in self.AGENCY_DEFAULTS.items():
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


class SectorFallbackStrategy(EnrichmentStrategy):
    """Always returns a default sector NAICS code as last resort."""

    def __init__(self, fallback_code: str = "5415"):
        self.fallback_code = fallback_code

    @property
    def strategy_name(self) -> str:
        return "sector_fallback"

    @property
    def confidence_level(self) -> float:
        return 0.30

    def enrich(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        normalized = normalize_naics_code(self.fallback_code)
        if normalized:
            return NAICSEnrichmentResult(
                naics_code=normalized,
                confidence=self.confidence_level,
                source=self.strategy_name,
                method="default_fallback",
                timestamp=datetime.now(),
                metadata={
                    "fallback_code": self.fallback_code,
                    "reason": "no_other_strategy_succeeded",
                },
            )
        return None
