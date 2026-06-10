"""
NAICS-to-BEA Sector Mapper for fiscal returns analysis.

This module implements the core mapping logic to convert NAICS codes to BEA Input-Output
sectors using official crosswalks and hierarchical fallback strategies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pandas as pd
import yaml
from loguru import logger

from ..config.loader import get_config


@dataclass
class NAICSToBEAResult:
    """Result of NAICS-to-BEA mapping with confidence and metadata."""

    naics_code: str
    bea_sector_code: str
    bea_sector_name: str
    allocation_weight: float
    confidence: float
    source: str  # 'direct', 'hierarchical', 'fallback', 'weighted'
    crosswalk_version: str
    mapped_at: datetime
    metadata: dict[str, Any]


@dataclass
class BEAMappingStatistics:
    """Statistics for BEA mapping quality and coverage."""

    total_mappings: int
    successful_mappings: int
    failed_mappings: int
    coverage_rate: float
    avg_confidence: float
    min_confidence: float
    max_confidence: float
    source_distribution: dict[str, int]
    hierarchical_fallback_count: int
    weighted_allocation_count: int


class NAICSToBEAMapper:
    """Map NAICS codes to BEA Input-Output sectors using hierarchical fallback."""

    # 24-entry 2-digit NAICS prefix → BEA Summary sector code.
    # Ported from the deleted sbir_etl.transformers.naics_bea_mapper.NAICSBEAMapper so that
    # map_naics_to_bea_summary() has a last-resort fallback matching the deleted mapper's behavior.
    _SUMMARY_FALLBACK: MappingProxyType[str, str] = MappingProxyType(
        {
            "11": "11",  # Agriculture, forestry, fishing, and hunting
            "21": "21",  # Mining, quarrying, and oil and gas extraction
            "22": "22",  # Utilities
            "23": "23",  # Construction
            "31": "31-33",  # Manufacturing (Food, beverage, tobacco)
            "32": "31-33",  # Manufacturing (Textiles, apparel, leather)
            "33": "31-33",  # Manufacturing (Wood, paper, printing)
            "42": "42",  # Wholesale trade
            "44": "44-45",  # Retail trade (Motor vehicle and parts)
            "45": "44-45",  # Retail trade (General merchandise)
            "48": "48-49",  # Transportation and warehousing
            "49": "48-49",  # Transportation and warehousing
            "51": "51",  # Information
            "52": "52",  # Finance and insurance
            "53": "53",  # Real estate and rental and leasing
            "54": "54",  # Professional, scientific, and technical services
            "55": "55",  # Management of companies and enterprises
            "56": "56",  # Administrative and support services
            "61": "61",  # Educational services
            "62": "62",  # Health care and social assistance
            "71": "71",  # Arts, entertainment, and recreation
            "72": "72",  # Accommodation and food services
            "81": "81",  # Other services (except public administration)
            "92": "92",  # Public administration
        }
    )

    def __init__(
        self,
        crosswalk_path: str | Path | None = None,
        fallback_config_path: str | Path | None = None,
        config: Any | None = None,
    ) -> None:
        """Initialize the NAICS-to-BEA mapper.

        Args:
            crosswalk_path: Path to BEA crosswalk CSV file
            fallback_config_path: Path to fallback mappings YAML file
            config: Optional configuration override
        """
        self.config = config or get_config().fiscal_analysis

        # Load crosswalk from config if not specified
        if crosswalk_path is None:
            naics_config = getattr(self.config, "naics_to_bea", {})
            crosswalk_path = naics_config.get(
                "crosswalk_path", "data/reference/bea/naics_to_bea_crosswalk_2017.csv"
            )
        if fallback_config_path is None:
            naics_config = getattr(self.config, "naics_to_bea", {})
            fallback_config_path = naics_config.get(
                "fallback_path", "config/fiscal/naics_bea_mappings.yaml"
            )

        self.crosswalk_path = Path(crosswalk_path)
        self.fallback_config_path = Path(fallback_config_path)

        # Load data
        self.crosswalk_df: pd.DataFrame | None = None
        self.fallback_config: dict[str, Any] = {}
        self._load_data()

        # Configuration
        self.hierarchical_fallback = True
        self.min_confidence_threshold = 0.50
        self._load_configuration()

        # Cache for performance
        self._mapping_cache: dict[str, list[NAICSToBEAResult]] = {}

    def _load_data(self) -> None:
        """Load crosswalk data and fallback configurations."""
        # Load BEA crosswalk CSV
        if self.crosswalk_path.exists():
            try:
                self.crosswalk_df = pd.read_csv(self.crosswalk_path)
                # Normalize NAICS codes (remove leading zeros, ensure string)
                self.crosswalk_df["naics_code"] = (
                    self.crosswalk_df["naics_code"].astype(str).str.zfill(6)
                )
                # Ensure BEA sector codes are strings (pandas may parse short numeric
                # values such as "54" as int64 without an explicit dtype override)
                if "bea_sector_code" in self.crosswalk_df.columns:
                    self.crosswalk_df["bea_sector_code"] = (
                        self.crosswalk_df["bea_sector_code"].astype(str)
                    )
                logger.info(
                    f"Loaded BEA crosswalk: {len(self.crosswalk_df)} mappings from {self.crosswalk_path}"
                )
            except Exception as e:
                logger.warning(f"Failed to load BEA crosswalk from {self.crosswalk_path}: {e}")
                self.crosswalk_df = pd.DataFrame()
        else:
            logger.warning(
                f"BEA crosswalk not found at {self.crosswalk_path}, using fallbacks only"
            )
            self.crosswalk_df = pd.DataFrame()

        # Load fallback configuration
        if self.fallback_config_path.exists():
            try:
                with self.fallback_config_path.open() as f:
                    self.fallback_config = yaml.safe_load(f) or {}
                logger.info(f"Loaded fallback mappings from {self.fallback_config_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to load fallback config from {self.fallback_config_path}: {e}"
                )
                self.fallback_config = {}

    def _load_configuration(self) -> None:
        """Load mapper configuration from config."""
        naics_config = getattr(self.config, "naics_to_bea", {})
        self.hierarchical_fallback = naics_config.get("hierarchical_fallback", True)
        self.min_confidence_threshold = naics_config.get("min_confidence_threshold", 0.50)
        self.crosswalk_version = naics_config.get("crosswalk_version", "2017")

    def _normalize_naics(self, naics_code: str) -> str:
        """Normalize NAICS code to 6-digit string with leading zeros.

        Args:
            naics_code: NAICS code of any length

        Returns:
            Normalized 6-digit NAICS code string
        """
        # Remove non-digit characters
        digits_only = "".join(c for c in str(naics_code) if c.isdigit())
        # Pad to 6 digits with leading zeros
        return digits_only.zfill(6)

    def _map_direct(self, naics_code: str) -> list[NAICSToBEAResult] | None:
        """Map NAICS code directly from crosswalk.

        Args:
            naics_code: Normalized NAICS code

        Returns:
            List of mapping results or None if not found
        """
        if self.crosswalk_df is None or self.crosswalk_df.empty:
            return None

        # Try exact match
        matches = self.crosswalk_df[self.crosswalk_df["naics_code"] == naics_code]
        if not matches.empty:
            results = []
            for _, row in matches.iterrows():
                results.append(
                    NAICSToBEAResult(
                        naics_code=naics_code,
                        bea_sector_code=row["bea_sector_code"],
                        bea_sector_name=row.get("bea_sector_name", ""),
                        allocation_weight=float(row.get("allocation_weight", 1.0)),
                        confidence=float(row.get("confidence", 0.90)),
                        source="direct",
                        crosswalk_version=self.crosswalk_version,
                        mapped_at=datetime.now(),
                        metadata={},
                    )
                )
            return results

        return None

    def _map_hierarchical(self, naics_code: str) -> list[NAICSToBEAResult] | None:
        """Map NAICS code using hierarchical fallback (6→4→3→2 digit).

        Args:
            naics_code: Normalized 6-digit NAICS code

        Returns:
            List of mapping results or None if not found
        """
        if not self.hierarchical_fallback or self.crosswalk_df is None or self.crosswalk_df.empty:
            return None

        # Try progressively shorter codes: 4-digit, 3-digit, 2-digit
        for level in [4, 3, 2]:
            prefix = naics_code[:level]
            prefix = prefix.ljust(6, "0")  # Pad to 6 digits on the right

            matches = self.crosswalk_df[self.crosswalk_df["naics_code"] == prefix]
            if not matches.empty:
                results = []
                confidence_discount = 0.10 * (6 - level)  # Reduce confidence for shorter matches
                for _, row in matches.iterrows():
                    results.append(
                        NAICSToBEAResult(
                            naics_code=naics_code,
                            bea_sector_code=row["bea_sector_code"],
                            bea_sector_name=row.get("bea_sector_name", ""),
                            allocation_weight=float(row.get("allocation_weight", 1.0)),
                            confidence=max(
                                0.50, float(row.get("confidence", 0.90)) - confidence_discount
                            ),
                            source=f"hierarchical_{level}digit",
                            crosswalk_version=self.crosswalk_version,
                            mapped_at=datetime.now(),
                            metadata={"hierarchical_level": level},
                        )
                    )
                return results

        return None

    def _map_fallback_config(self, naics_code: str) -> list[NAICSToBEAResult] | None:
        """Map NAICS code using fallback configuration.

        Args:
            naics_code: Normalized NAICS code

        Returns:
            List of mapping results or None if not found
        """
        mappings = self.fallback_config.get("mappings", {})
        if not mappings:
            return None

        # Try exact match
        mapping = mappings.get(naics_code) or mappings.get(naics_code.lstrip("0"))
        if mapping:
            results = []
            primary_sector = mapping.get("primary_sector", "")
            allocation_weight = float(mapping.get("allocation_weight", 1.0))
            confidence = float(mapping.get("confidence", 0.70))

            results.append(
                NAICSToBEAResult(
                    naics_code=naics_code,
                    bea_sector_code=primary_sector,
                    bea_sector_name="",
                    allocation_weight=allocation_weight,
                    confidence=confidence,
                    source="fallback_config",
                    crosswalk_version=self.crosswalk_version,
                    mapped_at=datetime.now(),
                    metadata={},
                )
            )

            # Check for secondary sectors (weighted allocations)
            secondary = mapping.get("secondary_sectors", [])
            for sec in secondary:
                results.append(
                    NAICSToBEAResult(
                        naics_code=naics_code,
                        bea_sector_code=sec.get("sector", ""),
                        bea_sector_name="",
                        allocation_weight=float(sec.get("weight", 0.0)),
                        confidence=confidence,
                        source="fallback_config_weighted",
                        crosswalk_version=self.crosswalk_version,
                        mapped_at=datetime.now(),
                        metadata={"weighted_allocation": True},
                    )
                )

            return results if results else None

        return None

    def _map_default(self, naics_code: str) -> list[NAICSToBEAResult]:
        """Map NAICS code using default sector.

        Args:
            naics_code: Normalized NAICS code

        Returns:
            List with one default mapping result
        """
        fallback_rules = self.fallback_config.get("fallback_rules", {})
        default_sector = fallback_rules.get("default_sector", "540000/US")
        default_confidence = float(fallback_rules.get("default_confidence", 0.30))

        return [
            NAICSToBEAResult(
                naics_code=naics_code,
                bea_sector_code=default_sector,
                bea_sector_name="R&D and related services",
                allocation_weight=1.0,
                confidence=default_confidence,
                source="default_fallback",
                crosswalk_version=self.crosswalk_version,
                mapped_at=datetime.now(),
                metadata={"fallback_reason": "no_mapping_found"},
            )
        ]

    def map_naics_to_bea(self, naics_code: str | None) -> list[NAICSToBEAResult]:
        """Map NAICS code to BEA sector(s) using hierarchical fallback.

        Args:
            naics_code: NAICS code (2-6 digits)

        Returns:
            List of mapping results (may have multiple for weighted allocations)
        """
        # Handle None/empty NAICS
        if not naics_code:
            return self._map_default("UNKNOWN")

        # Normalize NAICS code
        normalized = self._normalize_naics(naics_code)

        # Check cache first
        if normalized in self._mapping_cache:
            return self._mapping_cache[normalized]

        # Try mapping strategies in order
        # 1. Direct match
        results = self._map_direct(normalized)
        if results:
            self._mapping_cache[normalized] = results
            return results

        # 2. Hierarchical fallback
        if self.hierarchical_fallback:
            results = self._map_hierarchical(normalized)
            if results:
                self._mapping_cache[normalized] = results
                return results

        # 3. Fallback configuration
        results = self._map_fallback_config(normalized)
        if results:
            self._mapping_cache[normalized] = results
            return results

        # 4. Default sector
        results = self._map_default(normalized)
        self._mapping_cache[normalized] = results
        return results

    def enrich_awards_with_bea_sectors(
        self, awards_df: pd.DataFrame, naics_column: str = "fiscal_naics_code"
    ) -> pd.DataFrame:
        """Enrich awards DataFrame with BEA sector mappings.

        Args:
            awards_df: DataFrame with SBIR awards including NAICS codes
            naics_column: Column name containing NAICS codes

        Returns:
            Enriched DataFrame with BEA sector columns
        """
        enriched_rows = []

        for _idx, row in awards_df.iterrows():
            naics_code = row.get(naics_column)

            # Map to BEA sectors
            mapping_results = self.map_naics_to_bea(naics_code)

            # For weighted allocations, create multiple rows
            for mapping in mapping_results:
                enriched_row = row.copy()
                enriched_row["bea_sector_code"] = mapping.bea_sector_code
                enriched_row["bea_sector_name"] = mapping.bea_sector_name
                enriched_row["bea_allocation_weight"] = mapping.allocation_weight
                enriched_row["bea_mapping_confidence"] = mapping.confidence
                enriched_row["bea_mapping_source"] = mapping.source
                enriched_rows.append(enriched_row)

        enriched_df = pd.DataFrame(enriched_rows)
        return enriched_df

    def get_mapping_statistics(
        self, awards_df: pd.DataFrame, naics_column: str = "fiscal_naics_code"
    ) -> BEAMappingStatistics:
        """Calculate mapping statistics for a set of awards.

        Args:
            awards_df: DataFrame with awards to analyze
            naics_column: Column name containing NAICS codes

        Returns:
            BEAMappingStatistics with quality metrics
        """
        total = len(awards_df)
        successful = 0
        avg_confidence = 0.0
        min_confidence = 1.0
        max_confidence = 0.0
        source_counts: dict[str, int] = {}
        hierarchical_count = 0
        weighted_count = 0

        for _, row in awards_df.iterrows():
            naics_code = row.get(naics_column)
            if naics_code:
                mappings = self.map_naics_to_bea(naics_code)
                if mappings:
                    successful += 1
                    for mapping in mappings:
                        avg_confidence += mapping.confidence
                        min_confidence = min(min_confidence, mapping.confidence)
                        max_confidence = max(max_confidence, mapping.confidence)
                        source_counts[mapping.source] = source_counts.get(mapping.source, 0) + 1

                        if "hierarchical" in mapping.source:
                            hierarchical_count += 1
                        if mapping.allocation_weight < 1.0 or "weighted" in mapping.source:
                            weighted_count += 1

        avg_confidence = avg_confidence / successful if successful > 0 else 0.0
        coverage_rate = successful / total if total > 0 else 0.0

        return BEAMappingStatistics(
            total_mappings=total,
            successful_mappings=successful,
            failed_mappings=total - successful,
            coverage_rate=coverage_rate,
            avg_confidence=avg_confidence,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            source_distribution=source_counts,
            hierarchical_fallback_count=hierarchical_count,
            weighted_allocation_count=weighted_count,
        )


    def map_code(self, naics_code: str, vintage: str | None = None) -> str | None:
        """Return the BEA sector code for the highest-confidence mapping.

        Backward-compatible shim for callers that previously used the deleted
        sbir_etl.transformers.naics_to_bea.NAICSToBEAMapper.map_code().

        Args:
            naics_code: The NAICS code to map.
            vintage: Accepted for API parity with the deleted mapper; currently
                ignored (only one vintage is supported by the canonical crosswalk).

        Returns:
            The bea_sector_code of the highest-confidence NAICSToBEAResult, or
            None if no mapping is found (i.e. only a default_fallback result exists).
        """
        if not naics_code:
            return None
        results = self.map_naics_to_bea(naics_code)
        if not results:
            return None
        top = results[0]
        # Don't return the generic default fallback sector as a positive match —
        # the deleted mapper returned None when the code couldn't be mapped.
        if top.source == "default_fallback":
            return None
        return top.bea_sector_code

    def get_bea_code_description(self, bea_code: str) -> str:
        """Return a human-readable description of a BEA sector code.

        Backward-compatible shim for callers that previously used the deleted
        sbir_etl.transformers.naics_bea_mapper.NAICSBEAMapper.get_bea_code_description().

        Args:
            bea_code: BEA sector code (e.g. "54", "31-33").

        Returns:
            Description string, or "Unknown sector: <bea_code>" if not found.
        """
        descriptions: dict[str, str] = {
            "11": "Agriculture, forestry, fishing, and hunting",
            "21": "Mining, quarrying, and oil and gas extraction",
            "22": "Utilities",
            "23": "Construction",
            "31-33": "Manufacturing",
            "42": "Wholesale trade",
            "44-45": "Retail trade",
            "48-49": "Transportation and warehousing",
            "51": "Information",
            "52": "Finance and insurance",
            "53": "Real estate and rental and leasing",
            "54": "Professional, scientific, and technical services",
            "55": "Management of companies and enterprises",
            "56": "Administrative and support services",
            "61": "Educational services",
            "62": "Health care and social assistance",
            "71": "Arts, entertainment, and recreation",
            "72": "Accommodation and food services",
            "81": "Other services (except public administration)",
            "92": "Public administration",
        }
        return descriptions.get(bea_code, f"Unknown sector: {bea_code}")

    def map_naics_to_bea_summary(self, naics_code: str) -> str:
        """Return the BEA Summary-level sector code for a NAICS code.

        Backward-compatible shim for callers that previously used the deleted
        sbir_etl.transformers.naics_bea_mapper.NAICSBEAMapper.map_naics_to_bea_summary().

        The deleted mapper never raised on a missing prefix — it returned the raw
        2-digit prefix as a fallback.  This method preserves that contract exactly.

        Args:
            naics_code: NAICS industry code (2-6 digits).

        Returns:
            BEA Summary-level sector code (e.g. "54", "31-33").

        Raises:
            ValueError: If naics_code is empty or too short (< 2 chars after stripping).
        """
        if not naics_code:
            raise ValueError("NAICS code cannot be empty")
        code = str(naics_code).strip()
        if len(code) < 2:
            raise ValueError(f"NAICS code too short: {naics_code}")

        # Try the canonical mapper first (direct or hierarchical match).
        results = self.map_naics_to_bea(code)
        if results and results[0].source != "default_fallback":
            # bea_sector_code from the crosswalk is already at the Summary level
            # (e.g. "54", "31-33").  Use it when it looks like a BEA Summary code
            # (≤5 chars, may contain "-"), otherwise fall through to the 2-digit dict.
            sector = results[0].bea_sector_code
            prefix = code[:2]
            summary = self._SUMMARY_FALLBACK.get(prefix)
            if summary is not None:
                return summary
            # Crosswalk returned something outside our 24-entry dict — return it as-is.
            return sector

        # Fallback: use the 24-entry 2-digit prefix dict (matches deleted mapper behavior).
        prefix = code[:2]
        summary = self._SUMMARY_FALLBACK.get(prefix)
        if summary is not None:
            return summary
        # Unknown prefix — mirror the deleted mapper: return the 2-digit prefix.
        logger.warning(
            f"No BEA mapping found for NAICS {naics_code} (prefix {prefix}). "
            "Using NAICS 2-digit as fallback."
        )
        return prefix


def enrich_awards_with_bea_sectors(
    awards_df: pd.DataFrame, mapper: NAICSToBEAMapper | None = None
) -> tuple[pd.DataFrame, BEAMappingStatistics]:
    """Helper function to enrich awards with BEA sectors.

    Args:
        awards_df: DataFrame with awards to enrich
        mapper: Optional pre-configured mapper, creates new one if not provided

    Returns:
        Tuple of (enriched DataFrame, mapping statistics)
    """
    if mapper is None:
        mapper = NAICSToBEAMapper()

    enriched_df = mapper.enrich_awards_with_bea_sectors(awards_df)
    stats = mapper.get_mapping_statistics(awards_df)

    return enriched_df, stats
