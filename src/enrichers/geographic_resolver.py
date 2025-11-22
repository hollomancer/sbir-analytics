"""
Geographic resolution service for fiscal returns analysis.

This module standardizes company locations to state-level for StateIO model compatibility,
integrating with existing company enrichment and address parsing capabilities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger

from ..config.loader import get_config


@dataclass
class GeographicResolutionResult:
    """Result of geographic resolution with confidence and source tracking."""

    state_code: str | None
    state_name: str | None
    confidence: float
    source: str
    method: str
    timestamp: datetime
    metadata: dict[str, Any]


class GeographicResolver:
    """Geographic resolution service for standardizing company locations to state level."""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize the geographic resolver.

        Args:
            config: Optional configuration override (dict or FiscalAnalysisConfig)
        """
        from src.config.schemas.fiscal import FiscalAnalysisConfig

        config_obj = config or get_config().fiscal_analysis
        # Handle both dict and FiscalAnalysisConfig objects
        if isinstance(config_obj, dict):
            self.config: FiscalAnalysisConfig = FiscalAnalysisConfig(**config_obj)
        else:
            self.config: FiscalAnalysisConfig = config_obj
        self.quality_thresholds = self.config.quality_thresholds

        # US state mappings (code -> name and name -> code)
        self.state_mappings = {
            "AL": "Alabama",
            "AK": "Alaska",
            "AZ": "Arizona",
            "AR": "Arkansas",
            "CA": "California",
            "CO": "Colorado",
            "CT": "Connecticut",
            "DE": "Delaware",
            "FL": "Florida",
            "GA": "Georgia",
            "HI": "Hawaii",
            "ID": "Idaho",
            "IL": "Illinois",
            "IN": "Indiana",
            "IA": "Iowa",
            "KS": "Kansas",
            "KY": "Kentucky",
            "LA": "Louisiana",
            "ME": "Maine",
            "MD": "Maryland",
            "MA": "Massachusetts",
            "MI": "Michigan",
            "MN": "Minnesota",
            "MS": "Mississippi",
            "MO": "Missouri",
            "MT": "Montana",
            "NE": "Nebraska",
            "NV": "Nevada",
            "NH": "New Hampshire",
            "NJ": "New Jersey",
            "NM": "New Mexico",
            "NY": "New York",
            "NC": "North Carolina",
            "ND": "North Dakota",
            "OH": "Ohio",
            "OK": "Oklahoma",
            "OR": "Oregon",
            "PA": "Pennsylvania",
            "RI": "Rhode Island",
            "SC": "South Carolina",
            "SD": "South Dakota",
            "TN": "Tennessee",
            "TX": "Texas",
            "UT": "Utah",
            "VT": "Vermont",
            "VA": "Virginia",
            "WA": "Washington",
            "WV": "West Virginia",
            "WI": "Wisconsin",
            "WY": "Wyoming",
            "DC": "District of Columbia",
            "PR": "Puerto Rico",
            "VI": "Virgin Islands",
            "GU": "Guam",
            "AS": "American Samoa",
            "MP": "Northern Mariana Islands",
        }

        # Reverse mapping (name -> code)
        self.name_to_code = {name.upper(): code for code, name in self.state_mappings.items()}

        # Common state abbreviations and variations
        self.state_variations = {
            "CALIF": "CA",
            "CALIFORNIA": "CA",
            "FLA": "FL",
            "FLORIDA": "FL",
            "MASS": "MA",
            "MASSACHUSETTS": "MA",
            "MICH": "MI",
            "MICHIGAN": "MI",
            "PENN": "PA",
            "PENNSYLVANIA": "PA",
            "TEXAS": "TX",
            "TEX": "TX",
            "WASH": "WA",
            "WASHINGTON": "WA",
            "N.Y.": "NY",
            "NEW YORK": "NY",
            "N.J.": "NJ",
            "NEW JERSEY": "NJ",
            "N.C.": "NC",
            "NORTH CAROLINA": "NC",
            "S.C.": "SC",
            "SOUTH CAROLINA": "SC",
            "N.D.": "ND",
            "NORTH DAKOTA": "ND",
            "S.D.": "SD",
            "SOUTH DAKOTA": "SD",
            "W.V.": "WV",
            "WEST VIRGINIA": "WV",
            "N.H.": "NH",
            "NEW HAMPSHIRE": "NH",
            "N.M.": "NM",
            "NEW MEXICO": "NM",
            "R.I.": "RI",
            "RHODE ISLAND": "RI",
        }

        # Combine all mappings
        self.all_state_mappings = {**self.name_to_code, **self.state_variations}

        # Valid state codes set for quick lookup
        self.valid_state_codes = set(self.state_mappings.keys())

        logger.info(
            f"Initialized GeographicResolver with {len(self.state_mappings)} states and {len(self.state_variations)} variations"
        )

    def normalize_state_input(self, state_input: str) -> str:
        """Normalize state input for matching.

        Args:
            state_input: Raw state input

        Returns:
            Normalized state string
        """
        if not state_input:
            return ""

        # Convert to uppercase and strip whitespace
        normalized = str(state_input).upper().strip()

        # Remove common punctuation
        normalized = re.sub(r"[.,;]", "", normalized)

        # Handle common patterns
        normalized = re.sub(r"\s+", " ", normalized)  # Collapse whitespace

        return normalized

    def extract_state_from_address(self, address: str) -> str | None:
        """Extract state code from full address string.

        Args:
            address: Full address string

        Returns:
            State code or None if not found
        """
        if not address:
            return None

        normalized_address = self.normalize_state_input(address)

        # Try to find state code at end of address (common pattern)
        # Look for 2-letter codes followed by ZIP
        state_zip_pattern = r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\s*$"
        match = re.search(state_zip_pattern, normalized_address)
        if match:
            potential_state = match.group(1)
            if potential_state in self.valid_state_codes:
                return potential_state

        # Look for state names or codes anywhere in address
        words = normalized_address.split()
        for i, word in enumerate(words):
            # Check for exact state code match
            if word in self.valid_state_codes:
                return word

            # Check for state name or variation match
            if word in self.all_state_mappings:
                return self.all_state_mappings[word]

            # Check for multi-word state names
            if i < len(words) - 1:
                two_word = f"{word} {words[i + 1]}"
                if two_word in self.all_state_mappings:
                    return self.all_state_mappings[two_word]

        return None

    def resolve_from_state_field(self, award_row: pd.Series) -> GeographicResolutionResult | None:
        """Resolve state from dedicated state field.

        Args:
            award_row: Award row data

        Returns:
            Geographic resolution result or None
        """
        # Check common state column names
        state_columns = ["State", "state", "Company_State", "company_state", "ST", "st"]

        for col in state_columns:
            if col in award_row.index and pd.notna(award_row[col]):
                state_input = self.normalize_state_input(str(award_row[col]))

                # Direct state code match
                if state_input in self.valid_state_codes:
                    return GeographicResolutionResult(
                        state_code=state_input,
                        state_name=self.state_mappings[state_input],
                        confidence=0.95,
                        source="state_field",
                        method="direct_code",
                        timestamp=datetime.now(),
                        metadata={"column": col, "original_value": str(award_row[col])},
                    )

                # State name or variation match
                if state_input in self.all_state_mappings:
                    state_code = self.all_state_mappings[state_input]
                    return GeographicResolutionResult(
                        state_code=state_code,
                        state_name=self.state_mappings[state_code],
                        confidence=0.90,
                        source="state_field",
                        method="name_mapping",
                        timestamp=datetime.now(),
                        metadata={
                            "column": col,
                            "original_value": str(award_row[col]),
                            "matched_variation": state_input,
                        },
                    )

        return None

    def resolve_from_address_field(self, award_row: pd.Series) -> GeographicResolutionResult | None:
        """Resolve state from address field.

        Args:
            award_row: Award row data

        Returns:
            Geographic resolution result or None
        """
        # Check common address column names
        address_columns = [
            "Address",
            "address",
            "Company_Address",
            "company_address",
            "Full_Address",
            "Location",
        ]

        for col in address_columns:
            if col in award_row.index and pd.notna(award_row[col]):
                address = str(award_row[col])
                state_code = self.extract_state_from_address(address)

                if state_code:
                    return GeographicResolutionResult(
                        state_code=state_code,
                        state_name=self.state_mappings[state_code],
                        confidence=0.85,
                        source="address_field",
                        method="address_parsing",
                        timestamp=datetime.now(),
                        metadata={"column": col, "original_address": address},
                    )

        return None

    def resolve_from_city_state(self, award_row: pd.Series) -> GeographicResolutionResult | None:
        """Resolve state from separate city and state fields.

        Args:
            award_row: Award row data

        Returns:
            Geographic resolution result or None
        """
        # Look for city/state combinations
        city_columns = ["City", "city", "Company_City", "company_city"]
        state_columns = ["State", "state", "Company_State", "company_state"]

        for city_col in city_columns:
            for state_col in state_columns:
                if (
                    city_col in award_row.index
                    and pd.notna(award_row[city_col])
                    and state_col in award_row.index
                    and pd.notna(award_row[state_col])
                ):
                    state_input = self.normalize_state_input(str(award_row[state_col]))

                    # Direct state code match
                    if state_input in self.valid_state_codes:
                        return GeographicResolutionResult(
                            state_code=state_input,
                            state_name=self.state_mappings[state_input],
                            confidence=0.92,
                            source="city_state_fields",
                            method="direct_code",
                            timestamp=datetime.now(),
                            metadata={
                                "city_column": city_col,
                                "state_column": state_col,
                                "city": str(award_row[city_col]),
                                "state": str(award_row[state_col]),
                            },
                        )

                    # State name match
                    if state_input in self.all_state_mappings:
                        state_code = self.all_state_mappings[state_input]
                        return GeographicResolutionResult(
                            state_code=state_code,
                            state_name=self.state_mappings[state_code],
                            confidence=0.88,
                            source="city_state_fields",
                            method="name_mapping",
                            timestamp=datetime.now(),
                            metadata={
                                "city_column": city_col,
                                "state_column": state_col,
                                "city": str(award_row[city_col]),
                                "state": str(award_row[state_col]),
                                "matched_variation": state_input,
                            },
                        )

        return None

    def resolve_from_zip_code(self, award_row: pd.Series) -> GeographicResolutionResult | None:
        """Resolve state from ZIP code (placeholder for future implementation).

        Args:
            award_row: Award row data

        Returns:
            Geographic resolution result or None
        """
        # Placeholder for ZIP code to state mapping
        # This would require a ZIP code database
        logger.debug("ZIP code to state resolution not yet implemented")
        return None

    def resolve_from_enriched_data(self, award_row: pd.Series) -> GeographicResolutionResult | None:
        """Resolve state from existing enriched company data.

        Args:
            award_row: Award row data

        Returns:
            Geographic resolution result or None
        """
        # Check for existing company enrichment data
        enriched_columns = ["company_state", "company_State", "recipient_state"]

        for col in enriched_columns:
            if col in award_row.index and pd.notna(award_row[col]):
                state_input = self.normalize_state_input(str(award_row[col]))

                if state_input in self.valid_state_codes:
                    return GeographicResolutionResult(
                        state_code=state_input,
                        state_name=self.state_mappings[state_input],
                        confidence=0.80,
                        source="enriched_data",
                        method="existing_enrichment",
                        timestamp=datetime.now(),
                        metadata={"column": col, "original_value": str(award_row[col])},
                    )

                if state_input in self.all_state_mappings:
                    state_code = self.all_state_mappings[state_input]
                    return GeographicResolutionResult(
                        state_code=state_code,
                        state_name=self.state_mappings[state_code],
                        confidence=0.75,
                        source="enriched_data",
                        method="existing_enrichment_mapped",
                        timestamp=datetime.now(),
                        metadata={
                            "column": col,
                            "original_value": str(award_row[col]),
                            "matched_variation": state_input,
                        },
                    )

        return None

    def resolve_single_award(self, award_row: pd.Series) -> GeographicResolutionResult | None:
        """Resolve geographic location for a single award using hierarchical approach.

        Args:
            award_row: Award row data

        Returns:
            Geographic resolution result or None
        """
        # Try each resolution method in order of preference
        resolution_methods = [
            self.resolve_from_state_field,
            self.resolve_from_city_state,
            self.resolve_from_address_field,
            self.resolve_from_enriched_data,
            self.resolve_from_zip_code,
        ]

        for method in resolution_methods:
            try:
                result = method(award_row)
                if result and result.state_code:
                    return result
            except Exception as e:
                logger.warning(f"Geographic resolution method failed: {e}")
                continue

        return None

    def resolve_awards_dataframe(self, awards_df: pd.DataFrame) -> pd.DataFrame:
        """Resolve geographic locations for entire awards DataFrame.

        Args:
            awards_df: SBIR awards DataFrame

        Returns:
            DataFrame with geographic resolution columns
        """
        enriched_df = awards_df.copy()

        # Initialize geographic resolution columns
        enriched_df["fiscal_state_code"] = None
        enriched_df["fiscal_state_name"] = None
        enriched_df["fiscal_geo_confidence"] = None
        enriched_df["fiscal_geo_source"] = None
        enriched_df["fiscal_geo_method"] = None
        enriched_df["fiscal_geo_timestamp"] = None
        enriched_df["fiscal_geo_metadata"] = None

        logger.info(f"Starting geographic resolution for {len(awards_df)} awards")

        # Track resolution statistics
        source_counts: dict[Any, Any] = {}
        confidence_distribution = []
        resolved_count = 0

        # Resolve each award
        for idx, row in awards_df.iterrows():
            try:
                result = self.resolve_single_award(row)

                if result:
                    # Store resolution results
                    enriched_df.at[idx, "fiscal_state_code"] = result.state_code  # type: ignore[index]
                    enriched_df.at[idx, "fiscal_state_name"] = result.state_name  # type: ignore[index]
                    enriched_df.at[idx, "fiscal_geo_confidence"] = result.confidence  # type: ignore[index]
                    enriched_df.at[idx, "fiscal_geo_source"] = result.source  # type: ignore[index]
                    enriched_df.at[idx, "fiscal_geo_method"] = result.method  # type: ignore[index]
                    enriched_df.at[idx, "fiscal_geo_timestamp"] = result.timestamp  # type: ignore[index]
                    enriched_df.at[idx, "fiscal_geo_metadata"] = str(result.metadata)  # type: ignore[index]

                    # Track statistics
                    source_counts[result.source] = source_counts.get(result.source, 0) + 1
                    confidence_distribution.append(result.confidence)
                    resolved_count += 1

            except Exception as e:
                logger.error(f"Failed to resolve geography for award {idx}: {e}")

        # Log resolution statistics
        total_awards = len(awards_df)
        resolution_rate = resolved_count / total_awards if total_awards > 0 else 0
        avg_confidence = (
            sum(confidence_distribution) / len(confidence_distribution)
            if confidence_distribution
            else 0
        )

        logger.info("Geographic resolution complete:")
        logger.info(f"  Resolution rate: {resolution_rate:.1%} ({resolved_count}/{total_awards})")
        logger.info(f"  Average confidence: {avg_confidence:.2f}")
        logger.info(f"  Source breakdown: {source_counts}")

        return enriched_df

    def validate_resolution_quality(self, enriched_df: pd.DataFrame) -> dict[str, Any]:
        """Validate geographic resolution quality against configured thresholds.

        Args:
            enriched_df: DataFrame with geographic resolution

        Returns:
            Quality validation results
        """
        total_awards = len(enriched_df)
        resolved_count = enriched_df["fiscal_state_code"].notna().sum()
        resolution_rate = resolved_count / total_awards if total_awards > 0 else 0

        # Calculate confidence distribution
        confidences = enriched_df["fiscal_geo_confidence"].dropna()
        high_confidence_count = (confidences >= 0.80).sum() if not confidences.empty else 0
        medium_confidence_count = (
            ((confidences >= 0.60) & (confidences < 0.80)).sum() if not confidences.empty else 0
        )
        low_confidence_count = (confidences < 0.60).sum() if not confidences.empty else 0

        # Source distribution
        source_counts = enriched_df["fiscal_geo_source"].value_counts().to_dict()

        # State distribution
        state_counts = enriched_df["fiscal_state_code"].value_counts().to_dict()

        # Quality assessment
        quality_results = {
            "total_awards": total_awards,
            "resolution_rate": resolution_rate,
            "resolution_threshold": self.quality_thresholds.get("geographic_resolution_rate", 0.90),
            "resolution_meets_threshold": resolution_rate
            >= self.quality_thresholds.get("geographic_resolution_rate", 0.90),
            "resolved_count": int(resolved_count),
            "unresolved_count": int(total_awards - resolved_count),
            "confidence_distribution": {
                "high_confidence": int(high_confidence_count),
                "medium_confidence": int(medium_confidence_count),
                "low_confidence": int(low_confidence_count),
            },
            "source_distribution": source_counts,
            "state_distribution": state_counts,
            "average_confidence": float(confidences.mean()) if not confidences.empty else 0.0,
            "unique_states_resolved": len(state_counts),
        }

        # Log quality assessment
        if quality_results["resolution_meets_threshold"]:
            logger.info(f"Geographic resolution quality: PASS (rate: {resolution_rate:.1%})")
        else:
            logger.warning(
                f"Geographic resolution quality: FAIL (rate: {resolution_rate:.1%}, threshold: {quality_results['resolution_threshold']:.1%})"
            )

        return quality_results


def resolve_award_geography(
    awards_df: pd.DataFrame, config: dict[str, Any] | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Main function to resolve geographic locations for SBIR awards.

    Args:
        awards_df: SBIR awards DataFrame
        config: Optional configuration override

    Returns:
        Tuple of (enriched DataFrame, quality metrics)
    """
    resolver = GeographicResolver(config)
    enriched_df = resolver.resolve_awards_dataframe(awards_df)
    quality_metrics = resolver.validate_resolution_quality(enriched_df)

    return enriched_df, quality_metrics
