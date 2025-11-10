"""
Tests for src/transition/features/vendor_crosswalk.py

Tests the VendorCrosswalk manager for vendor identity resolution,
alias management, and acquisition tracking with optional persistence.
"""

import json
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

from src.transition.features.vendor_crosswalk import (
    AliasRecord,
    CrosswalkRecord,
    VendorCrosswalk,
    _fuzzy_score,
    _iso_date,
    _normalize_identifier,
    _normalize_name,
)


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_normalize_identifier_strips_and_uppercases(self):
        """Test identifier normalization removes whitespace and uppercases."""
        assert _normalize_identifier("  abc123  ") == "ABC123"
        assert _normalize_identifier("abc-123") == "ABC-123"
        assert _normalize_identifier("abc_123") == "ABC_123"

    def test_normalize_identifier_removes_punctuation(self):
        """Test identifier normalization removes punctuation."""
        assert _normalize_identifier("abc.123") == "ABC123"
        assert _normalize_identifier("abc,123") == "ABC123"
        assert _normalize_identifier("abc/123") == "ABC123"
        assert _normalize_identifier("abc&123") == "ABC123"

    def test_normalize_identifier_returns_none_for_empty(self):
        """Test identifier normalization returns None for empty strings."""
        assert _normalize_identifier(None) is None
        assert _normalize_identifier("") is None
        assert _normalize_identifier("   ") is None

    def test_normalize_name_strips_and_normalizes_whitespace(self):
        """Test name normalization collapses whitespace."""
        assert _normalize_name("  Acme   Corporation  ") == "Acme Corporation"
        assert _normalize_name("Acme\n\tCorporation") == "Acme Corporation"

    def test_normalize_name_replaces_punctuation(self):
        """Test name normalization replaces punctuation."""
        assert _normalize_name("Acme, Inc.") == "Acme  Inc"
        assert _normalize_name("Acme & Co.") == "Acme AND Co"
        assert _normalize_name("Acme/Corp") == "Acme Corp"

    def test_normalize_name_returns_none_for_empty(self):
        """Test name normalization returns None for empty strings."""
        assert _normalize_name(None) is None

    def test_fuzzy_score_exact_match(self):
        """Test fuzzy score returns 1.0 for exact matches."""
        score = _fuzzy_score("Acme Corporation", "Acme Corporation")
        assert score == 1.0

    def test_fuzzy_score_similar_strings(self):
        """Test fuzzy score returns high score for similar strings."""
        score = _fuzzy_score("Acme Corporation", "Acme Corp")
        assert 0.7 < score < 1.0

    def test_fuzzy_score_different_strings(self):
        """Test fuzzy score returns low score for different strings."""
        score = _fuzzy_score("Acme Corporation", "Different Company")
        assert score < 0.5

    def test_fuzzy_score_empty_strings(self):
        """Test fuzzy score returns 0.0 for empty strings."""
        assert _fuzzy_score("", "Acme") == 0.0
        assert _fuzzy_score("Acme", "") == 0.0
        assert _fuzzy_score("", "") == 0.0

    def test_iso_date_from_date_object(self):
        """Test ISO date conversion from date object."""
        d = date(2023, 6, 15)
        assert _iso_date(d) == "2023-06-15"

    def test_iso_date_from_datetime_object(self):
        """Test ISO date conversion from datetime object."""
        dt = datetime(2023, 6, 15, 10, 30, 45)
        assert _iso_date(dt) == "2023-06-15"

    def test_iso_date_from_iso_string(self):
        """Test ISO date conversion from ISO string."""
        assert _iso_date("2023-06-15") == "2023-06-15"

    def test_iso_date_from_common_formats(self):
        """Test ISO date conversion from common formats."""
        assert _iso_date("06/15/2023") == "2023-06-15"
        assert _iso_date("2023/06/15") == "2023-06-15"

    def test_iso_date_returns_none_for_none(self):
        """Test ISO date conversion returns None for None input."""
        assert _iso_date(None) is None


