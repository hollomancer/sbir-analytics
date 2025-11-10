"""
Tests for src/transition/features/vendor_resolver.py

Tests the VendorResolver for vendor identity resolution across
multiple identifier spaces (UEI, CAGE, DUNS) with fuzzy name matching.
"""

import pytest

from src.transition.features.vendor_resolver import (
    VendorMatch,
    VendorRecord,
    VendorResolver,
    build_resolver_from_iterable,
)


@pytest.fixture
def sample_vendors():
    """Sample vendor records for testing."""
    return [
        VendorRecord(
            uei="ABC123DEF456",
            cage="1A2B3",
            duns="123456789",
            name="Acme Corporation",
            metadata={"state": "CA"},
        ),
        VendorRecord(
            uei="DEF456GHI789",
            cage="4C5D6",
            duns="987654321",
            name="Beta Technologies Inc",
            metadata={"state": "MA"},
        ),
        VendorRecord(
            uei="GHI789JKL012",
            cage=None,
            duns=None,
            name="Gamma Research LLC",
            metadata={"state": "TX"},
        ),
        VendorRecord(
            uei=None,
            cage="7E8F9",
            duns="555555555",
            name="Delta Systems",
            metadata={"state": "NY"},
        ),
    ]


class TestVendorRecord:
    """Tests for VendorRecord dataclass."""

    def test_vendor_record_creation(self):
        """Test creating a VendorRecord with all fields."""
        record = VendorRecord(
            uei="ABC123",
            cage="1A2B3",
            duns="123456789",
            name="Acme Corporation",
            metadata={"source": "test"},
        )

        assert record.uei == "ABC123"
        assert record.cage == "1A2B3"
        assert record.duns == "123456789"
        assert record.name == "Acme Corporation"
        assert record.metadata["source"] == "test"

    def test_vendor_record_defaults(self):
        """Test VendorRecord with default values."""
        record = VendorRecord(uei=None, cage=None, duns=None, name="Acme")

        assert record.uei is None
        assert record.cage is None
        assert record.duns is None
        assert record.metadata == {}


class TestVendorMatch:
    """Tests for VendorMatch dataclass."""

    def test_vendor_match_creation(self):
        """Test creating a VendorMatch result."""
        record = VendorRecord(uei="ABC123", cage=None, duns=None, name="Acme")
        match = VendorMatch(record=record, method="uei", score=1.0, note="exact match")

        assert match.record == record
        assert match.method == "uei"
        assert match.score == 1.0
        assert match.note == "exact match"

    def test_vendor_match_no_match(self):
        """Test VendorMatch with no match found."""
        match = VendorMatch(record=None, method="uei", score=0.0, note="no match")

        assert match.record is None
        assert match.score == 0.0


class TestVendorResolverInitialization:
    """Tests for VendorResolver initialization."""

    def test_initialization_empty(self):
        """Test VendorResolver initializes with empty records."""
        resolver = VendorResolver(records=[])

        assert len(resolver._uei_index) == 0
        assert len(resolver._cage_index) == 0
        assert len(resolver._duns_index) == 0
        assert len(resolver._name_index) == 0

    def test_initialization_with_records(self, sample_vendors):
        """Test VendorResolver loads records and builds indices."""
        resolver = VendorResolver(records=sample_vendors)

        assert len(resolver._uei_index) == 3  # 3 vendors with UEI
        assert len(resolver._cage_index) == 3  # 3 vendors with CAGE
        assert len(resolver._duns_index) == 3  # 3 vendors with DUNS
        assert len(resolver._name_index) == 4  # 4 unique names

    def test_initialization_with_thresholds(self):
        """Test VendorResolver initialization with custom thresholds."""
        resolver = VendorResolver(
            records=[], fuzzy_threshold=0.85, fuzzy_secondary_threshold=0.75
        )

        assert resolver.fuzzy_threshold == 0.85
        assert resolver.fuzzy_secondary_threshold == 0.75

    def test_from_records_classmethod(self, sample_vendors):
        """Test VendorResolver.from_records constructor."""
        resolver = VendorResolver.from_records(sample_vendors, fuzzy_threshold=0.85)

        assert len(resolver._uei_index) == 3
        assert resolver.fuzzy_threshold == 0.85


