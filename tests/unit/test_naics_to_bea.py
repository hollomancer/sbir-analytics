from pathlib import Path

import pytest

from src.transformers.naics_to_bea import NAICSToBEAMapper


pytestmark = pytest.mark.fast


def test_map_exact_6digit():
    m = NAICSToBEAMapper()
    assert m.map_code("334510") == "4300"


def test_map_sector_prefix():
    m = NAICSToBEAMapper()
    # 541330 is mapped explicitly, but 5413 prefix should resolve to 5400 via 541330
    assert m.map_code("541330") == "5400"
    # 11 maps to 10
    assert m.map_code("11") == "10"


def test_map_missing():
    m = NAICSToBEAMapper()
    assert m.map_code("") is None
    assert m.map_code("999999") is None


def test_map_bea_excel(bea_mapping: Path):
    """Test BEA mapping using CSV fixture."""
    import pandas as pd

    df = pd.read_csv(bea_mapping)

    # Test that we can read the mapping
    assert len(df) > 0
    # Fixture uses NAICS column name
    assert "NAICS" in df.columns or "naics_prefix" in df.columns
    assert "BEA_Code" in df.columns or "bea_sector" in df.columns

    # Test a known mapping from fixture - use actual column names
    naics_col = "NAICS" if "NAICS" in df.columns else "naics_prefix"
    bea_col = "BEA_Code" if "BEA_Code" in df.columns else "bea_sector"

    # NAICS may be read as int or string, handle both
    # Use a code that exists in the fixture (5413 -> 5400)
    naics_5413 = df[df[naics_col].astype(str) == "5413"]
    assert len(naics_5413) > 0
    assert str(naics_5413.iloc[0][bea_col]) == "5400"
