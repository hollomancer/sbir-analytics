"""Tests for enrichment and patent models."""

import pytest
from datetime import datetime, date, timedelta
from pydantic import ValidationError

from src.models.enrichment import (
    EnrichmentStatus,
    EnrichmentFreshnessRecord,
    EnrichmentFreshnessRecordModel,
    EnrichmentDeltaEvent,
)
from src.models.patent import Patent, RawPatent, PatentCitation


class TestEnrichmentStatus:
    """Tests for EnrichmentStatus enum."""

    def test_enrichment_status_values(self):
        """Test EnrichmentStatus enum has correct values."""
        assert EnrichmentStatus.SUCCESS == "success"
        assert EnrichmentStatus.FAILED == "failed"
        assert EnrichmentStatus.UNCHANGED == "unchanged"
        assert EnrichmentStatus.STALE == "stale"
        assert EnrichmentStatus.PENDING == "pending"
        assert EnrichmentStatus.SKIPPED == "skipped"

    def test_enrichment_status_all_values(self):
        """Test all EnrichmentStatus values are accessible."""
        all_statuses = [
            EnrichmentStatus.SUCCESS,
            EnrichmentStatus.FAILED,
            EnrichmentStatus.UNCHANGED,
            EnrichmentStatus.STALE,
            EnrichmentStatus.PENDING,
            EnrichmentStatus.SKIPPED,
        ]
        assert len(all_statuses) == 6


class TestEnrichmentFreshnessRecord:
    """Tests for EnrichmentFreshnessRecord dataclass."""

    def test_valid_freshness_record(self):
        """Test creating a valid freshness record."""
        now = datetime.now()
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=now,
            last_success_at=now,
            payload_hash="abc123def456",
            status=EnrichmentStatus.SUCCESS,
            error_message=None,
            metadata={"modification_number": 5},
            attempt_count=3,
            success_count=2,
        )
        assert record.award_id == "AWARD-001"
        assert record.source == "usaspending"
        assert record.status == EnrichmentStatus.SUCCESS
        assert record.attempt_count == 3
        assert record.success_count == 2

    def test_freshness_record_minimal(self):
        """Test freshness record with only required fields."""
        now = datetime.now()
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-002",
            source="sam_gov",
            last_attempt_at=now,
        )
        assert record.award_id == "AWARD-002"
        assert record.source == "sam_gov"
        assert record.last_success_at is None
        assert record.payload_hash is None
        assert record.status == EnrichmentStatus.PENDING
        assert record.error_message is None
        assert record.metadata == {}
        assert record.attempt_count == 0
        assert record.success_count == 0

    def test_is_stale_with_no_success(self):
        """Test is_stale returns True when last_success_at is None."""
        now = datetime.now()
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-003",
            source="test",
            last_attempt_at=now,
            last_success_at=None,
        )
        assert record.is_stale(sla_days=30) is True

    def test_is_stale_within_sla(self):
        """Test is_stale returns False when within SLA."""
        now = datetime.now()
        recent = now - timedelta(days=5)
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-004",
            source="test",
            last_attempt_at=now,
            last_success_at=recent,
        )
        assert record.is_stale(sla_days=30) is False

    def test_is_stale_exceeds_sla(self):
        """Test is_stale returns True when exceeding SLA."""
        now = datetime.now()
        old = now - timedelta(days=35)
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-005",
            source="test",
            last_attempt_at=now,
            last_success_at=old,
        )
        assert record.is_stale(sla_days=30) is True

    def test_is_stale_exactly_at_sla(self):
        """Test is_stale at exact SLA boundary."""
        now = datetime.now()
        boundary = now - timedelta(days=30)
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-006",
            source="test",
            last_attempt_at=now,
            last_success_at=boundary,
        )
        # Exactly at boundary should not be stale (age = SLA, not > SLA)
        assert record.is_stale(sla_days=30) is False

    def test_has_delta_with_no_previous_hash(self):
        """Test has_delta returns True when no previous hash."""
        now = datetime.now()
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-007",
            source="test",
            last_attempt_at=now,
            payload_hash=None,
        )
        assert record.has_delta("new_hash_123") is True

    def test_has_delta_with_different_hash(self):
        """Test has_delta returns True when hashes differ."""
        now = datetime.now()
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-008",
            source="test",
            last_attempt_at=now,
            payload_hash="old_hash_abc",
        )
        assert record.has_delta("new_hash_xyz") is True

    def test_has_delta_with_same_hash(self):
        """Test has_delta returns False when hashes match."""
        now = datetime.now()
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-009",
            source="test",
            last_attempt_at=now,
            payload_hash="same_hash_123",
        )
        assert record.has_delta("same_hash_123") is False

    def test_freshness_record_with_error(self):
        """Test freshness record with error status."""
        now = datetime.now()
        record = EnrichmentFreshnessRecord(
            award_id="AWARD-010",
            source="test",
            last_attempt_at=now,
            status=EnrichmentStatus.FAILED,
            error_message="API timeout",
            attempt_count=5,
            success_count=0,
        )
        assert record.status == EnrichmentStatus.FAILED
        assert record.error_message == "API timeout"
        assert record.attempt_count == 5
        assert record.success_count == 0


