"""Tests for company canonicalizer."""

import pandas as pd
import pytest

from src.utils.company_canonicalizer import canonicalize_companies_from_awards


def test_canonicalize_companies_simple():
    """Test basic canonicalization."""
    awards_df = pd.DataFrame(
        [
            {
                "company": "Acme Inc",
                "company_uei": "ABC123",
                "company_duns": None,
            },
            {
                "company": "Acme Incorporated",
                "company_uei": "ABC123",
                "company_duns": None,
            },
        ]
    )

    canonical_map = canonicalize_companies_from_awards(awards_df, high_threshold=90)

    # Both should map to same canonical ID (UEI-based)
    assert len(set(canonical_map.values())) == 1
    assert "UEI:ABC123" in canonical_map.values()


def test_canonicalize_companies_duns():
    """Test canonicalization with DUNS."""
    awards_df = pd.DataFrame(
        [
            {
                "company": "Tech Corp",
                "company_uei": None,
                "company_duns": "123456789",
            },
            {
                "company": "Tech Corporation",
                "company_uei": None,
                "company_duns": "123456789",
            },
        ]
    )

    canonical_map = canonicalize_companies_from_awards(awards_df, high_threshold=90)

    # Both should map to same canonical ID (DUNS-based)
    assert len(set(canonical_map.values())) == 1
    assert "DUNS:123456789" in canonical_map.values()


def test_canonicalize_companies_name_only():
    """Test canonicalization with name-only companies."""
    awards_df = pd.DataFrame(
        [
            {
                "company": "Startup Co",
                "company_uei": None,
                "company_duns": None,
            },
        ]
    )

    canonical_map = canonicalize_companies_from_awards(awards_df, high_threshold=90)

    # Should create NAME-based canonical ID
    assert len(canonical_map) == 1
    assert any("NAME:" in v for v in canonical_map.values())


def test_canonicalize_companies_empty():
    """Test canonicalization with empty DataFrame."""
    awards_df = pd.DataFrame([])

    canonical_map = canonicalize_companies_from_awards(awards_df)

    assert canonical_map == {}


def test_canonicalize_companies_no_identifiers():
    """Test canonicalization when no identifiers present."""
    awards_df = pd.DataFrame(
        [
            {
                "company": "Company A",
                "company_uei": None,
                "company_duns": None,
            },
            {
                "company": "Company B",
                "company_uei": None,
                "company_duns": None,
            },
        ]
    )

    canonical_map = canonicalize_companies_from_awards(awards_df, high_threshold=90)

    # Should create separate canonical IDs for different names
    assert len(canonical_map) == 2

