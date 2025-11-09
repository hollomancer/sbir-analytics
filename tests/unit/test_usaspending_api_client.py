"""Unit tests for USAspending API client."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = pytest.mark.fast
from httpx import HTTPStatusError, TimeoutException

from src.enrichers.usaspending.client import USAspendingAPIClient
from src.exceptions import APIError as USAspendingAPIError
from src.exceptions import RateLimitError as USAspendingRateLimitError
from src.models.enrichment import EnrichmentFreshnessRecord, EnrichmentStatus


@pytest.fixture
def mock_config():
    """Mock configuration for USAspending API client."""
    return {
        "base_url": "https://api.usaspending.gov/api/v2",
        "timeout_seconds": 30,
        "retry_attempts": 3,
        "retry_backoff_seconds": 2,
        "rate_limit_per_minute": 120,
    }


@pytest.fixture
def api_client(mock_config, tmp_path):
    """Create USAspending API client for testing."""
    with patch("src.enrichers.usaspending.client.get_config") as mock_get_config:
        mock_cfg = MagicMock()
        mock_cfg.enrichment_refresh.usaspending.model_dump.return_value = {
            "timeout_seconds": 30,
            "retry_attempts": 3,
            "retry_backoff_seconds": 2.0,
            "retry_backoff_multiplier": 2.0,
            "rate_limit_per_minute": 120,
            "state_file": str(tmp_path / "state.json"),
        }
        mock_cfg.enrichment.usaspending_api = {
            "base_url": "https://api.usaspending.gov/api/v2",
        }
        mock_get_config.return_value = mock_cfg

        client = USAspendingAPIClient()
        client.state_file = tmp_path / "state.json"
        return client


@pytest.fixture
def sample_recipient_response():
    """Sample USAspending recipient API response."""
    return {
        "recipient_id": "12345",
        "recipient_name": "Test Company Inc.",
        "recipient_uei": "ABC123DEF456",  # pragma: allowlist secret
        "recipient_duns": "123456789",
        "recipient_cage": "1A2B3",
        "naics_code": "541511",
        "action_date": "2024-01-15",
        "modification_number": "A00001",
    }


@pytest.fixture
def sample_award_response():
    """Sample USAspending award API response."""
    return {
        "award_id": "AWARD-001",
        "piid": "CONTRACT-123",
        "recipient_name": "Test Company Inc.",
        "naics_code": "541511",
        "action_date": "2024-01-15",
        "modification_number": "A00001",
        "last_modified_date": "2024-01-20",
    }


class TestUSAspendingAPIClientInitialization:
    """Test client initialization."""

    def test_client_initializes_with_config(self, api_client):
        """Test client initializes with correct configuration."""
        assert api_client.base_url == "https://api.usaspending.gov/api/v2"
        assert api_client.timeout == 30
        assert api_client.retry_attempts == 3
        assert api_client.rate_limit_per_minute == 120

    def test_rate_limiter_starts_empty(self, api_client):
        """Test rate limiter starts with empty request times."""
        assert len(api_client.request_times) == 0


class TestPayloadHashing:
    """Test payload hash computation."""

    def test_compute_payload_hash_is_deterministic(self, api_client, sample_recipient_response):
        """Test payload hash is deterministic (same input = same hash)."""
        hash1 = api_client._compute_payload_hash(sample_recipient_response)
        hash2 = api_client._compute_payload_hash(sample_recipient_response)
        assert hash1 == hash2

    def test_compute_payload_hash_detects_changes(self, api_client, sample_recipient_response):
        """Test payload hash changes when data changes."""
        hash1 = api_client._compute_payload_hash(sample_recipient_response)
        sample_recipient_response["naics_code"] = "541512"
        hash2 = api_client._compute_payload_hash(sample_recipient_response)
        assert hash1 != hash2

    def test_compute_payload_hash_handles_sorting(self, api_client):
        """Test payload hash ignores key order."""
        payload1 = {"a": 1, "b": 2, "c": 3}
        payload2 = {"c": 3, "b": 2, "a": 1}
        hash1 = api_client._compute_payload_hash(payload1)
        hash2 = api_client._compute_payload_hash(payload2)
        assert hash1 == hash2


class TestDeltaMetadataExtraction:
    """Test delta identifier extraction."""

    def test_extract_delta_metadata_captures_modification_number(
        self, api_client, sample_recipient_response
    ):
        """Test extraction of modification_number."""
        metadata = api_client._extract_delta_metadata(sample_recipient_response)
        assert metadata["modification_number"] == "A00001"
        assert metadata["action_date"] == "2024-01-15"

    def test_extract_delta_metadata_captures_piid(self, api_client, sample_award_response):
        """Test extraction of PIID from award response."""
        metadata = api_client._extract_delta_metadata(sample_award_response)
        assert metadata["piid"] == "CONTRACT-123"
        assert metadata["last_modified_date"] == "2024-01-20"

    def test_extract_delta_metadata_handles_missing_fields(self, api_client):
        """Test extraction handles missing fields gracefully."""
        payload = {"recipient_name": "Test Company"}
        metadata = api_client._extract_delta_metadata(payload)
        assert "modification_number" not in metadata
        assert "action_date" not in metadata


class TestRateLimiting:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limiter_waits_when_limit_exceeded(self, api_client):
        """Test rate limiter waits when limit is exceeded."""
        # Fill request times to exceed limit
        now = datetime.now()
        api_client.request_times = [now] * 120  # Exactly at limit

        # Mock asyncio.sleep to verify it's called
        with patch("asyncio.sleep") as mock_sleep:
            await api_client._wait_for_rate_limit()
            # Should wait since we're at the limit
            assert mock_sleep.called

    @pytest.mark.asyncio
    async def test_rate_limiter_doesnt_wait_below_limit(self, api_client):
        """Test rate limiter doesn't wait when below limit."""
        api_client.request_times = []  # No previous requests

        with patch("asyncio.sleep") as mock_sleep:
            await api_client._wait_for_rate_limit()
            # Should not wait
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limiter_removes_old_requests(self, api_client):
        """Test rate limiter removes requests older than 1 minute."""
        now = datetime.now()
        from datetime import timedelta

        # Add old and recent requests
        api_client.request_times = [
            now - timedelta(seconds=70),  # Old (70 seconds ago)
            now - timedelta(seconds=30),  # Recent (30 seconds ago)
        ]

        await api_client._wait_for_rate_limit()

        # Should only have recent request plus the new one
        assert len(api_client.request_times) >= 2
        # All requests should be recent
        for req_time in api_client.request_times:
            assert (now - req_time).total_seconds() < 61