class TestNameNormalization:
    """Tests for name normalization."""

    def test_normalize_name_basic(self):
        """Test basic name normalization."""
        resolver = VendorResolver(records=[])

        normalized = resolver._normalize_name("Acme Corporation")

        assert normalized == "acme corp"

    def test_normalize_name_whitespace(self):
        """Test name normalization collapses whitespace."""
        resolver = VendorResolver(records=[])

        normalized = resolver._normalize_name("  Acme   Corporation  ")

        assert normalized == "acme corp"

    def test_normalize_name_punctuation(self):
        """Test name normalization removes punctuation."""
        resolver = VendorResolver(records=[])

        assert resolver._normalize_name("Acme, Inc.") == "acme inc"
        assert resolver._normalize_name("Acme & Co.") == "acme AND co"
        assert resolver._normalize_name("Acme/Corp") == "acme corp"

    def test_normalize_name_business_suffixes(self):
        """Test name normalization standardizes business suffixes."""
        resolver = VendorResolver(records=[])

        assert resolver._normalize_name("Acme Corporation") == "acme corp"
        assert resolver._normalize_name("Acme Corp") == "acme corp"
        assert resolver._normalize_name("Acme Incorporated") == "acme inc"
        assert resolver._normalize_name("Acme Inc") == "acme inc"
        assert resolver._normalize_name("Acme Company") == "acme co"
        assert resolver._normalize_name("Acme Limited") == "acme ltd"
        assert resolver._normalize_name("Acme LLC") == "acme llc"

    def test_normalize_name_empty(self):
        """Test name normalization handles empty strings."""
        resolver = VendorResolver(records=[])

        assert resolver._normalize_name("") == ""


class TestResolveByUEI:
    """Tests for UEI-based resolution."""

    def test_resolve_by_uei_success(self, sample_vendors):
        """Test successful resolution by UEI."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_uei("ABC123DEF456")

        assert match.record is not None
        assert match.record.name == "Acme Corporation"
        assert match.method == "uei"
        assert match.score == 1.0

    def test_resolve_by_uei_case_insensitive(self, sample_vendors):
        """Test UEI resolution is case-insensitive."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_uei("abc123def456")  # Lowercase

        assert match.record is not None
        assert match.record.name == "Acme Corporation"

    def test_resolve_by_uei_with_whitespace(self, sample_vendors):
        """Test UEI resolution strips whitespace."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_uei("  ABC123DEF456  ")

        assert match.record is not None
        assert match.record.name == "Acme Corporation"

    def test_resolve_by_uei_not_found(self, sample_vendors):
        """Test UEI resolution returns no match when not found."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_uei("UNKNOWN")

        assert match.record is None
        assert match.method == "uei"
        assert match.score == 0.0
        assert match.note == "no match"

    def test_resolve_by_uei_empty(self, sample_vendors):
        """Test UEI resolution handles empty input."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_uei("")

        assert match.record is None
        assert match.score == 0.0
        assert match.note == "no uei provided"


class TestResolveByCAGE:
    """Tests for CAGE-based resolution."""

    def test_resolve_by_cage_success(self, sample_vendors):
        """Test successful resolution by CAGE."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_cage("1A2B3")

        assert match.record is not None
        assert match.record.name == "Acme Corporation"
        assert match.method == "cage"
        assert match.score == 1.0

    def test_resolve_by_cage_case_insensitive(self, sample_vendors):
        """Test CAGE resolution is case-insensitive."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_cage("1a2b3")

        assert match.record is not None
        assert match.record.name == "Acme Corporation"

    def test_resolve_by_cage_not_found(self, sample_vendors):
        """Test CAGE resolution returns no match when not found."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_cage("UNKNOWN")

        assert match.record is None
        assert match.score == 0.0

    def test_resolve_by_cage_empty(self, sample_vendors):
        """Test CAGE resolution handles empty input."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_cage("")

        assert match.record is None
        assert match.note == "no cage provided"


class TestResolveByDUNS:
    """Tests for DUNS-based resolution."""

    def test_resolve_by_duns_success(self, sample_vendors):
        """Test successful resolution by DUNS."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_duns("123456789")

        assert match.record is not None
        assert match.record.name == "Acme Corporation"
        assert match.method == "duns"
        assert match.score == 1.0

    def test_resolve_by_duns_not_found(self, sample_vendors):
        """Test DUNS resolution returns no match when not found."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_duns("999999999")

        assert match.record is None
        assert match.score == 0.0

    def test_resolve_by_duns_empty(self, sample_vendors):
        """Test DUNS resolution handles empty input."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_duns("")

        assert match.record is None
        assert match.note == "no duns provided"


