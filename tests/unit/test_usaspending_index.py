import os

import pytest

from src.enrichers.usaspending_index import extract_table_sample, parse_toc_table_dat_map


USASPENDING_ZIP = os.path.join("data", "raw", "usaspending", "usaspending-db-subset_20251006.zip")


def test_parse_toc_mapping_exists():
    # Skip if the large zip isn't present in runner environment
    if not os.path.exists(USASPENDING_ZIP):
        pytest.skip("usaspending zip not present")

    mapping = parse_toc_table_dat_map(USASPENDING_ZIP)
    # Expect at least the naics table to be present in mapping
    assert any(k.endswith(".naics") or k == "public.naics" for k in mapping.keys())


def test_extract_naics_sample():
    if not os.path.exists(USASPENDING_ZIP):
        pytest.skip("usaspending zip not present")

    mapping = parse_toc_table_dat_map(USASPENDING_ZIP)
    dat = mapping.get("public.naics") or mapping.get("naics")
    assert dat is not None
    sample = extract_table_sample(USASPENDING_ZIP, dat, n_lines=5)
    # sample should be non-empty text lines
    assert isinstance(sample, list)
    assert len(sample) > 0
