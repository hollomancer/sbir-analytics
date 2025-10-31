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
