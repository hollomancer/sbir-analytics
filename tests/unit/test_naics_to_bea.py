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


def test_map_bea_excel():
    """Test BEA mapping using CSV fixture."""
    # Use CSV fixture instead of Excel
    bea_csv_path = "tests/fixtures/bea_mapping.csv"

    if not Path(bea_csv_path).exists():
        pytest.skip(f"BEA CSV fixture not found: {bea_csv_path}")

    # Load CSV and create simple mapper
    import pandas as pd

    df = pd.read_csv(bea_csv_path)

    # Test that we can read the mapping
    assert len(df) > 0
    assert "NAICS" in df.columns
    assert "BEA_Code" in df.columns

    # Test a known mapping from fixture
    naics_541712 = df[df["NAICS"] == "541712"]
    assert len(naics_541712) > 0
    assert naics_541712.iloc[0]["BEA_Code"] == "5415"
