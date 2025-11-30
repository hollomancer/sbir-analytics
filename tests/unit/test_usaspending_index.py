"""Tests for usaspending index."""

from pathlib import Path

import pytest

from src.enrichers.usaspending.index import extract_table_sample, parse_toc_table_dat_map


pytestmark = pytest.mark.fast


def test_parse_toc_mapping_exists(usaspending_zip: Path):
    """Test parsing TOC table from USAspending zip."""
    mapping = parse_toc_table_dat_map(str(usaspending_zip))
    assert any(k.endswith(".naics") or k == "public.naics" for k in mapping.keys())


def test_extract_naics_sample(usaspending_zip: Path):
    """Test extracting NAICS sample from USAspending zip."""
    mapping = parse_toc_table_dat_map(str(usaspending_zip))
    dat = mapping.get("public.naics") or mapping.get("naics")
    assert dat is not None
    sample = extract_table_sample(str(usaspending_zip), dat, n_lines=5)
    assert isinstance(sample, list)
    assert len(sample) > 0
