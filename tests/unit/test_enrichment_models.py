"""Unit tests for enrichment models."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.models.enrichment import (
    EnrichmentDeltaEvent,
    EnrichmentFreshnessRecord,
    EnrichmentFreshnessRecordModel,
    EnrichmentStatus,
)


pytestmark = pytest.mark.fast


class TestEnrichmentStatus:
    """Test EnrichmentStatus enum."""

    def test_status_values(self):
        """Test status enum has expected values."""
        assert EnrichmentStatus.SUCCESS.value == "success"
        assert EnrichmentStatus.FAILED.value == "failed"
        assert EnrichmentStatus.UNCHANGED.value == "unchanged"
        assert EnrichmentStatus.STALE.value == "stale"


class TestEnrichmentFreshnessRecord:
    """Test EnrichmentFreshnessRecord dataclass."""

    def test_record_creation(self):
        """Test creating a freshness record."""
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=datetime.now(),
            payload_hash="abc123",
            status=EnrichmentStatus.SUCCESS,
        )

        assert record.award_id == "AWARD-001"
        assert record.source == "usaspending"
        assert record.payload_hash == "abc123"
        assert record.status == EnrichmentStatus.SUCCESS

    def test_record_defaults(self):
        """Test record has correct defaults."""
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
        )

        assert record.last_success_at is None
        assert record.payload_hash is None
        assert record.status == EnrichmentStatus.PENDING
        assert record.error_message is None
        assert record.metadata == {}
        assert record.attempt_count == 0
        assert record.success_count == 0

    def test_is_stale_with_no_success(self):
        """Test is_stale returns True when no success timestamp."""
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=None,
        )

        assert record.is_stale(sla_days=1) is True

    def test_is_stale_within_sla(self):
        """Test is_stale returns False when within SLA."""
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=datetime.now(),  # Just now
        )

        assert record.is_stale(sla_days=1) is False

    def test_has_delta_when_no_previous_hash(self):
        """Test has_delta returns True when no previous hash."""
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            payload_hash=None,
        )

        assert record.has_delta("new_hash") is True

    def test_has_delta_detects_change(self):
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
    """Test EnrichmentFreshnessRecordModel Pydantic model."""

    def test_model_creation(self):
        """Test creating Pydantic model."""
        model = EnrichmentFreshnessRecordModel(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=datetime.now(),
            payload_hash="abc123",
            status="success",
        )

        assert model.award_id == "AWARD-001"
        assert model.source == "usaspending"
        assert model.status == "success"

    def test_from_dataclass_conversion(self):
        """Test converting dataclass to Pydantic model."""
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=datetime.now(),
            payload_hash="abc123",
            status=EnrichmentStatus.SUCCESS,
            metadata={"key": "value"},
        )

        model = EnrichmentFreshnessRecordModel.from_dataclass(record)

        assert model.award_id == record.award_id
        assert model.source == record.source
        assert model.status == "success"  # Converted to string
        assert model.metadata == {"key": "value"}

    def test_to_dataclass_conversion(self):
        """Test converting Pydantic model back to dataclass."""
        model = EnrichmentFreshnessRecordModel(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=datetime.now(),
            payload_hash="abc123",
            status="success",
            metadata={"key": "value"},
        )

        record = model.to_dataclass()

        assert isinstance(record, EnrichmentFreshnessRecord)
        assert record.award_id == "AWARD-001"
        assert record.status == EnrichmentStatus.SUCCESS  # Converted back to enum
        assert record.metadata == {"key": "value"}


class TestEnrichmentDeltaEvent:
    """Test EnrichmentDeltaEvent model."""

    def test_delta_event_creation(self):
        """Test creating a delta event."""
        event = EnrichmentDeltaEvent(
            award_id="AWARD-001",
            source="usaspending",
            old_payload_hash="old_hash",
            new_payload_hash="new_hash",
            changed_fields=["naics_code", "recipient_name"],
            metadata={"modification_number": "A00001"},
        )

        assert event.award_id == "AWARD-001"
        assert event.source == "usaspending"
        assert event.old_payload_hash == "old_hash"
        assert event.new_payload_hash == "new_hash"
        assert len(event.changed_fields) == 2
        assert "naics_code" in event.changed_fields

    def test_delta_event_defaults(self):
        """Test delta event has correct defaults."""
        event = EnrichmentDeltaEvent(
            award_id="AWARD-001",
            source="usaspending",
            new_payload_hash="new_hash",
        )

        assert event.old_payload_hash is None
        assert event.changed_fields == []
        assert event.metadata == {}
        assert event.timestamp is not None  # Should be auto-generated
