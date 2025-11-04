import pytest


pytestmark = pytest.mark.fast

from src.transition.features.vendor_resolver import VendorRecord, VendorResolver


@pytest.fixture
def sample_vendors():
    """
    Provide a small, curated list of canonical VendorRecord instances for testing.
    """
    return [
        VendorRecord(uei="UEI-AAA", cage="CAGE1", duns="111111111", name="Acme Corporation"),
        VendorRecord(uei="UEI-BBB", cage="CAGE2", duns="222222222", name="Beta Solutions LLC"),
        VendorRecord(uei=None, cage=None, duns=None, name="Ophir Corporation"),
        VendorRecord(uei="UEI-CCC", cage=None, duns="333333333", name="Gamma, Inc."),
    ]


def test_exact_identifier_matching(sample_vendors):
    resolver = VendorResolver.from_records(sample_vendors)

    # UEI exact match
    m = resolver.resolve(uei="UEI-AAA")
    assert m.record is not None
    assert m.method == "uei"
    assert m.score == 1.0
    assert m.record.name == "Acme Corporation"

    # CAGE exact match
    m = resolver.resolve(cage="CAGE2")
    assert m.record is not None
    assert m.method == "cage"
    assert m.score == 1.0
    assert m.record.uei == "UEI-BBB"

    # DUNS exact match
    m = resolver.resolve(duns="333333333")
    assert m.record is not None
    assert m.method == "duns"
    assert m.score == 1.0
    assert m.record.name.startswith("Gamma")


def test_exact_name_matching(sample_vendors):
    resolver = VendorResolver.from_records(sample_vendors)

    # Exact (normalized) name match should succeed
    m = resolver.resolve(name="Acme Corporation")
    assert m.record is not None
    assert m.method == "name_exact"
    assert m.record.uei == "UEI-AAA"

    # Case-insensitive / punctuation-normalized match
    m2 = resolver.resolve(name="gamma inc")
    assert m2.record is not None
    assert m2.method == "name_exact" or m2.method.startswith("name_fuzzy")
    assert "Gamma" in m2.record.name


@pytest.mark.parametrize(
    "query,expected_name,expect_fuzzy",
    [
        ("Acme Corp", "Acme Corporation", True),
        ("Betta Solutions", "Beta Solutions LLC", True),
        ("Ophir Corp.", "Ophir Corporation", True),
        ("Nonexistent Co", None, False),
    ],
)
def test_fuzzy_name_matching(sample_vendors, query, expected_name, expect_fuzzy):
    resolver = VendorResolver.from_records(
        sample_vendors, fuzzy_threshold=0.85, fuzzy_secondary_threshold=0.75
    )

    m = resolver.resolve(name=query)
    if expected_name is None:
        assert m.record is None
        assert m.score == 0.0
    else:
        assert m.record is not None
        # Accept either exact or fuzzy depending on normalization/threshold
        assert expected_name.lower().split()[0] in m.record.name.lower()
        # If we expect fuzzy, ensure the method indicates a fuzzy match or exact
        assert m.method in ("name_exact", "name_fuzzy", "name_fuzzy_secondary")
        assert 0.0 <= m.score <= 1.0


def test_prefer_identifiers_over_name(sample_vendors):
    resolver = VendorResolver.from_records(sample_vendors, fuzzy_threshold=0.8)

    # Provide both UEI and a slightly different name. UEI should win.
    m = resolver.resolve(uei="UEI-BBB", name="Beta Solutions Incorporated")
    assert m.record is not None
    assert m.method == "uei"
    assert m.record.uei == "UEI-BBB"


def test_add_and_remove_records(sample_vendors):
    resolver = VendorResolver.from_records(sample_vendors)

    # Add a new record and resolve it
    new = VendorRecord(uei="UEI-ZZZ", cage="CAGEZ", duns="999999999", name="Zeta Labs")
    resolver.add_record(new)
    m = resolver.resolve(uei="UEI-ZZZ")
    assert m.record is not None and m.record.name == "Zeta Labs"

    # Remove it and ensure resolution fails afterwards
    removed = resolver.remove_record_by_uei("UEI-ZZZ")
    assert removed is True
    m2 = resolver.resolve(uei="UEI-ZZZ")
    assert m2.record is None


def test_cache_behavior(sample_vendors):
    resolver = VendorResolver.from_records(sample_vendors)
    # Ensure cache empty initially
    initial_stats = resolver.stats()
    assert "cache_entries" in initial_stats

    # Resolve twice and ensure no exception and cache used (cache_entries may increment)
    m1 = resolver.resolve(name="Acme Corp")
    m2 = resolver.resolve(name="Acme Corp")
    assert m1.method in ("name_exact", "name_fuzzy", "name_fuzzy_secondary") or m1.method == "uei"
    assert m2.method == m1.method
    # Clearing cache resets entries
    resolver.clear_cache()
    assert resolver.stats()["cache_entries"] == 0


def test_resolve_none_inputs(sample_vendors):
    resolver = VendorResolver.from_records(sample_vendors)

    # All empty inputs should return a None match
    m = resolver.resolve()
    assert m.record is None
    assert m.score == 0.0
    assert m.method == "none"