class TestEnrichmentFreshnessRecordModel:
    """Tests for EnrichmentFreshnessRecordModel Pydantic model."""

    def test_valid_freshness_record_model(self):
        """Test creating a valid freshness record model."""
        now = datetime.now()
        model = EnrichmentFreshnessRecordModel(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=now,
            last_success_at=now,
            payload_hash="hash123",
            status="success",
            metadata={"key": "value"},
            attempt_count=2,
            success_count=2,
        )
        assert model.award_id == "AWARD-001"
        assert model.status == "success"

    def test_freshness_record_model_defaults(self):
        """Test freshness record model with default values."""
        now = datetime.now()
        model = EnrichmentFreshnessRecordModel(
            award_id="AWARD-002",
            source="test",
            last_attempt_at=now,
        )
        assert model.last_success_at is None
        assert model.payload_hash is None
        assert model.status == "pending"
        assert model.error_message is None
        assert model.metadata == {}
        assert model.attempt_count == 0
        assert model.success_count == 0

    def test_from_dataclass_conversion(self):
        """Test converting dataclass to Pydantic model."""
        now = datetime.now()
        dataclass_record = EnrichmentFreshnessRecord(
            award_id="AWARD-003",
            source="usaspending",
            last_attempt_at=now,
            last_success_at=now,
            payload_hash="hash456",
            status=EnrichmentStatus.SUCCESS,
            error_message=None,
            metadata={"test": "data"},
            attempt_count=5,
            success_count=4,
        )
        model = EnrichmentFreshnessRecordModel.from_dataclass(dataclass_record)
        assert model.award_id == "AWARD-003"
        assert model.source == "usaspending"
        assert model.payload_hash == "hash456"
        assert model.status == "success"
        assert model.attempt_count == 5
        assert model.success_count == 4

    def test_to_dataclass_conversion(self):
        """Test converting Pydantic model to dataclass."""
        now = datetime.now()
        model = EnrichmentFreshnessRecordModel(
            award_id="AWARD-004",
            source="sam_gov",
            last_attempt_at=now,
            last_success_at=now,
            payload_hash="hash789",
            status="failed",
            error_message="Connection error",
            metadata={"retry": 3},
            attempt_count=3,
            success_count=0,
        )
        dataclass_record = model.to_dataclass()
        assert dataclass_record.award_id == "AWARD-004"
        assert dataclass_record.source == "sam_gov"
        assert dataclass_record.payload_hash == "hash789"
        assert dataclass_record.status == EnrichmentStatus.FAILED
        assert dataclass_record.error_message == "Connection error"
        assert dataclass_record.attempt_count == 3

    def test_bidirectional_conversion(self):
        """Test round-trip conversion dataclass -> model -> dataclass."""
        now = datetime.now()
        original = EnrichmentFreshnessRecord(
            award_id="AWARD-005",
            source="test",
            last_attempt_at=now,
            last_success_at=now,
            payload_hash="roundtrip",
            status=EnrichmentStatus.UNCHANGED,
            metadata={"round": "trip"},
            attempt_count=10,
            success_count=8,
        )
        model = EnrichmentFreshnessRecordModel.from_dataclass(original)
        back_to_dataclass = model.to_dataclass()

        assert back_to_dataclass.award_id == original.award_id
        assert back_to_dataclass.source == original.source
        assert back_to_dataclass.payload_hash == original.payload_hash
        assert back_to_dataclass.status == original.status
        assert back_to_dataclass.attempt_count == original.attempt_count
        assert back_to_dataclass.success_count == original.success_count