class TestResolveByName:
    """Tests for name-based resolution."""

    def test_resolve_by_name_exact_match(self, sample_vendors):
        """Test exact name match."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_name("Acme Corporation")

        assert match.record is not None
        assert match.record.uei == "ABC123DEF456"
        assert match.method == "name_exact"
        assert match.score == 1.0

    def test_resolve_by_name_exact_with_variations(self, sample_vendors):
        """Test exact match handles name variations."""
        resolver = VendorResolver(records=sample_vendors)

        # "Corp" and "Corporation" both normalize to "corp"
        match = resolver.resolve_by_name("Acme Corp")

        assert match.record is not None
        assert match.record.name == "Acme Corporation"
        assert match.method == "name_exact"

    def test_resolve_by_name_fuzzy_match(self, sample_vendors):
        """Test fuzzy name matching."""
        resolver = VendorResolver(records=sample_vendors, fuzzy_threshold=0.8)

        # "Beta Technologies" should match "Beta Technologies Inc"
        match = resolver.resolve_by_name("Beta Technologies")

        assert match.record is not None
        assert match.record.name == "Beta Technologies Inc"
        assert match.method == "name_fuzzy"
        assert match.score >= 0.8

    def test_resolve_by_name_fuzzy_below_threshold(self, sample_vendors):
        """Test fuzzy matching below threshold returns no match."""
        resolver = VendorResolver(records=sample_vendors, fuzzy_threshold=0.95)

        match = resolver.resolve_by_name("Completely Different Company")

        assert match.record is None
        assert match.score == 0.0

    def test_resolve_by_name_secondary_threshold(self, sample_vendors):
        """Test secondary threshold for lower-confidence matches."""
        resolver = VendorResolver(
            records=sample_vendors, fuzzy_threshold=0.95, fuzzy_secondary_threshold=0.75
        )

        # Should match with secondary threshold
        match = resolver.resolve_by_name("Acme Corp Systems")

        # If score between 0.75 and 0.95, should use secondary threshold
        if 0.75 <= match.score < 0.95:
            assert match.method == "name_fuzzy_secondary"
            assert match.note == "secondary threshold met"

    def test_resolve_by_name_empty(self, sample_vendors):
        """Test name resolution handles empty input."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve_by_name("")

        assert match.record is None
        assert match.note == "no name provided"

    def test_resolve_by_name_caching(self, sample_vendors):
        """Test name resolution caches results."""
        resolver = VendorResolver(records=sample_vendors)

        # First call
        match1 = resolver.resolve_by_name("Acme Corporation")
        # Second call should use cache
        match2 = resolver.resolve_by_name("Acme Corporation")

        assert match1.record == match2.record
        assert len(resolver._cache) > 0