class TestAPICalls:
    """Test API call methods."""

    @pytest.mark.asyncio
    async def test_get_recipient_by_uei_success(self, api_client, sample_recipient_response):
        """Test successful recipient lookup by UEI."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = sample_recipient_response

            result = await api_client.get_recipient_by_uei(
                "ABC123DEF456"  # pragma: allowlist secret
            )

            assert result == sample_recipient_response
            mock_request.assert_called_once()
            # Check that endpoint was called with recipient path
            call_args = mock_request.call_args[0]
            assert len(call_args) >= 2
            assert call_args[1].endswith("ABC123DEF456/") or "recipients" in call_args[1].lower()

    @pytest.mark.asyncio
    async def test_get_recipient_by_uei_not_found(self, api_client):
        """Test recipient not found returns None."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = USAspendingAPIError("HTTP 404: Not found")

            result = await api_client.get_recipient_by_uei("INVALID")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_recipient_by_duns_success(self, api_client, sample_recipient_response):
        """Test successful recipient lookup by DUNS."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"results": [sample_recipient_response]}

            result = await api_client.get_recipient_by_duns("123456789")

            assert result == sample_recipient_response

    @pytest.mark.asyncio
    async def test_get_recipient_by_cage_success(self, api_client, sample_recipient_response):
        """Test successful recipient lookup by CAGE."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"results": [sample_recipient_response]}

            result = await api_client.get_recipient_by_cage("1A2B3")

            assert result == sample_recipient_response

    @pytest.mark.asyncio
    async def test_get_award_by_piid_success(self, api_client, sample_award_response):
        """Test successful award lookup by PIID."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = sample_award_response

            result = await api_client.get_award_by_piid("CONTRACT-123")

            assert result == sample_award_response


class TestRetryLogic:
    """Test retry and error handling."""

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, api_client):
        """Test retry on timeout exception."""
        # Mock the rate limiter to avoid async sleep delays in tests
        api_client._wait_for_rate_limit = AsyncMock()

        # Mock httpx.AsyncClient to avoid actual HTTP calls
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_client
            mock_context.__aexit__.return_value = None
            mock_client_class.return_value = mock_context

            # Setup client to eventually succeed after timeouts
            mock_response = AsyncMock()
            mock_response.status_code = 200
            # httpx's .json() is a sync method, not async
            mock_response.json = MagicMock(return_value={"success": True})
            mock_response.raise_for_status = MagicMock()

            # First calls timeout, last succeeds (tenacity will retry)
            # The retry decorator stops after 3 attempts, so we need success within 3 attempts
            mock_client.get.side_effect = [
                TimeoutException("Request timeout"),
                TimeoutException("Request timeout"),
                mock_response,  # Success on 3rd attempt
            ]

            # Should eventually succeed after retries (tenacity will handle retries)
            # The retry decorator will retry on TimeoutException up to 3 attempts
            # With our fix, TimeoutException propagates so retry decorator can catch it
            # After 2 timeouts, the 3rd attempt should succeed
            response = await api_client._make_request("GET", "/test/")
            assert response["success"] is True
            # Verify multiple attempts were made (retry happened)
            assert mock_client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limit_error_raised(self, api_client):
        """Test rate limit error is properly raised."""
        # Mock the rate limiter to avoid async sleep delays in tests
        api_client._wait_for_rate_limit = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_client
            mock_context.__aexit__.return_value = None
            mock_client_class.return_value = mock_context

            response_obj = AsyncMock()
            response_obj.status_code = 429
            response_obj.text = "Rate limit exceeded"
            response_obj.raise_for_status.side_effect = HTTPStatusError(
                "429 Rate Limit", request=MagicMock(), response=response_obj
            )
            mock_client.get.return_value = response_obj

            with pytest.raises(USAspendingRateLimitError):
                await api_client._make_request("GET", "/test/")


class TestEnrichAward:
    """Test enrich_award method."""

    @pytest.mark.asyncio
    async def test_enrich_award_success_with_uei(self, api_client, sample_recipient_response):
        """Test successful enrichment with UEI."""
        with patch.object(api_client, "get_recipient_by_uei", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_recipient_response

            result = await api_client.enrich_award(
                award_id="AWARD-001",
                uei="ABC123DEF456",  # pragma: allowlist secret
            )

            assert result["success"] is True
            assert result["payload"] == sample_recipient_response
            assert result["payload_hash"] is not None
            assert result["delta_detected"] is True

    @pytest.mark.asyncio
    async def test_enrich_award_delta_detection(self, api_client, sample_recipient_response):
        """Test delta detection when freshness record exists."""
        # Create freshness record with existing hash
        existing_hash = api_client._compute_payload_hash(sample_recipient_response)
        freshness_record = EnrichmentFreshnessRecord(
            award_id="AWARD-001",
            source="usaspending",
            last_attempt_at=datetime.now(),
            last_success_at=datetime.now(),
            payload_hash=existing_hash,
            status=EnrichmentStatus.SUCCESS,
        )

        with patch.object(api_client, "get_recipient_by_uei", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_recipient_response

            result = await api_client.enrich_award(
                award_id="AWARD-001",
                uei="ABC123DEF456",  # pragma: allowlist secret
                freshness_record=freshness_record,
            )

            # Hash matches, so no delta detected
            assert result["success"] is True
            assert result["delta_detected"] is False

    @pytest.mark.asyncio
    async def test_enrich_award_fallback_to_duns(self, api_client, sample_recipient_response):
        """Test enrichment falls back to DUNS when UEI fails."""
        with patch.object(api_client, "get_recipient_by_uei", new_callable=AsyncMock) as mock_uei:
            with patch.object(
                api_client, "get_recipient_by_duns", new_callable=AsyncMock
            ) as mock_duns:
                mock_uei.return_value = None  # UEI lookup fails
                mock_duns.return_value = sample_recipient_response

                result = await api_client.enrich_award(
                    award_id="AWARD-001",
                    uei=None,  # When uei is None, get_recipient_by_uei should not be called
                    duns="123456789",
                )

                assert result["success"] is True
                # When uei is None, get_recipient_by_uei is not called (due to `if uei:` check)
                mock_uei.assert_not_called()
                mock_duns.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_award_handles_no_data_found(self, api_client):
        """Test enrichment handles case where no data is found."""
        with patch.object(api_client, "get_recipient_by_uei", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await api_client.enrich_award(
                award_id="AWARD-001",
                uei="INVALID",
            )

            assert result["success"] is False
            assert "No recipient/award data found" in result["error"]

    @pytest.mark.asyncio
    async def test_enrich_award_handles_api_error(self, api_client):
        """Test enrichment handles API errors gracefully."""
        with patch.object(api_client, "get_recipient_by_uei", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = USAspendingAPIError("API error occurred")

            result = await api_client.enrich_award(
                award_id="AWARD-001",
                uei="ABC123DEF456",  # pragma: allowlist secret
            )

            assert result["success"] is False
            assert "API error occurred" in result["error"]


class TestStateManagement:
    """Test state file management."""

    def test_load_state_returns_empty_dict_when_missing(self, api_client):
        """Test loading state when file doesn't exist returns empty dict."""
        state = api_client.load_state()
        assert state == {}

    def test_save_and_load_state(self, api_client):
        """Test saving and loading state."""
        test_state = {
            "last_fetch": "2024-01-15T10:00:00",
            "cursor": "abc123",
        }

        api_client.save_state(test_state)
        loaded_state = api_client.load_state()

        assert loaded_state == test_state

    def test_save_state_creates_directory(self, api_client, tmp_path):
        """Test save_state creates parent directory if needed."""
        api_client.state_file = tmp_path / "nested" / "deep" / "state.json"
        test_state = {"test": "data"}

        api_client.save_state(test_state)

        assert api_client.state_file.exists()