class TestAliasRecord:
    """Tests for AliasRecord dataclass."""

    def test_alias_record_creation(self):
        """Test creating an AliasRecord with all fields."""
        alias = AliasRecord(
            name="Acme Corp",
            start_date="2020-01-01",
            end_date="2023-12-31",
            note="Previous name",
        )

        assert alias.name == "Acme Corp"
        assert alias.start_date == "2020-01-01"
        assert alias.end_date == "2023-12-31"
        assert alias.note == "Previous name"

    def test_alias_record_defaults(self):
        """Test AliasRecord with default values."""
        alias = AliasRecord(name="Acme")

        assert alias.name == "Acme"
        assert alias.start_date is None
        assert alias.end_date is None
        assert alias.note is None


class TestCrosswalkRecord:
    """Tests for CrosswalkRecord dataclass."""

    def test_crosswalk_record_creation(self):
        """Test creating a CrosswalkRecord with all fields."""
        aliases = [AliasRecord(name="Acme Corp")]
        record = CrosswalkRecord(
            canonical_id="co-123",
            canonical_name="Acme Corporation",
            uei="ABC123DEF456",
            cage="1A2B3",
            duns="123456789",
            aliases=aliases,
            metadata={"source": "test"},
        )

        assert record.canonical_id == "co-123"
        assert record.canonical_name == "Acme Corporation"
        assert record.uei == "ABC123DEF456"
        assert record.cage == "1A2B3"
        assert record.duns == "123456789"
        assert len(record.aliases) == 1
        assert record.metadata["source"] == "test"
        assert record.created_at  # Should have default timestamp

    def test_crosswalk_record_defaults(self):
        """Test CrosswalkRecord with default values."""
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme")

        assert record.uei is None
        assert record.cage is None
        assert record.duns is None
        assert record.aliases == []
        assert record.metadata == {}

    def test_crosswalk_record_as_dict(self):
        """Test CrosswalkRecord conversion to dict."""
        record = CrosswalkRecord(
            canonical_id="co-123", canonical_name="Acme", uei="ABC123", metadata={"key": "value"}
        )

        d = record.as_dict()

        assert d["canonical_id"] == "co-123"
        assert d["canonical_name"] == "Acme"
        assert d["uei"] == "ABC123"
        assert d["metadata"]["key"] == "value"

    def test_crosswalk_record_normalize(self):
        """Test CrosswalkRecord normalization."""
        aliases = [AliasRecord(name="  Acme  Corp  ")]
        record = CrosswalkRecord(
            canonical_id="co-123",
            canonical_name="  Acme  Corporation  ",
            uei=" abc123 ",
            cage=" 1a2b3 ",
            duns=" 123456789 ",
            aliases=aliases,
        )

        record.normalize()

        assert record.canonical_name == "Acme Corporation"
        assert record.uei == "ABC123"
        assert record.cage == "1A2B3"
        assert record.duns == "123456789"
        assert record.aliases[0].name == "Acme Corp"


class TestVendorCrosswalkInitialization:
    """Tests for VendorCrosswalk initialization."""

    def test_initialization_empty(self):
        """Test VendorCrosswalk initializes empty."""
        cw = VendorCrosswalk()

        assert len(cw.records) == 0
        assert len(cw._uei_index) == 0
        assert len(cw._cage_index) == 0
        assert len(cw._duns_index) == 0
        assert len(cw._name_index) == 0

    def test_initialization_with_records(self):
        """Test VendorCrosswalk initializes with records."""
        records = [
            CrosswalkRecord(canonical_id="co-1", canonical_name="Acme", uei="UEI001"),
            CrosswalkRecord(canonical_id="co-2", canonical_name="Beta", cage="CAGE001"),
        ]

        cw = VendorCrosswalk(records=records)

        assert len(cw.records) == 2
        assert "co-1" in cw.records
        assert "co-2" in cw.records


