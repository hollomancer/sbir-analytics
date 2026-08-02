"""Text normalization utilities for consistent name matching across enrichers.

This module provides shared text normalization functions to eliminate duplicate
normalization logic across company_fuzzy_matcher, usaspending_enricher, and other modules.

Key Features:
- Unified name normalization with configurable suffix handling
- Consistent punctuation and whitespace handling
- Support for both "normalize" and "remove" suffix strategies
- Optional enhanced abbreviations support
"""

from __future__ import annotations

from sbir_etl.identity import CompanyNameProfile
from sbir_etl.identity import normalize_company_name as _normalize_company_name


def normalize_name(
    name: str | None,
    *,
    remove_suffixes: bool = False,
    apply_abbreviations: bool = False,
    abbreviations: dict[str, str] | None = None,
) -> str:
    """Normalize a company or recipient name for fuzzy matching.

    This function provides unified normalization logic used across multiple enrichers:
    - company_fuzzy_matcher: Uses normalize_suffixes=True (keeps standardized suffixes)
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
    selected_abbreviations = abbreviations
    if apply_abbreviations:
        if selected_abbreviations is None:
            from sbir_etl.identity import ENHANCED_ABBREVIATIONS

            selected_abbreviations = ENHANCED_ABBREVIATIONS
    else:
        selected_abbreviations = None
    profile = CompanyNameProfile.RECIPIENT_V1 if remove_suffixes else CompanyNameProfile.MATCHING_V1
    return _normalize_company_name(
        name,
        profile=profile,
        abbreviations=selected_abbreviations,
    )


# Backward-compatible aliases for existing code
def normalize_company_name(name: str | None) -> str:
    """Normalize a company name (keeps standardized suffixes).

    This is a backward-compatible wrapper for normalize_name() with
    remove_suffixes=False. Used by company_fuzzy_matcher.

    Args:
        name: Company name to normalize

    Returns:
        Normalized company name
    """
    return normalize_name(name, remove_suffixes=False)


def pluralize_col_key(col: str) -> str:
    """Convert a column name to a pluralized dict key.

    Lowercases, replaces spaces with underscores, and applies basic English
    pluralization (``y`` → ``ies``, otherwise append ``s``).

    Examples:
        >>> pluralize_col_key("Company")
        'companies'
        >>> pluralize_col_key("Phase")
        'phases'
        >>> pluralize_col_key("Agency")
        'agencies'
    """
    key = col.lower().replace(" ", "_")
    if key.endswith("y"):
        return key[:-1] + "ies"
    return key + "s"


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