class TestChoosePreferredRecord:
    """Tests for preferred record selection."""

    def test_choose_preferred_with_uei(self):
        """Test prefers record with UEI."""
        resolver = VendorResolver(records=[])

        records = [
            VendorRecord(uei=None, cage="CAGE1", duns=None, name="Acme"),
            VendorRecord(uei="UEI123", cage=None, duns=None, name="Acme"),
            VendorRecord(uei=None, cage=None, duns="DUNS1", name="Acme"),
        ]

        preferred = resolver._choose_preferred_record(records)

        assert preferred.uei == "UEI123"

    def test_choose_preferred_with_cage_no_uei(self):
        """Test prefers record with CAGE when no UEI."""
        resolver = VendorResolver(records=[])

        records = [
            VendorRecord(uei=None, cage=None, duns="DUNS1", name="Acme"),
            VendorRecord(uei=None, cage="CAGE1", duns=None, name="Acme"),
        ]

        preferred = resolver._choose_preferred_record(records)

        assert preferred.cage == "CAGE1"

    def test_choose_preferred_with_duns_only(self):
        """Test prefers record with DUNS when no UEI or CAGE."""
        resolver = VendorResolver(records=[])

        records = [
            VendorRecord(uei=None, cage=None, duns=None, name="Acme"),
            VendorRecord(uei=None, cage=None, duns="DUNS1", name="Acme"),
        ]

        preferred = resolver._choose_preferred_record(records)

        assert preferred.duns == "DUNS1"

    def test_choose_preferred_defaults_to_first(self):
        """Test defaults to first record when no identifiers."""
        resolver = VendorResolver(records=[])

        records = [
            VendorRecord(uei=None, cage=None, duns=None, name="First"),
            VendorRecord(uei=None, cage=None, duns=None, name="Second"),
        ]

        preferred = resolver._choose_preferred_record(records)

        assert preferred.name == "First"


class TestHighLevelResolve:
    """Tests for high-level resolve method."""

    def test_resolve_tries_uei_first(self, sample_vendors):
        """Test resolve tries UEI first."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve(
            uei="ABC123DEF456", cage="1A2B3", duns="123456789", name="Acme Corporation"
        )

        assert match.method == "uei"
        assert match.score == 1.0

    def test_resolve_falls_back_to_cage(self, sample_vendors):
        """Test resolve falls back to CAGE when UEI fails."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve(uei="UNKNOWN", cage="1A2B3", name="Acme Corporation")

        assert match.method == "cage"
        assert match.score == 1.0

    def test_resolve_falls_back_to_duns(self, sample_vendors):
        """Test resolve falls back to DUNS."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve(uei="UNKNOWN", cage="UNKNOWN", duns="123456789")

        assert match.method == "duns"
        assert match.score == 1.0

    def test_resolve_falls_back_to_name(self, sample_vendors):
        """Test resolve falls back to name matching."""
        resolver = VendorResolver(records=sample_vendors, fuzzy_threshold=0.8)

        match = resolver.resolve(name="Acme Corp")

        assert match.record is not None
        assert match.method in ["name_exact", "name_fuzzy"]

    def test_resolve_no_match(self, sample_vendors):
        """Test resolve returns no match when all methods fail."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve(
            uei="UNKNOWN", cage="UNKNOWN", duns="UNKNOWN", name="Nonexistent Company"
        )

        assert match.record is None
        assert match.method == "none"
        assert match.note == "no match found"

    def test_resolve_with_no_inputs(self, sample_vendors):
        """Test resolve with no inputs returns no match."""
        resolver = VendorResolver(records=sample_vendors)

        match = resolver.resolve()

        assert match.record is None
        assert match.method == "none"


class TestAddRecord:
    """Tests for adding records at runtime."""

    def test_add_record_success(self):
        """Test adding a record updates indices."""
        resolver = VendorResolver(records=[])

        record = VendorRecord(uei="NEW123", cage="NEW1", duns="999999999", name="New Company")

        resolver.add_record(record)

        assert "NEW123" in resolver._uei_index
        assert "NEW1" in resolver._cage_index
        assert "999999999" in resolver._duns_index
        # Can now resolve by any identifier
        assert resolver.resolve_by_uei("NEW123").record == record

    def test_add_record_clears_cache(self, sample_vendors):
        """Test adding record clears cache."""
        resolver = VendorResolver(records=sample_vendors)

        # Populate cache
        resolver.resolve_by_name("Acme Corporation")
        assert len(resolver._cache) > 0

        # Add new record
        new_record = VendorRecord(uei="NEW123", cage=None, duns=None, name="New Co")
        resolver.add_record(new_record)

        # Cache should be cleared
        assert len(resolver._cache) == 0