class TestEnrichmentDeltaEvent:
    """Tests for EnrichmentDeltaEvent model."""

    def test_valid_delta_event(self):
        """Test creating a valid delta event."""
        now = datetime.now()
        event = EnrichmentDeltaEvent(
            award_id="AWARD-001",
            source="usaspending",
            timestamp=now,
            old_payload_hash="old_hash",
            new_payload_hash="new_hash",
            changed_fields=["obligation_amount", "modification_number"],
            metadata={"delta_type": "modification"},
        )
        assert event.award_id == "AWARD-001"
        assert event.source == "usaspending"
        assert event.old_payload_hash == "old_hash"
        assert event.new_payload_hash == "new_hash"
        assert len(event.changed_fields) == 2

    def test_delta_event_minimal(self):
        """Test delta event with only required fields."""
        event = EnrichmentDeltaEvent(
            award_id="AWARD-002",
            source="test",
            new_payload_hash="hash123",
        )
        assert event.award_id == "AWARD-002"
        assert event.source == "test"
        assert event.new_payload_hash == "hash123"
        assert event.old_payload_hash is None
        assert event.changed_fields == []
        assert event.metadata == {}
        assert isinstance(event.timestamp, datetime)

    def test_delta_event_timestamp_default_factory(self):
        """Test delta event timestamp uses default factory."""
        before = datetime.now()
        event = EnrichmentDeltaEvent(
            award_id="AWARD-003",
            source="test",
            new_payload_hash="hash456",
        )
        after = datetime.now()
        assert before <= event.timestamp <= after

    def test_delta_event_with_no_old_hash(self):
        """Test delta event representing initial enrichment."""
        event = EnrichmentDeltaEvent(
            award_id="AWARD-004",
            source="usaspending",
            old_payload_hash=None,
            new_payload_hash="first_hash",
            changed_fields=["*"],  # All fields are "new"
        )
        assert event.old_payload_hash is None
        assert event.new_payload_hash == "first_hash"
        assert "*" in event.changed_fields


class TestPatentModel:
    """Tests for Patent model."""

    def test_valid_patent(self):
        """Test creating a valid patent."""
        patent = Patent(
            patent_number="US10123456B2",
            title="Innovative Technology",
            abstract="This patent describes...",
            filing_date=date(2020, 1, 15),
            grant_date=date(2022, 6, 20),
            publication_date=date(2021, 7, 15),
            inventors=["Alice Smith", "Bob Johnson"],
            assignee="Acme Corporation",
            uspc_class="705/14",
            cpc_class="G06F21/60",
            status="Active",
            patent_type="Utility",
            application_number="16/123456",
            related_patents=["US9876543B2"],
            sbir_award_id="AWARD-001",
        )
        assert patent.patent_number == "US10123456B2"
        assert patent.title == "Innovative Technology"
        assert len(patent.inventors) == 2
        assert patent.assignee == "Acme Corporation"

    def test_patent_minimal(self):
        """Test patent with only required fields."""
        patent = Patent(
            patent_number="US12345678",
            title="Test Patent",
        )
        assert patent.patent_number == "US12345678"
        assert patent.title == "Test Patent"
        assert patent.abstract is None
        assert patent.inventors == []
        assert patent.related_patents == []

    def test_patent_number_validator_accepts_valid(self):
        """Test patent_number validator accepts valid formats."""
        valid_numbers = [
            "US10123456B2",
            "US9876543",
            "EP1234567A1",
            "12345678",
        ]
        for number in valid_numbers:
            patent = Patent(
                patent_number=number,
                title="Test",
            )
            assert patent.patent_number == number

    def test_patent_number_validator_rejects_too_short(self):
        """Test patent_number validator rejects numbers too short."""
        with pytest.raises(ValidationError) as exc_info:
            Patent(
                patent_number="12345",  # Only 5 alphanumeric characters
                title="Test",
            )
        assert "Patent number too short" in str(exc_info.value)

    def test_patent_number_validator_strips_non_alphanumeric(self):
        """Test patent_number validator strips non-alphanumeric for validation."""
        # US-10,123,456-B2 has 12 alphanumeric chars -> valid
        patent = Patent(
            patent_number="US-10,123,456-B2",
            title="Test",
        )
        assert patent.patent_number == "US-10,123,456-B2"  # Preserved as-is

    def test_inventors_validator_rejects_empty_list(self):
        """Test inventors validator rejects explicitly empty list."""
        with pytest.raises(ValidationError) as exc_info:
            Patent(
                patent_number="US12345678",
                title="Test",
                inventors=[],  # Explicitly empty
            )
        assert "Inventors list cannot be empty" in str(exc_info.value)

    def test_inventors_validator_accepts_populated_list(self):
        """Test inventors validator accepts non-empty list."""
        patent = Patent(
            patent_number="US12345678",
            title="Test",
            inventors=["John Doe"],
        )
        assert len(patent.inventors) == 1
        assert patent.inventors[0] == "John Doe"

    def test_patent_with_dates(self):
        """Test patent with all date fields."""
        patent = Patent(
            patent_number="US12345678",
            title="Test",
            filing_date=date(2019, 3, 1),
            grant_date=date(2021, 9, 15),
            publication_date=date(2020, 9, 1),
        )
        assert patent.filing_date == date(2019, 3, 1)
        assert patent.grant_date == date(2021, 9, 15)
        assert patent.publication_date == date(2020, 9, 1)

    def test_patent_with_sbir_award_link(self):
        """Test patent linked to SBIR award."""
        patent = Patent(
            patent_number="US12345678",
            title="SBIR-funded Innovation",
            sbir_award_id="SBIR-2020-001",
        )
        assert patent.sbir_award_id == "SBIR-2020-001"

    def test_patent_with_related_patents(self):
        """Test patent with related patents."""
        patent = Patent(
            patent_number="US12345678",
            title="Test",
            related_patents=["US11111111", "US22222222", "US33333333"],
        )
        assert len(patent.related_patents) == 3
        assert "US11111111" in patent.related_patents


