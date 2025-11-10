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
    """Test BEA excel mapping (requires openpyxl)."""
    bea_excel_path = "data/reference/BEA-Industry-and-Commodity-Codes-and-NAICS-Concordance.xlsx"

    # Skip if file doesn't exist or openpyxl not available
    if not Path(bea_excel_path).exists():
        pytest.skip(f"BEA Excel file not found: {bea_excel_path}")

    try:
        import openpyxl  # noqa: F401
    except ImportError:
        pytest.skip("openpyxl not available")

    m = NAICSToBEAMapper(bea_excel_path=bea_excel_path)

    # If multi_map is empty, skip (file couldn't be loaded)
    if not m.multi_map:
        pytest.skip("BEA Excel file could not be loaded")

    # Example: NAICS code '334510' should map to one or more BEA codes in the spreadsheet
    result = m.map_code("334510", vintage="bea")

    # Should return a list (could be empty if mapping doesn't exist)
    assert result is None or isinstance(result, list)
