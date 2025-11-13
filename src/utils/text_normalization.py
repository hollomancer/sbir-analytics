"""Text normalization utilities for consistent name matching across enrichers.

This module provides shared text normalization functions to eliminate duplicate
normalization logic across company_enricher, usaspending_enricher, and other modules.

Key Features:
- Unified name normalization with configurable suffix handling
- Consistent punctuation and whitespace handling
- Support for both "normalize" and "remove" suffix strategies
- Optional enhanced abbreviations support
"""

from __future__ import annotations

import re
from typing import Any


def normalize_name(
    name: str | None,
    *,
    remove_suffixes: bool = False,
    apply_abbreviations: bool = False,
    abbreviations: dict[str, str] | None = None,
) -> str:
    """Normalize a company or recipient name for fuzzy matching.

    This function provides unified normalization logic used across multiple enrichers:
    - company_enricher: Uses normalize_suffixes=True (keeps standardized suffixes)
    - usaspending_enricher: Uses remove_suffixes=True (strips all suffixes)

    Args:
        name: Company or recipient name to normalize
        remove_suffixes: If True, remove business suffixes entirely.
                        If False, normalize them to standard forms.
        apply_abbreviations: If True, apply abbreviation dictionary
        abbreviations: Custom abbreviation dict (if None, uses enhanced_matching.ENHANCED_ABBREVIATIONS)

    Returns:
        Normalized name string (lowercase, normalized punctuation/whitespace)

    Examples:
        >>> normalize_name("Acme, Inc.", remove_suffixes=False)
        'acme inc'
        >>> normalize_name("Acme, Inc.", remove_suffixes=True)
        'acme'
        >>> normalize_name("TechCorp Incorporated")
        'techcorp inc'
        >>> normalize_name("Advanced Technologies", apply_abbreviations=True)
        'adv tech'
    """
    if not name:
        return ""

    s = str(name).strip().lower()

    # Replace punctuation with spaces
    s = re.sub(r"[^\w\s]", " ", s)

    if remove_suffixes:
        # Remove all common business suffixes (usaspending_enricher behavior)
        s = re.sub(
            r"\b(incorporated|incorporation|inc|corp|corporation|llc|ltd|limited|co|company)\b",
            "",
            s,
        )
    else:
        # Normalize suffixes to standard forms (company_enricher behavior)
        s = re.sub(r"\b(incorporated|incorporation)\b", "inc", s)
        s = re.sub(r"\b(company|co)\b", "company", s)
        s = re.sub(r"\b(limited|ltd)\b", "ltd", s)

    # Apply abbreviations if requested
    if apply_abbreviations:
        if abbreviations is None:
            # Import here to avoid circular dependency
            try:
                from .enhanced_matching import ENHANCED_ABBREVIATIONS

                abbreviations = ENHANCED_ABBREVIATIONS
            except ImportError:  # pragma: no cover
                abbreviations = {}

        if abbreviations:
            tokens = s.split()
            normalized_tokens = [abbreviations.get(token, token) for token in tokens]
            s = " ".join(normalized_tokens)

    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    return s


# Backward-compatible aliases for existing code
def normalize_company_name(name: str | None) -> str:
    """Normalize a company name (keeps standardized suffixes).

    This is a backward-compatible wrapper for normalize_name() with
    remove_suffixes=False. Used by company_enricher.

    Args:
        name: Company name to normalize

    Returns:
        Normalized company name
    """
    return normalize_name(name, remove_suffixes=False)


def normalize_recipient_name(name: str | None) -> str:
    """Normalize a recipient name (removes all suffixes).

    This is a backward-compatible wrapper for normalize_name() with
    remove_suffixes=True. Used by usaspending_enricher.

    Args:
        name: Recipient name to normalize

    Returns:
        Normalized recipient name
    """
    return normalize_name(name, remove_suffixes=True)