class TestRawPatentModel:
    """Tests for RawPatent model."""

    def test_raw_patent_all_none(self):
        """Test RawPatent can be created with all None values."""
        raw = RawPatent()
        assert raw.patent_number is None
        assert raw.title is None
        assert raw.abstract is None
        assert raw.filing_date is None
        assert raw.inventors is None

    def test_raw_patent_with_string_dates(self):
        """Test RawPatent accepts string dates."""
        raw = RawPatent(
            patent_number="US12345678",
            title="Raw Patent",
            filing_date="2020-01-15",
            grant_date="2022-06-20",
            publication_date="2021-07-15",
        )
        assert raw.filing_date == "2020-01-15"
        assert raw.grant_date == "2022-06-20"
        assert raw.publication_date == "2021-07-15"

    def test_raw_patent_partial(self):
        """Test RawPatent with some fields."""
        raw = RawPatent(
            patent_number="US87654321",
            title="Partial Data",
            inventors=["Jane Doe"],
            assignee="Test Corp",
        )
        assert raw.patent_number == "US87654321"
        assert raw.title == "Partial Data"
        assert raw.inventors == ["Jane Doe"]
        assert raw.assignee == "Test Corp"
        assert raw.filing_date is None


class TestPatentCitationModel:
    """Tests for PatentCitation model."""

    def test_valid_patent_citation(self):
        """Test creating a valid patent citation."""
        citation = PatentCitation(
            citing_patent="US10123456",
            cited_patent="US9876543",
            citation_type="backward",
            citation_date=date(2022, 5, 10),
        )
        assert citation.citing_patent == "US10123456"
        assert citation.cited_patent == "US9876543"
        assert citation.citation_type == "backward"
        assert citation.citation_date == date(2022, 5, 10)

    def test_patent_citation_minimal(self):
        """Test patent citation with only required fields."""
        citation = PatentCitation(
            citing_patent="US11111111",
            cited_patent="US22222222",
            citation_type="forward",
        )
        assert citation.citing_patent == "US11111111"
        assert citation.cited_patent == "US22222222"
        assert citation.citation_type == "forward"
        assert citation.citation_date is None

    def test_patent_citation_types(self):
        """Test patent citation with different citation types."""
        for cit_type in ["backward", "forward", "self-citation", "examiner"]:
            citation = PatentCitation(
                citing_patent="US10000000",
                cited_patent="US20000000",
                citation_type=cit_type,
            )
            assert citation.citation_type == cit_type

    def test_patent_citation_date_parsing(self):
        """Test patent citation accepts date strings."""
        citation = PatentCitation(
            citing_patent="US10000000",
            cited_patent="US20000000",
            citation_type="backward",
            citation_date="2023-03-15",
        )
        assert citation.citation_date == date(2023, 3, 15)
