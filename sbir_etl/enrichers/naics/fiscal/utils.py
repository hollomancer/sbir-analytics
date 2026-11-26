"""Shared utilities for NAICS enrichment."""

from __future__ import annotations

from sbir_etl.utils.identifiers import normalize_naics


def validate_naics_code(naics_code: str) -> bool:
    """Return True when ``naics_code`` is a valid 2- to 6-digit NAICS code.

    Uses the shared rules in ``sbir_etl.utils.identifiers.normalize_naics``.
    """
    return normalize_naics(naics_code) is not None


def normalize_naics_code(naics_code: str) -> str | None:
    """Return the normalized NAICS code, or None if it is invalid.

    Delegates to ``sbir_etl.utils.identifiers.normalize_naics``.
    """
    return normalize_naics(naics_code)
