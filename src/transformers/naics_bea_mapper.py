"""NAICS to BEA Sector Code Mapping.

This module provides mapping between NAICS industry codes and BEA Input-Output sector codes.
NAICS codes are 6-digit industry classification codes used by census/federal data.
BEA codes are used in input-output (I-O) economic models like USEEIOR and StateIO.
"""

from __future__ import annotations

from typing import Dict

from loguru import logger


class NAICSBEAMapper:
    """Maps NAICS codes to BEA Summary-level I-O sector codes.

    BEA Summary level has approximately 71 sectors, derived from more detailed
    sector schemes. This mapper provides a simplified mapping based on NAICS
    prefixes to BEA Summary codes.

    For production use, this should be replaced with BEA's official concordance tables.
    """

    # Simplified NAICS 2-digit to BEA Summary mapping
    # Based on BEA's I-O sector definitions
    # Source: https://www.bea.gov/industry/input-output-accounts-data
    NAICS_2DIGIT_TO_BEA_SUMMARY: Dict[str, str] = {
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

    def __init__(self, concordance_path: str | None = None):
        """Initialize NAICS-BEA mapper.

        Args:
            concordance_path: Optional path to BEA concordance file.
                            If None, uses simplified built-in mapping.
        """
        self.concordance_path = concordance_path
        if concordance_path:
            logger.warning(
                f"Custom concordance path provided: {concordance_path}, "
                "but custom concordance loading not yet implemented. "
                "Using built-in mapping."
            )

    def map_naics_to_bea_summary(self, naics_code: str) -> str:
        """Map NAICS code to BEA Summary-level sector code.

        Args:
            naics_code: NAICS industry code (2-6 digits)

        Returns:
            BEA Summary-level sector code (e.g., "54", "31-33")

        Raises:
            ValueError: If NAICS code cannot be mapped
        """
        # Clean input
        naics_clean = str(naics_code).strip()

        if not naics_clean:
            raise ValueError("NAICS code cannot be empty")

        # Extract first 2 digits for mapping
        if len(naics_clean) < 2:
            raise ValueError(f"NAICS code too short: {naics_code}")

        naics_2digit = naics_clean[:2]

        # Look up in mapping
        bea_code = self.NAICS_2DIGIT_TO_BEA_SUMMARY.get(naics_2digit)

        if bea_code is None:
            logger.warning(
                f"No BEA mapping found for NAICS {naics_code} (prefix {naics_2digit}). "
                f"Using NAICS 2-digit as fallback."
            )
            return naics_2digit

        return bea_code

    def map_naics_series(self, naics_series) -> list[str]:
        """Map a series/list of NAICS codes to BEA codes.

        Args:
            naics_series: Iterable of NAICS codes

        Returns:
            List of BEA sector codes
        """
        return [self.map_naics_to_bea_summary(naics) for naics in naics_series]

    def validate_bea_code(self, bea_code: str) -> bool:
        """Check if a BEA code is valid.

        Args:
            bea_code: BEA sector code to validate

        Returns:
            True if valid, False otherwise
        """
        valid_codes = set(self.NAICS_2DIGIT_TO_BEA_SUMMARY.values())
        return bea_code in valid_codes

    def get_bea_code_description(self, bea_code: str) -> str:
        """Get human-readable description of BEA sector code.

        Args:
            bea_code: BEA sector code

        Returns:
            Description string
        """
        descriptions = {
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