class TestAddOrMerge:
    """Tests for add_or_merge functionality."""

    def test_add_new_record(self):
        """Test adding a new record."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(
            canonical_id="co-123", canonical_name="Acme Corporation", uei="ABC123"
        )

        result = cw.add_or_merge(record)

        assert result.canonical_id == "co-123"
        assert "co-123" in cw.records
        assert cw._uei_index["ABC123"] == "co-123"

    def test_add_record_with_multiple_identifiers(self):
        """Test adding record indexes all identifiers."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(
            canonical_id="co-123",
            canonical_name="Acme Corporation",
            uei="ABC123",
            cage="1A2B3",
            duns="123456789",
        )

        cw.add_or_merge(record)

        assert cw._uei_index["ABC123"] == "co-123"
        assert cw._cage_index["1A2B3"] == "co-123"
        assert cw._duns_index["123456789"] == "co-123"

    def test_add_record_indexes_name(self):
        """Test adding record indexes normalized name."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme Corporation")

        cw.add_or_merge(record)

        assert "Acme Corporation" in cw._name_index
        assert "co-123" in cw._name_index["Acme Corporation"]

    def test_merge_by_uei_match(self):
        """Test merging records with matching UEI."""
        cw = VendorCrosswalk()
        record1 = CrosswalkRecord(canonical_id="co-1", canonical_name="Acme", uei="ABC123")
        cw.add_or_merge(record1)

        # Add record with same UEI but different ID
        record2 = CrosswalkRecord(
            canonical_id="co-2", canonical_name="Acme Corp", uei="ABC123", cage="1A2B3"
        )

        result = cw.add_or_merge(record2)

        # Should merge into existing co-1
        assert result.canonical_id == "co-1"
        assert result.cage == "1A2B3"  # Merged
        assert len(cw.records) == 1  # Only one record

    def test_merge_by_cage_match(self):
        """Test merging records with matching CAGE."""
        cw = VendorCrosswalk()
        record1 = CrosswalkRecord(canonical_id="co-1", canonical_name="Acme", cage="1A2B3")
        cw.add_or_merge(record1)

        # Add record with same CAGE
        record2 = CrosswalkRecord(canonical_id="co-2", canonical_name="Acme", cage="1A2B3", uei="ABC123")

        result = cw.add_or_merge(record2)

        assert result.canonical_id == "co-1"
        assert result.uei == "ABC123"  # Merged

    def test_merge_by_duns_match(self):
        """Test merging records with matching DUNS."""
        cw = VendorCrosswalk()
        record1 = CrosswalkRecord(canonical_id="co-1", canonical_name="Acme", duns="123456789")
        cw.add_or_merge(record1)

        # Add record with same DUNS
        record2 = CrosswalkRecord(canonical_id="co-2", canonical_name="Acme", duns="123456789", uei="ABC123")

        result = cw.add_or_merge(record2)

        assert result.canonical_id == "co-1"
        assert result.uei == "ABC123"  # Merged

    def test_update_existing_by_canonical_id(self):
        """Test updating record by canonical_id."""
        cw = VendorCrosswalk()
        record1 = CrosswalkRecord(canonical_id="co-1", canonical_name="Acme")
        cw.add_or_merge(record1)

        # Update same canonical_id with new data
        record2 = CrosswalkRecord(canonical_id="co-1", canonical_name="Acme", uei="ABC123")

        result = cw.add_or_merge(record2)

        assert result.canonical_id == "co-1"
        assert result.uei == "ABC123"
        assert len(cw.records) == 1

    def test_merge_combines_aliases(self):
        """Test merging combines aliases without duplicates."""
        cw = VendorCrosswalk()
        record1 = CrosswalkRecord(
            canonical_id="co-1",
            canonical_name="Acme",
            uei="ABC123",
            aliases=[AliasRecord(name="Acme Corp")],
        )
        cw.add_or_merge(record1)

        # Merge with additional alias
        record2 = CrosswalkRecord(
            canonical_id="co-2",
            canonical_name="Acme",
            uei="ABC123",
            aliases=[AliasRecord(name="Acme Inc"), AliasRecord(name="Acme Corp")],  # Duplicate
        )

        result = cw.add_or_merge(record2)

        # Should have 2 unique aliases
        assert len(result.aliases) == 2
        alias_names = {a.name for a in result.aliases}
        assert "Acme Corp" in alias_names
        assert "Acme Inc" in alias_names

    def test_merge_combines_metadata(self):
        """Test merging combines metadata."""
        cw = VendorCrosswalk()
        record1 = CrosswalkRecord(
            canonical_id="co-1", canonical_name="Acme", uei="ABC123", metadata={"source": "db1"}
        )
        cw.add_or_merge(record1)

        record2 = CrosswalkRecord(
            canonical_id="co-2", canonical_name="Acme", uei="ABC123", metadata={"verified": True}
        )

        result = cw.add_or_merge(record2)

        assert result.metadata["source"] == "db1"
        assert result.metadata["verified"] is True

    def test_merge_different_canonical_names_creates_alias(self):
        """Test merging records with different canonical names creates alias."""
        cw = VendorCrosswalk()
        record1 = CrosswalkRecord(canonical_id="co-1", canonical_name="Acme Corporation", uei="ABC123")
        cw.add_or_merge(record1)

        record2 = CrosswalkRecord(canonical_id="co-2", canonical_name="Acme Inc", uei="ABC123")

        result = cw.add_or_merge(record2)

        # Should keep original canonical_name and add new name as alias
        assert result.canonical_name == "Acme Corporation"
        alias_names = [a.name for a in result.aliases]
        assert "Acme Inc" in alias_names


class TestLookupMethods:
    """Tests for lookup methods."""

    def test_find_by_uei_success(self):
        """Test finding record by UEI."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme", uei="ABC123")
        cw.add_or_merge(record)

        result = cw.find_by_uei("ABC123")

        assert result is not None
        assert result.canonical_id == "co-123"

    def test_find_by_uei_case_insensitive(self):
        """Test finding by UEI is case-insensitive."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme", uei="ABC123")
        cw.add_or_merge(record)

        result = cw.find_by_uei("abc123")  # Lowercase

        assert result is not None
        assert result.canonical_id == "co-123"

    def test_find_by_uei_not_found(self):
        """Test finding by UEI returns None when not found."""
        cw = VendorCrosswalk()

        result = cw.find_by_uei("UNKNOWN")

        assert result is None

    def test_find_by_cage_success(self):
        """Test finding record by CAGE."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme", cage="1A2B3")
        cw.add_or_merge(record)

        result = cw.find_by_cage("1A2B3")

        assert result is not None
        assert result.canonical_id == "co-123"

    def test_find_by_duns_success(self):
        """Test finding record by DUNS."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme", duns="123456789")
        cw.add_or_merge(record)

        result = cw.find_by_duns("123456789")

        assert result is not None
        assert result.canonical_id == "co-123"

    def test_find_by_name_exact_match(self):
        """Test finding by name with exact match."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme Corporation")
        cw.add_or_merge(record)

        result = cw.find_by_name("Acme Corporation")

        assert result is not None
        assert result[0].canonical_id == "co-123"
        assert result[1] == 1.0  # Perfect score

    def test_find_by_name_fuzzy_match(self):
        """Test finding by name with fuzzy matching."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme Corporation")
        cw.add_or_merge(record)

        result = cw.find_by_name("Acme Corp", fuzzy_threshold=0.7)

        assert result is not None
        assert result[0].canonical_id == "co-123"
        assert result[1] > 0.7  # Above threshold

    def test_find_by_name_below_threshold(self):
        """Test finding by name below threshold returns None."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme Corporation")
        cw.add_or_merge(record)

        result = cw.find_by_name("Different Company", fuzzy_threshold=0.9)

        assert result is None

    def test_find_by_any_tries_uei_first(self):
        """Test find_by_any tries UEI first."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(
            canonical_id="co-123", canonical_name="Acme", uei="ABC123", cage="1A2B3"
        )
        cw.add_or_merge(record)

        result = cw.find_by_any(uei="ABC123", cage="1A2B3")

        assert result is not None
        assert result[0].canonical_id == "co-123"
        assert result[1] == "uei"  # Method
        assert result[2] == 1.0  # Score

    def test_find_by_any_falls_back_to_cage(self):
        """Test find_by_any falls back to CAGE when UEI fails."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme", cage="1A2B3")
        cw.add_or_merge(record)

        result = cw.find_by_any(uei="UNKNOWN", cage="1A2B3")

        assert result is not None
        assert result[1] == "cage"

    def test_find_by_any_falls_back_to_duns(self):
        """Test find_by_any falls back to DUNS."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme", duns="123456789")
        cw.add_or_merge(record)

        result = cw.find_by_any(uei="UNKNOWN", cage="UNKNOWN", duns="123456789")

        assert result is not None
        assert result[1] == "duns"

    def test_find_by_any_falls_back_to_name(self):
        """Test find_by_any falls back to name fuzzy matching."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme Corporation")
        cw.add_or_merge(record)

        result = cw.find_by_any(name="Acme Corp", fuzzy_threshold=0.7)

        assert result is not None
        assert result[1] == "name"
        assert result[2] > 0.7


