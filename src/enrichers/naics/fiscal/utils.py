"""Shared utilities for NAICS enrichment."""

from __future__ import annotations

import re


def validate_naics_code(naics_code: str) -> bool:
    """Validate NAICS code format and structure.

    Args:
        naics_code: NAICS code to validate

    Returns:
        True if valid NAICS code format
    """
    if not naics_code:
        return False

    # Remove any non-digit characters
    clean_code = re.sub(r"\D", "", str(naics_code))

    # NAICS codes should be 2-6 digits
    if len(clean_code) < 2 or len(clean_code) > 6:
        return False

    # Check if it's a valid numeric string
    try:
        int(clean_code)
        return True
    except ValueError:
        return False


def normalize_naics_code(naics_code: str) -> str | None:
    """Normalize NAICS code to standard format.

    Args:
        naics_code: Raw NAICS code

    Returns:
        Normalized NAICS code or None if invalid
    """
    if not naics_code:
        return None

    # Remove non-digit characters and leading zeros
    clean_code = re.sub(r"\D", "", str(naics_code)).lstrip("0")

    if not clean_code:
        return None

    # Validate the cleaned code
    if validate_naics_code(clean_code):
        return clean_code

    return None
