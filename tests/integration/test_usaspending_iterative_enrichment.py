"""Integration tests for USAspending iterative enrichment.

Tests the full iterative enrichment cycle including:
- Freshness metadata tracking
- Delta detection
- Resume flows
- API client behavior with fixtures
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest


pytestmark = pytest.mark.integration

from src.enrichers.usaspending import USAspendingAPIClient
from src.models.enrichment import EnrichmentFreshnessRecord, EnrichmentStatus
from src.utils.enrichment_checkpoints import CheckpointStore
from src.utils.enrichment_freshness import FreshnessStore


@pytest.fixture
def tmp_freshness_store(tmp_path):
    """Create temporary freshness store for testing."""
    return FreshnessStore(parquet_path=tmp_path / "freshness.parquet")


@pytest.fixture
def tmp_checkpoint_store(tmp_path):
    """Create temporary checkpoint store for testing."""
    return CheckpointStore(parquet_path=tmp_path / "checkpoints.parquet")


@pytest.fixture
def sample_awards_df():
    """Sample awards DataFrame for testing."""
    return pd.DataFrame(
        {
            "award_id": ["AWARD-001", "AWARD-002", "AWARD-003"],
            "UEI": ["UEI123456789", "UEI987654321", None],
            "DUNS": ["123456789", None, "987654321"],
            "CAGE": ["1A2B3", None, "4C5D6"],
            "contract": ["CONTRACT-001", None, None],
        }
    )


@pytest.fixture
def mock_usaspending_api_client():
    """Mock USAspending API client with fixtures."""
    with patch("src.enrichers.usaspending.USAspendingAPIClient") as mock_client_class:
        mock_client = MagicMock(spec=USAspendingAPIClient)
        mock_client_class.return_value = mock_client

        # Setup default responses
        def make_recipient_response(uei: str, naics: str = "541511"):
            return {
                "recipient_id": "12345",
                "recipient_name": f"Company for {uei}",
                "recipient_uei": uei,
                "naics_code": naics,
                "action_date": "2024-01-15",
                "modification_number": "A00001",
            }

        async def mock_enrich_award(**kwargs):
            kwargs.get("award_id", "UNKNOWN")
            uei = kwargs.get("uei")

            if not uei:
                return {
                    "success": False,
                    "error": "No UEI provided",
                    "payload_hash": None,
                    "delta_detected": True,
                }

            # Check freshness record for delta detection
            freshness_record = kwargs.get("freshness_record")
            payload = make_recipient_response(uei)

            # Compute hash
            import hashlib
            import json

            payload_str = json.dumps(payload, sort_keys=True)
            new_hash = hashlib.sha256(payload_str.encode()).hexdigest()

            delta_detected = True
            if freshness_record and freshness_record.payload_hash:
                delta_detected = freshness_record.payload_hash != new_hash

            return {
                "success": True,
                "payload": payload,
                "payload_hash": new_hash,
                "delta_detected": delta_detected,
                "metadata": {
                    "modification_number": "A00001",
                    "action_date": "2024-01-15",
                },
            }

        mock_client.enrich_award = AsyncMock(side_effect=mock_enrich_award)
        mock_client.get_recipient_by_uei = AsyncMock(
            side_effect=lambda uei: make_recipient_response(uei)
        )
        mock_client.get_recipient_by_duns = AsyncMock(
            side_effect=lambda duns: make_recipient_response(f"UEI{duns}")
        )
        mock_client.get_recipient_by_cage = AsyncMock(
            side_effect=lambda cage: make_recipient_response(f"UEI_{cage}")
        )

        yield mock_client


class TestFreshnessTrackingCycle:
    """Test full freshness tracking cycle."""

    @pytest.mark.asyncio
    async def test_fresh_award_not_refreshed(
        self, tmp_freshness_store, mock_usaspending_api_client
    ):
        """Test that fresh awards are not refreshed."""
        # Create a fresh record (within SLA)
        fresh_record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=datetime.now(),  # Just refreshed
            payload_hash="existing_hash",
            status=EnrichmentStatus.SUCCESS,
        )
        tmp_freshness_store.save_record(fresh_record)

        # Get stale records (SLA = 1 day)
        stale = tmp_freshness_store.get_stale_records("usaspending", sla_days=1)
        stale_ids = {r.award_id for r in stale}

        assert "AWARD-001" not in stale_ids

    @pytest.mark.asyncio
    async def test_stale_award_refreshed(
        self, tmp_freshness_store, mock_usaspending_api_client, sample_awards_df
    ):
        """Test that stale awards are refreshed."""
        # Create a stale record
        stale_record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now() - timedelta(days=2),
            last_success_at=datetime.now() - timedelta(days=2),  # 2 days old
            payload_hash="old_hash",
            status=EnrichmentStatus.SUCCESS,
        )
        tmp_freshness_store.save_record(stale_record)

        # Get stale records
        stale = tmp_freshness_store.get_stale_records("usaspending", sla_days=1)
        stale_ids = {r.award_id for r in stale}

        assert "AWARD-001" in stale_ids

        # Simulate refresh
        award_row = sample_awards_df[sample_awards_df["award_id"] == "AWARD-001"].iloc[0]
        freshness_record = tmp_freshness_store.get_record("AWARD-001", "usaspending")

        result = await mock_usaspending_api_client.enrich_award(
            award_id="AWARD-001",
            uei=award_row["UEI"],
            freshness_record=freshness_record,
        )

        assert result["success"] is True
        assert result["delta_detected"] is True  # Hash changed

        # Update freshness record
        from src.utils.enrichment_freshness import update_freshness_ledger

        update_freshness_ledger(
            store=tmp_freshness_store,
            award_id="AWARD-001",
            source="usaspending",
            success=result["success"],
            payload_hash=result["payload_hash"],
            metadata=result.get("metadata", {}),
        )

        # Verify record updated
        updated = tmp_freshness_store.get_record("AWARD-001", "usaspending")
        assert updated.payload_hash == result["payload_hash"]
        assert updated.status == EnrichmentStatus.SUCCESS


class TestDeltaDetection:
    """Test delta detection functionality."""

    @pytest.mark.asyncio
    async def test_delta_detected_when_hash_changes(
        self, tmp_freshness_store, mock_usaspending_api_client
    ):
        """Test that delta is detected when payload hash changes."""
        # Create record with old hash
        old_record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=datetime.now(),
            payload_hash="old_hash",
            status=EnrichmentStatus.SUCCESS,
        )
        tmp_freshness_store.save_record(old_record)

        # Enrich with new data (mock returns different hash)
        result = await mock_usaspending_api_client.enrich_award(
            award_id="AWARD-001",
            uei="UEI123456789",
            freshness_record=old_record,
        )

        assert result["success"] is True
        assert result["delta_detected"] is True
        assert result["payload_hash"] != "old_hash"

    @pytest.mark.asyncio
    async def test_no_delta_when_hash_unchanged(
        self, tmp_freshness_store, mock_usaspending_api_client
    ):
        """Test that no delta is detected when hash is unchanged."""
        # Create record and enrich to get hash
        result1 = await mock_usaspending_api_client.enrich_award(
            award_id="AWARD-001",
            uei="UEI123456789",
        )

        # Save the hash
        from src.utils.enrichment_freshness import update_freshness_ledger

        update_freshness_ledger(
            store=tmp_freshness_store,
            award_id="AWARD-001",
            source="usaspending",
            success=True,
            payload_hash=result1["payload_hash"],
        )

        # Get the saved record
        saved_record = tmp_freshness_store.get_record("AWARD-001", "usaspending")

        # Enrich again (mock returns same hash)
        result2 = await mock_usaspending_api_client.enrich_award(
            award_id="AWARD-001",
            uei="UEI123456789",
            freshness_record=saved_record,
        )

        assert result2["success"] is True
        assert result2["delta_detected"] is False  # Hash unchanged


class TestResumeFlow:
    """Test checkpoint and resume functionality."""

    def test_checkpoint_save_and_load(self, tmp_checkpoint_store):
        """Test saving and loading checkpoints."""
        from src.utils.enrichment_checkpoints import EnrichmentCheckpoint

        checkpoint = EnrichmentCheckpoint(
            partition_id="partition_001",
            source="usaspending",
            last_processed_award_id="AWARD-050",
            last_success_timestamp=datetime.now(),
            records_processed=50,
            records_failed=2,
            records_total=100,
            checkpoint_timestamp=datetime.now(),
            metadata={"batch": 1},
        )

        tmp_checkpoint_store.save_checkpoint(checkpoint)

        loaded = tmp_checkpoint_store.load_checkpoint("partition_001", "usaspending")

        assert loaded is not None
        assert loaded.last_processed_award_id == "AWARD-050"
        assert loaded.records_processed == 50

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="EnrichmentCheckpoint API changed")
    async def test_resume_after_interruption(
        self, tmp_checkpoint_store, tmp_freshness_store, mock_usaspending_api_client
    ):
        """Test resuming refresh after interruption."""
        from src.utils.enrichment_checkpoints import EnrichmentCheckpoint

        # Simulate interrupted run - checkpoint saved at AWARD-050
        checkpoint = EnrichmentCheckpoint(
            partition_id="partition_001",
            source="usaspending",
            last_processed_award_id="AWARD-050",
            last_success_timestamp=datetime.now() - timedelta(hours=1),
            records_processed=50,
            records_failed=2,
            records_total=100,
            checkpoint_timestamp=datetime.now() - timedelta(hours=1),
        )
        tmp_checkpoint_store.save_checkpoint(checkpoint)

        # Resume from checkpoint
        loaded_checkpoint = tmp_checkpoint_store.load_checkpoint("partition_001", "usaspending")

        assert loaded_checkpoint is not None
        assert loaded_checkpoint.last_processed_award_id == "AWARD-050"

        # In a real scenario, we'd skip awards up to AWARD-050
        # For this test, just verify checkpoint is usable
        assert loaded_checkpoint.records_processed == 50
        assert loaded_checkpoint.records_total == 100


class TestFullIterativeCycle:
    """Test complete iterative enrichment cycle."""

    @pytest.mark.asyncio
    async def test_full_cycle_simulation(
        self, tmp_freshness_store, mock_usaspending_api_client, sample_awards_df
    ):
        """Simulate a full iterative enrichment cycle."""
        # Step 1: Identify stale awards
        # Create some stale records
        now = datetime.now()
        for i, award_id in enumerate(["AWARD-001", "AWARD-002"]):
            stale_record = EnrichmentFreshnessRecord(
                award_id=award_id,
                source="usaspending",
                last_attempt_at=now - timedelta(days=2),
                last_success_at=now - timedelta(days=2),
                payload_hash=f"old_hash_{i}",
                status=EnrichmentStatus.SUCCESS,
            )
            tmp_freshness_store.save_record(stale_record)

        # Step 2: Get stale awards
        stale = tmp_freshness_store.get_stale_records("usaspending", sla_days=1)
        assert len(stale) == 2

        # Step 3: Refresh stale awards
        from src.utils.enrichment_freshness import update_freshness_ledger

        for stale_record in stale:
            award_row = sample_awards_df[
                sample_awards_df["award_id"] == stale_record.award_id
            ].iloc[0]

            result = await mock_usaspending_api_client.enrich_award(
                award_id=stale_record.award_id,
                uei=award_row["UEI"],
                freshness_record=stale_record,
            )

            update_freshness_ledger(
                store=tmp_freshness_store,
                award_id=stale_record.award_id,
                source="usaspending",
                success=result["success"],
                payload_hash=result["payload_hash"],
            )

        # Step 4: Verify all are fresh now
        stale_after = tmp_freshness_store.get_stale_records("usaspending", sla_days=1)
        assert len(stale_after) == 0  # All should be fresh

        # Step 5: Verify records updated
        for award_id in ["AWARD-001", "AWARD-002"]:
            record = tmp_freshness_store.get_record(award_id, "usaspending")
            assert record is not None
            assert record.status == EnrichmentStatus.SUCCESS
            assert record.last_success_at is not None
            # Should be recent (within last minute)
            assert (datetime.now() - record.last_success_at).total_seconds() < 60