class TestRemove:
    """Tests for record removal."""

    def test_remove_success(self):
        """Test removing a record."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(
            canonical_id="co-123",
            canonical_name="Acme Corporation",
            uei="ABC123",
            cage="1A2B3",
            duns="123456789",
        )
        cw.add_or_merge(record)

        result = cw.remove("co-123")

        assert result is True
        assert "co-123" not in cw.records
        assert "ABC123" not in cw._uei_index
        assert "1A2B3" not in cw._cage_index
        assert "123456789" not in cw._duns_index

    def test_remove_not_found(self):
        """Test removing non-existent record returns False."""
        cw = VendorCrosswalk()

        result = cw.remove("co-unknown")

        assert result is False

    def test_remove_cleans_name_index(self):
        """Test removing record cleans name index."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme Corporation")
        cw.add_or_merge(record)

        cw.remove("co-123")

        # Name index should be cleaned up
        assert "Acme Corporation" not in cw._name_index


class TestAliasHandling:
    """Tests for alias management."""

    def test_add_alias_success(self):
        """Test adding an alias to a record."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme Corporation")
        cw.add_or_merge(record)

        result = cw.add_alias(
            canonical_id="co-123",
            alias_name="Acme Inc",
            start_date=date(2020, 1, 1),
            note="Previous name",
        )

        assert result is True
        rec = cw.records["co-123"]
        assert len(rec.aliases) == 1
        assert rec.aliases[0].name == "Acme Inc"
        assert rec.aliases[0].start_date == "2020-01-01"
        assert rec.aliases[0].note == "Previous name"

    def test_add_alias_prevents_duplicates(self):
        """Test adding duplicate alias is prevented."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme Corporation")
        cw.add_or_merge(record)

        cw.add_alias("co-123", "Acme Inc")
        cw.add_alias("co-123", "Acme Inc")  # Duplicate

        rec = cw.records["co-123"]
        assert len(rec.aliases) == 1  # Only one

    def test_add_alias_record_not_found(self):
        """Test adding alias to non-existent record returns False."""
        cw = VendorCrosswalk()

        result = cw.add_alias("co-unknown", "Acme")

        assert result is False

    def test_add_alias_updates_name_index(self):
        """Test adding alias updates name index."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme Corporation")
        cw.add_or_merge(record)

        cw.add_alias("co-123", "Acme Inc")

        # Should be findable by alias name
        assert "Acme Inc" in cw._name_index
        assert "co-123" in cw._name_index["Acme Inc"]


class TestAcquisitionHandling:
    """Tests for acquisition/merger handling."""

    def test_handle_acquisition_with_merge(self):
        """Test handling acquisition with merge."""
        cw = VendorCrosswalk()
        acquirer = CrosswalkRecord(
            canonical_id="co-1", canonical_name="Big Corp", uei="UEI001", cage="CAGE1"
        )
        acquired = CrosswalkRecord(
            canonical_id="co-2", canonical_name="Small Inc", uei="UEI002", duns="123456789"
        )
        cw.add_or_merge(acquirer)
        cw.add_or_merge(acquired)

        result = cw.handle_acquisition(
            acquirer_id="co-1",
            acquired_id="co-2",
            date_of_acquisition=date(2024, 1, 1),
            merge=True,
            note="Acquisition",
        )

        assert result is True
        # Acquired should be removed
        assert "co-2" not in cw.records
        # Acquirer should have merged data
        acq = cw.records["co-1"]
        assert acq.duns == "123456789"  # Merged from acquired
        # Acquisition metadata
        assert "acquisitions" in acq.metadata
        assert len(acq.metadata["acquisitions"]) == 1
        assert acq.metadata["acquisitions"][0]["acquired_id"] == "co-2"

    def test_handle_acquisition_without_merge(self):
        """Test handling acquisition without merge."""
        cw = VendorCrosswalk()
        acquirer = CrosswalkRecord(canonical_id="co-1", canonical_name="Big Corp")
        acquired = CrosswalkRecord(canonical_id="co-2", canonical_name="Small Inc")
        cw.add_or_merge(acquirer)
        cw.add_or_merge(acquired)

        result = cw.handle_acquisition(
            acquirer_id="co-1", acquired_id="co-2", merge=False
        )

        assert result is True
        # Both should still exist
        assert "co-1" in cw.records
        assert "co-2" in cw.records
        # Both should have metadata
        assert "acquisitions" in cw.records["co-1"].metadata
        assert "acquired_by" in cw.records["co-2"].metadata

    def test_handle_acquisition_adds_alias(self):
        """Test acquisition adds acquired name as alias."""
        cw = VendorCrosswalk()
        acquirer = CrosswalkRecord(canonical_id="co-1", canonical_name="Big Corp")
        acquired = CrosswalkRecord(canonical_id="co-2", canonical_name="Small Inc")
        cw.add_or_merge(acquirer)
        cw.add_or_merge(acquired)

        cw.handle_acquisition("co-1", "co-2", date_of_acquisition=date(2024, 1, 1))

        acq = cw.records["co-1"]
        alias_names = [a.name for a in acq.aliases]
        assert "Small Inc" in alias_names

    def test_handle_acquisition_records_not_found(self):
        """Test acquisition with non-existent records returns False."""
        cw = VendorCrosswalk()

        result = cw.handle_acquisition("co-unknown1", "co-unknown2")

        assert result is False


class TestPersistence:
    """Tests for persistence methods."""

    def test_to_list_of_dicts(self):
        """Test converting crosswalk to list of dicts."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme", uei="ABC123")
        cw.add_or_merge(record)

        dicts = cw.to_list_of_dicts()

        assert len(dicts) == 1
        assert dicts[0]["canonical_id"] == "co-123"
        assert dicts[0]["canonical_name"] == "Acme"
        assert dicts[0]["uei"] == "ABC123"

    def test_save_jsonl(self):
        """Test saving to JSONL format."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme", uei="ABC123")
        cw.add_or_merge(record)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "crosswalk.jsonl"
            cw.save_jsonl(path)

            assert path.exists()

            # Verify content
            with open(path) as f:
                lines = f.readlines()
                assert len(lines) == 1
                data = json.loads(lines[0])
                assert data["canonical_id"] == "co-123"

    def test_load_jsonl(self):
        """Test loading from JSONL format."""
        # Create JSONL file
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "crosswalk.jsonl"
            data = {
                "canonical_id": "co-123",
                "canonical_name": "Acme",
                "uei": "ABC123",
                "cage": "1A2B3",
                "duns": "123456789",
                "aliases": [{"name": "Acme Inc", "start_date": "2020-01-01", "note": "Old name"}],
                "metadata": {"source": "test"},
            }
            with open(path, "w") as f:
                f.write(json.dumps(data) + "\n")

            cw = VendorCrosswalk()
            cw.load_jsonl(path)

            assert len(cw.records) == 1
            rec = cw.records["co-123"]
            assert rec.canonical_name == "Acme"
            assert rec.uei == "ABC123"
            assert len(rec.aliases) == 1
            assert rec.aliases[0].name == "Acme Inc"

    def test_load_jsonl_file_not_found(self):
        """Test loading from non-existent JSONL raises FileNotFoundError."""
        cw = VendorCrosswalk()

        with pytest.raises(FileNotFoundError):
            cw.load_jsonl("/nonexistent/path.jsonl")

    def test_save_parquet_requires_pandas(self):
        """Test saving to Parquet requires pandas."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme")
        cw.add_or_merge(record)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "crosswalk.parquet"

            # If pandas not available, should raise RuntimeError
            with patch("src.transition.features.vendor_crosswalk.pd", None):
                with pytest.raises(RuntimeError, match="pandas is required"):
                    cw.save_parquet(path)

    def test_save_duckdb_table_requires_dependencies(self):
        """Test saving to DuckDB requires dependencies."""
        cw = VendorCrosswalk()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            # If duckdb or pandas not available, should raise RuntimeError
            with patch("src.transition.features.vendor_crosswalk.duckdb", None):
                with pytest.raises(RuntimeError, match="duckdb and pandas required"):
                    cw.save_duckdb_table(db_path)

    def test_load_duckdb_table_requires_dependencies(self):
        """Test loading from DuckDB requires dependencies."""
        cw = VendorCrosswalk()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            with patch("src.transition.features.vendor_crosswalk.duckdb", None):
                with pytest.raises(RuntimeError, match="duckdb and pandas required"):
                    cw.load_duckdb_table(db_path)