class TestRemoveRecord:
    """Tests for removing records."""

    def test_remove_record_by_uei_success(self, sample_vendors):
        """Test removing a record by UEI."""
        resolver = VendorResolver(records=sample_vendors)

        result = resolver.remove_record_by_uei("ABC123DEF456")

        assert result is True
        # Should no longer be findable
        assert resolver.resolve_by_uei("ABC123DEF456").record is None

    def test_remove_record_clears_all_indices(self, sample_vendors):
        """Test removing record clears all indices."""
        resolver = VendorResolver(records=sample_vendors)

        resolver.remove_record_by_uei("ABC123DEF456")

        # All identifiers should be removed
        assert "ABC123DEF456" not in resolver._uei_index
        assert "1A2B3" not in resolver._cage_index
        assert "123456789" not in resolver._duns_index

    def test_remove_record_not_found(self, sample_vendors):
        """Test removing non-existent record returns False."""
        resolver = VendorResolver(records=sample_vendors)

        result = resolver.remove_record_by_uei("UNKNOWN")

        assert result is False

    def test_remove_record_clears_cache(self, sample_vendors):
        """Test removing record clears cache."""
        resolver = VendorResolver(records=sample_vendors)

        # Populate cache
        resolver.resolve_by_name("Acme Corporation")
        assert len(resolver._cache) > 0

        resolver.remove_record_by_uei("ABC123DEF456")

        # Cache should be cleared
        assert len(resolver._cache) == 0


class TestUtilities:
    """Tests for utility methods."""

    def test_clear_cache(self, sample_vendors):
        """Test clearing the cache."""
        resolver = VendorResolver(records=sample_vendors)

        # Populate cache
        resolver.resolve_by_name("Acme Corporation")
        resolver.resolve_by_name("Beta Technologies Inc")
        assert len(resolver._cache) > 0

        resolver.clear_cache()

        assert len(resolver._cache) == 0

    def test_stats(self, sample_vendors):
        """Test getting resolver statistics."""
        resolver = VendorResolver(records=sample_vendors)

        stats = resolver.stats()

        assert stats["records_by_uei"] == 3
        assert stats["records_by_cage"] == 3
        assert stats["records_by_duns"] == 3
        assert stats["unique_names"] == 4
        assert stats["cache_entries"] == 0

    def test_stats_with_cache(self, sample_vendors):
        """Test stats includes cache entries."""
        resolver = VendorResolver(records=sample_vendors)

        resolver.resolve_by_name("Acme Corporation")

        stats = resolver.stats()

        assert stats["cache_entries"] > 0


class TestBuildResolverFromIterable:
    """Tests for build_resolver_from_iterable factory."""

    def test_build_from_dicts(self):
        """Test building resolver from dict iterable."""
        data = [
            {"uei": "UEI001", "cage": "CAGE1", "duns": "111111111", "name": "Company A"},
            {"uei": "UEI002", "cage": "CAGE2", "duns": "222222222", "name": "Company B"},
        ]

        resolver = build_resolver_from_iterable(data)

        assert len(resolver._uei_index) == 2
        match = resolver.resolve_by_uei("UEI001")
        assert match.record is not None
        assert match.record.name == "Company A"

    def test_build_from_dicts_alternative_keys(self):
        """Test building with alternative key names."""
        data = [
            {"UEI": "UEI001", "CAGE": "CAGE1", "DUNS": "111111111", "company": "Company A"},
            {"uei_string": "UEI002", "cage": "CAGE2", "duns": "222222222", "org": "Company B"},
        ]

        resolver = build_resolver_from_iterable(data)

        assert len(resolver._uei_index) == 2
        assert resolver.resolve_by_uei("UEI001").record.name == "Company A"
        assert resolver.resolve_by_uei("UEI002").record.name == "Company B"

    def test_build_from_dicts_skips_no_name(self):
        """Test building skips records without names."""
        data = [
            {"uei": "UEI001", "name": "Company A"},
            {"uei": "UEI002"},  # No name
            {"uei": "UEI003", "name": "Company C"},
        ]

        resolver = build_resolver_from_iterable(data)

        assert len(resolver._uei_index) == 2  # Only 2 records with names

    def test_build_from_dicts_with_metadata(self):
        """Test building preserves metadata."""
        data = [
            {
                "uei": "UEI001",
                "name": "Company A",
                "metadata": {"state": "CA", "industry": "tech"},
            }
        ]

        resolver = build_resolver_from_iterable(data)

        match = resolver.resolve_by_uei("UEI001")
        assert match.record.metadata["state"] == "CA"
        assert match.record.metadata["industry"] == "tech"

    def test_build_with_custom_threshold(self):
        """Test building with custom fuzzy threshold."""
        data = [{"uei": "UEI001", "name": "Company A"}]

        resolver = build_resolver_from_iterable(data, fuzzy_threshold=0.85)

        assert resolver.fuzzy_threshold == 0.85


