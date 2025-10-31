"""Unit tests for enrichment freshness tracking."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.models.enrichment import (
    EnrichmentFreshnessRecord,
    EnrichmentFreshnessRecordModel,
    EnrichmentStatus,
)
from src.utils.enrichment_freshness import (
    FreshnessStore,
    update_freshness_ledger,
)


@pytest.fixture
def freshness_store(tmp_path):
    """Create FreshnessStore for testing."""
    return FreshnessStore(parquet_path=tmp_path / "freshness.parquet")


@pytest.fixture
def sample_freshness_record():
    """Sample freshness record for testing."""
    return EnrichmentFreshnessRecord(
        award_id="AWARD-001",
        source="usaspending",
        last_attempt_at=datetime.now(),
        last_success_at=datetime.now(),
        payload_hash="abc123def456",
        status=EnrichmentStatus.SUCCESS,
        attempt_count=1,
        success_count=1,
        metadata={"test": "data"},
    )


class TestFreshnessStore:
    """Test FreshnessStore operations."""

    def test_save_and_load_record(self, freshness_store, sample_freshness_record):
        """Test saving and loading a single record."""
        freshness_store.save_record(sample_freshness_record)

        loaded = freshness_store.get_record("AWARD-001", "usaspending")

        assert loaded is not None
        assert loaded.award_id == sample_freshness_record.award_id
        assert loaded.source == sample_freshness_record.source
        assert loaded.payload_hash == sample_freshness_record.payload_hash

    def test_save_record_updates_existing(self, freshness_store, sample_freshness_record):
        """Test saving updates existing record."""
        freshness_store.save_record(sample_freshness_record)

        # Update the record
        updated_record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=datetime.now(),
            payload_hash="new_hash",
            status=EnrichmentStatus.SUCCESS,
            attempt_count=2,
            success_count=2,
        )
        freshness_store.save_record(updated_record)

        loaded = freshness_store.get_record("AWARD-001", "usaspending")
        assert loaded.payload_hash == "new_hash"
        assert loaded.attempt_count == 2

    def test_save_records_batch(self, freshness_store):
        """Test saving multiple records in batch."""
        records = [
            EnrichmentFreshnessRecord(
                award_id=f"AWARD-{i:03d}",
                source="usaspending",
                last_attempt_at=datetime.now(),
                last_success_at=datetime.now(),
                payload_hash=f"hash{i}",
                status=EnrichmentStatus.SUCCESS,
            )
            for i in range(10)
        ]

        freshness_store.save_records(records)

        df = freshness_store.load_all()
        assert len(df) == 10

    def test_load_all_returns_empty_dataframe_when_no_data(self, freshness_store):
        """Test load_all returns empty DataFrame when no data exists."""
        df = freshness_store.load_all()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_get_record_returns_none_when_not_found(self, freshness_store):
        """Test get_record returns None for non-existent record."""
        result = freshness_store.get_record("NONEXISTENT", "usaspending")
        assert result is None

    def test_get_stale_records_filters_by_sla(self, freshness_store):
        """Test get_stale_records filters by SLA threshold."""
        now = datetime.now()

        # Create records with different ages
        records = [
            EnrichmentFreshnessRecord(
                award_id="STALE-001",
                source="usaspending",
                last_attempt_at=now,
                last_success_at=now - timedelta(days=2),  # 2 days old - stale
                payload_hash="hash1",
                status=EnrichmentStatus.SUCCESS,
            ),
            EnrichmentFreshnessRecord(
                award_id="FRESH-001",
                source="usaspending",
                last_attempt_at=now,
                last_success_at=now - timedelta(hours=12),  # 12 hours old - fresh
                payload_hash="hash2",
                status=EnrichmentStatus.SUCCESS,
            ),
            EnrichmentFreshnessRecord(
                award_id="NEVER-001",
                source="usaspending",
                last_attempt_at=now,
                last_success_at=None,  # Never succeeded - stale
                payload_hash=None,
                status=EnrichmentStatus.PENDING,
            ),
        ]

        freshness_store.save_records(records)

        stale = freshness_store.get_stale_records("usaspending", sla_days=1)

        assert len(stale) == 2  # STALE-001 and NEVER-001
        award_ids = {r.award_id for r in stale}
        assert "STALE-001" in award_ids
        assert "NEVER-001" in award_ids
        assert "FRESH-001" not in award_ids

    def test_get_awards_needing_refresh(self, freshness_store):
        """Test get_awards_needing_refresh returns correct award IDs."""
        records = [
            EnrichmentFreshnessRecord(
                award_id=f"STALE-{i:03d}",
                source="usaspending",
                last_attempt_at=datetime.now(),
                last_success_at=datetime.now() - timedelta(days=2),
                payload_hash=f"hash{i}",
                status=EnrichmentStatus.SUCCESS,
            )
            for i in range(5)
        ]

        freshness_store.save_records(records)

        award_ids = freshness_store.get_awards_needing_refresh("usaspending", sla_days=1)
        assert len(award_ids) == 5
        assert all(aid.startswith("STALE-") for aid in award_ids)

    def test_get_awards_needing_refresh_filters_by_ids(self, freshness_store):
        """Test get_awards_needing_refresh filters to requested IDs only."""
        records = [
            EnrichmentFreshnessRecord(
                award_id=f"AWARD-{i:03d}",
                source="usaspending",
                last_attempt_at=datetime.now(),
                last_success_at=datetime.now() - timedelta(days=2),
                payload_hash=f"hash{i}",
                status=EnrichmentStatus.SUCCESS,
            )
            for i in range(10)
        ]

        freshness_store.save_records(records)

        requested_ids = ["AWARD-001", "AWARD-005", "AWARD-999"]  # 999 doesn't exist
        award_ids = freshness_store.get_awards_needing_refresh(
            "usaspending", sla_days=1, award_ids=requested_ids
        )

        assert len(award_ids) == 2  # Only 001 and 005 are stale
        assert "AWARD-001" in award_ids
        assert "AWARD-005" in award_ids
        assert "AWARD-999" not in award_ids


class TestUpdateFreshnessLedger:
    """Test update_freshness_ledger function."""

    def test_update_ledger_creates_new_record(self, freshness_store):
        """Test updating ledger creates new record if none exists."""
        record = update_freshness_ledger(
            store=freshness_store,
            award_id="AWARD-001",
            source="usaspending",
            success=True,
            payload_hash="abc123",
        )

        assert record.award_id == "AWARD-001"
        assert record.source == "usaspending"
        assert record.status == EnrichmentStatus.SUCCESS
        assert record.payload_hash == "abc123"
        assert record.attempt_count == 1
        assert record.success_count == 1

    def test_update_ledger_updates_existing_record(self, freshness_store):
        """Test updating ledger updates existing record."""
        # Create initial record
        update_freshness_ledger(
            store=freshness_store,
            award_id="AWARD-001",
            source="usaspending",
            success=True,
            payload_hash="hash1",
        )

        # Update it
        record = update_freshness_ledger(
            store=freshness_store,
            award_id="AWARD-001",
            source="usaspending",
            success=True,
            payload_hash="hash2",
        )

        assert record.attempt_count == 2
        assert record.success_count == 2
        assert record.payload_hash == "hash2"

    def test_update_ledger_handles_failure(self, freshness_store):
        """Test updating ledger handles failed attempts."""
        record = update_freshness_ledger(
            store=freshness_store,
            award_id="AWARD-001",
            source="usaspending",
            success=False,
            error_message="API error",
        )

        assert record.status == EnrichmentStatus.FAILED
        assert record.error_message == "API error"
        assert record.attempt_count == 1
        assert record.success_count == 0
        assert record.last_success_at is None

    def test_update_ledger_includes_metadata(self, freshness_store):
        """Test updating ledger includes metadata."""
        metadata = {"modification_number": "A00001", "action_date": "2024-01-15"}

        record = update_freshness_ledger(
            store=freshness_store,
            award_id="AWARD-001",
            source="usaspending",
            success=True,
            payload_hash="abc123",
            metadata=metadata,
        )

        assert record.metadata == metadata


class TestEnrichmentFreshnessRecord:
    """Test EnrichmentFreshnessRecord dataclass."""

    def test_is_stale_when_no_success(self):
        """Test is_stale returns True when no successful enrichment."""
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=None,
        )

        assert record.is_stale(sla_days=1) is True

    def test_is_stale_when_exceeds_sla(self):
        """Test is_stale returns True when exceeds SLA."""
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=datetime.now() - timedelta(days=2),
        )

        assert record.is_stale(sla_days=1) is True
        assert record.is_stale(sla_days=3) is False

    def test_has_delta_when_no_previous_hash(self):
        """Test has_delta returns True when no previous hash exists."""
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
        )

        assert record.has_delta("new_hash") is True

    def test_has_delta_detects_changes(self):
        """Test has_delta detects hash changes."""
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            payload_hash="old_hash",
        )

        assert record.has_delta("new_hash") is True
        assert record.has_delta("old_hash") is False


class TestEnrichmentFreshnessRecordModel:
    """Test Pydantic model for serialization."""

    def test_from_dataclass_conversion(self, sample_freshness_record):
        """Test converting dataclass to Pydantic model."""
        model = EnrichmentFreshnessRecordModel.from_dataclass(sample_freshness_record)

        assert model.award_id == sample_freshness_record.award_id
        assert model.source == sample_freshness_record.source
        assert model.payload_hash == sample_freshness_record.payload_hash
        assert model.status == sample_freshness_record.status.value

    def test_to_dataclass_conversion(self, sample_freshness_record):
        """Test converting Pydantic model back to dataclass."""
        model = EnrichmentFreshnessRecordModel.from_dataclass(sample_freshness_record)
        record = model.to_dataclass()

        assert isinstance(record, EnrichmentFreshnessRecord)
        assert record.award_id == sample_freshness_record.award_id
        assert record.status == sample_freshness_record.status