class TestUtilities:
    """Tests for utility methods."""

    def test_list_records(self):
        """Test listing all records."""
        cw = VendorCrosswalk()
        record1 = CrosswalkRecord(canonical_id="co-1", canonical_name="Acme")
        record2 = CrosswalkRecord(canonical_id="co-2", canonical_name="Beta")
        cw.add_or_merge(record1)
        cw.add_or_merge(record2)

        records = cw.list_records()

        assert len(records) == 2
        ids = {r.canonical_id for r in records}
        assert ids == {"co-1", "co-2"}

    def test_stats(self):
        """Test getting crosswalk statistics."""
        cw = VendorCrosswalk()
        record1 = CrosswalkRecord(
            canonical_id="co-1", canonical_name="Acme", uei="UEI001", cage="CAGE1"
        )
        record2 = CrosswalkRecord(
            canonical_id="co-2", canonical_name="Beta", duns="123456789"
        )
        cw.add_or_merge(record1)
        cw.add_or_merge(record2)

        stats = cw.stats()

        assert stats["count"] == 2
        assert stats["uei_index"] == 1
        assert stats["cage_index"] == 1
        assert stats["duns_index"] == 1
        assert stats["name_index"] == 2


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_add_record_with_empty_identifiers(self):
        """Test adding record with empty/None identifiers."""
        cw = VendorCrosswalk()
        record = CrosswalkRecord(
            canonical_id="co-123", canonical_name="Acme", uei=None, cage="", duns="   "
        )

        cw.add_or_merge(record)

        # Should still add record but not index empty identifiers
        assert "co-123" in cw.records
        assert len(cw._uei_index) == 0
        assert len(cw._cage_index) == 0
        assert len(cw._duns_index) == 0

    def test_find_with_empty_values(self):
        """Test finding with empty/None values returns None."""
        cw = VendorCrosswalk()

        assert cw.find_by_uei(None) is None
        assert cw.find_by_uei("") is None
        assert cw.find_by_cage(None) is None
        assert cw.find_by_duns(None) is None
        assert cw.find_by_name(None) is None

    def test_multiple_records_same_normalized_name(self):
        """Test multiple records can have same normalized name."""
        cw = VendorCrosswalk()
        record1 = CrosswalkRecord(canonical_id="co-1", canonical_name="Acme Corp", uei="UEI001")
        record2 = CrosswalkRecord(canonical_id="co-2", canonical_name="Acme, Corp.", uei="UEI002")

        cw.add_or_merge(record1)
        cw.add_or_merge(record2)

        # Both normalize to "Acme  Corp"
        assert len(cw.records) == 2

    def test_jsonl_with_empty_lines(self):
        """Test loading JSONL handles empty lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "crosswalk.jsonl"
            with open(path, "w") as f:
                f.write('{"canonical_id": "co-1", "canonical_name": "Acme"}\n')
                f.write("\n")  # Empty line
                f.write('{"canonical_id": "co-2", "canonical_name": "Beta"}\n')

            cw = VendorCrosswalk()
            cw.load_jsonl(path)

            assert len(cw.records) == 2