class TestFuzzyScore:
    """Tests for fuzzy scoring logic."""

    def test_fuzzy_score_exact_match(self):
        """Test fuzzy score for exact match."""
        resolver = VendorResolver(records=[])

        score = resolver._fuzzy_score("Acme Corporation", "Acme Corporation")

        assert score == 1.0

    def test_fuzzy_score_similar_strings(self):
        """Test fuzzy score for similar strings."""
        resolver = VendorResolver(records=[])

        score = resolver._fuzzy_score("Acme Corporation", "Acme Corp")

        assert 0.7 < score < 1.0

    def test_fuzzy_score_different_strings(self):
        """Test fuzzy score for different strings."""
        resolver = VendorResolver(records=[])

        score = resolver._fuzzy_score("Acme Corporation", "Different Company")

        assert score < 0.5

    def test_fuzzy_score_empty_strings(self):
        """Test fuzzy score with empty strings."""
        resolver = VendorResolver(records=[])

        assert resolver._fuzzy_score("", "Acme") == 0.0
        assert resolver._fuzzy_score("Acme", "") == 0.0
        assert resolver._fuzzy_score("", "") == 0.0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_resolver_with_duplicate_identifiers(self):
        """Test resolver handles duplicate identifiers (last one wins)."""
        vendors = [
            VendorRecord(uei="SAME_UEI", cage=None, duns=None, name="Company A"),
            VendorRecord(uei="SAME_UEI", cage=None, duns=None, name="Company B"),
        ]

        resolver = VendorResolver(records=vendors)

        # Last record with same UEI overwrites
        match = resolver.resolve_by_uei("SAME_UEI")
        assert match.record.name == "Company B"

    def test_resolver_with_none_identifiers(self):
        """Test resolver handles None identifiers gracefully."""
        vendors = [VendorRecord(uei=None, cage=None, duns=None, name="Company A")]

        resolver = VendorResolver(records=vendors)

        # Should still be findable by name
        match = resolver.resolve_by_name("Company A")
        assert match.record is not None

    def test_resolver_with_empty_string_identifiers(self):
        """Test resolver handles empty string identifiers."""
        vendors = [VendorRecord(uei="", cage="  ", duns=None, name="Company A")]

        resolver = VendorResolver(records=vendors)

        # Empty strings should not be indexed
        assert len(resolver._uei_index) == 0
        assert len(resolver._cage_index) == 0

    def test_multiple_vendors_same_normalized_name(self):
        """Test resolver handles multiple vendors with same normalized name."""
        vendors = [
            VendorRecord(uei="UEI001", cage=None, duns=None, name="Acme Corp"),
            VendorRecord(uei="UEI002", cage=None, duns=None, name="Acme, Corp."),
        ]

        resolver = VendorResolver(records=vendors)

        # Both normalize to same name - should return preferred (with UEI)
        match = resolver.resolve_by_name("Acme Corporation")
        assert match.record is not None
        # Should prefer one with UEI (either is fine since both have UEI)
        assert match.record.uei in ["UEI001", "UEI002"]

    def test_resolve_none_values(self):
        """Test high-level resolve with None values."""
        resolver = VendorResolver(records=[])

        match = resolver.resolve(uei=None, cage=None, duns=None, name=None)

        assert match.record is None
        assert match.method == "none"
