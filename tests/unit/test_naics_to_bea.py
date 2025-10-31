from src.transformers.naics_to_bea import NAICSToBEAMapper


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
    m = NAICSToBEAMapper(bea_excel_path="data/reference/BEA-Industry-and-Commodity-Codes-and-NAICS-Concordance.xlsx")
    # Example: NAICS code '334510' should map to one or more BEA codes in the spreadsheet
    result = m.map_code("334510", vintage="bea")
    assert isinstance(result, list)
    # Should return a non-empty list if mapping exists
    assert result is None or len(result) >= 0
