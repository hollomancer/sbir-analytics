"""Tests for USAspending API client."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.enrichers.usaspending.client import (
    USAspendingAPIClient,
    USAspendingAPIError,
    USAspendingRateLimitError,
)
from src.exceptions import APIError, ConfigurationError, RateLimitError
from src.models.enrichment import EnrichmentFreshnessRecord


# ==================== Fixtures ====================


pytestmark = pytest.mark.fast

from tests.utils.config_mocks import create_mock_pipeline_config


@pytest.fixture
def mock_config(tmp_path):
    """Mock configuration using consolidated utility."""
    config = create_mock_pipeline_config()
    # Set enrichment_refresh.usaspending state_file
    if hasattr(config, "enrichment_refresh") and hasattr(config.enrichment_refresh, "usaspending"):
        config.enrichment_refresh.usaspending.state_file = str(tmp_path / "test_state.json")
    # Ensure enrichment.usaspending_api is set
    if hasattr(config, "enrichment"):
        config.enrichment.usaspending_api = {
            "base_url": "https://api.usaspending.gov/api/v2",
        }
    return config


@pytest.fixture
def mock_http_client():
    """Mock httpx.AsyncClient for testing."""
    mock_client = AsyncMock()
    mock_client.aclose = AsyncMock()
    return mock_client


@pytest.fixture
def client(mock_config, tmp_path, mock_http_client):
    """USAspendingAPIClient instance with test config and mock HTTP client."""
    with patch("src.enrichers.usaspending.client.get_config", return_value=mock_config):
        # Override state file to use tmp_path
        test_config = mock_config.enrichment_refresh.usaspending.model_dump()
        test_config["state_file"] = str(tmp_path / "test_state.json")
        test_config["usaspending_api"] = {
            "base_url": "https://api.usaspending.gov/api/v2",
        }
        return USAspendingAPIClient(config=test_config, http_client=mock_http_client)


@pytest.fixture
def sample_recipient_data():
    """Sample recipient API response."""
    return {
        "recipient_uei": "UEI123456789",
        "recipient_name": "Acme Corp",
        "recipient_duns": "123456789",
        "cage_code": "ABC12",
        "total_amount": 5000000,
    }


@pytest.fixture
def sample_award_data():
    """Sample award data fixture - uses consolidated utility."""
    from tests.utils.fixtures import create_sample_award_data

    return create_sample_award_data()


@pytest.fixture
def freshness_record():
    """Sample freshness record."""
    return EnrichmentFreshnessRecord(
        award_id="AWD001",
        source="usaspending",
        last_attempt_at=datetime(2023, 1, 1, 12, 0, 0),
        payload_hash="abc123",
        metadata={"modification_number": "0"},
    )


# ==================== Backward Compatibility Tests ====================


class TestBackwardCompatibility:
    """Tests for backward compatibility aliases."""

    def test_usaspending_api_error_alias(self):
        """Test USAspendingAPIError is an alias for APIError."""
        assert USAspendingAPIError is APIError

    def test_usaspending_rate_limit_error_alias(self):
        """Test USAspendingRateLimitError is an alias for RateLimitError."""
        assert USAspendingRateLimitError is RateLimitError


# ==================== Initialization Tests ====================


class TestUSAspendingAPIClientInitialization:
    """Tests for USAspendingAPIClient initialization."""

    @patch("src.enrichers.usaspending.client.get_config")
    def test_initialization_from_get_config(self, mock_get_config, mock_config):
        """Test initialization loads config from get_config()."""
        mock_get_config.return_value = mock_config

        client = USAspendingAPIClient()

        assert client.base_url == "https://api.usaspending.gov/api/v2"
        assert client.timeout == 30
        assert client.retry_attempts == 3
        assert client.retry_backoff == 2.0
        assert client.retry_multiplier == 2.0
        assert client.rate_limit_per_minute == 120
        assert client.request_times == []

    def test_initialization_with_custom_config(self):
        """Test initialization with custom config override."""
        custom_config = {
            "timeout_seconds": 60,
            "retry_attempts": 5,
            "retry_backoff_seconds": 1.0,
            "retry_backoff_multiplier": 1.5,
            "rate_limit_per_minute": 60,
            "state_file": "custom/state.json",
            "usaspending_api": {
                "base_url": "https://custom.api.url",
            },
        }

        client = USAspendingAPIClient(config=custom_config)

        assert client.base_url == "https://custom.api.url"
        assert client.timeout == 60
        assert client.retry_attempts == 5
        assert client.retry_backoff == 1.0
        assert client.retry_multiplier == 1.5
        assert client.rate_limit_per_minute == 60

    def test_state_file_parent_created(self, tmp_path):
        """Test state file parent directory is created."""
        state_path = tmp_path / "nested" / "dirs" / "state.json"
        config = {
            "state_file": str(state_path),
            "usaspending_api": {"base_url": "https://api.test.com"},
        }

        client = USAspendingAPIClient(config=config)

        assert state_path.parent.exists()
        assert client.state_file == state_path


# ==================== Rate Limiting Tests ====================


class TestRateLimiting:
    """Tests for rate limiting logic."""

    @pytest.mark.asyncio
    async def test_wait_for_rate_limit_under_limit(self, client):
        """Test rate limiting when under limit."""
        # Add some requests but stay under limit
        for _ in range(50):
            client.request_times.append(datetime.now())

        # Should not wait
        await client._wait_for_rate_limit()

        # New request should be added
        assert len(client.request_times) == 51

    @pytest.mark.asyncio
    async def test_wait_for_rate_limit_cleans_old_requests(self, client):
        """Test rate limiter cleans requests older than 1 minute."""
        # Add old requests
        old_time = datetime.now() - timedelta(seconds=70)
        for _ in range(50):
            client.request_times.append(old_time)

        # Add recent requests
        for _ in range(10):
            client.request_times.append(datetime.now())

        await client._wait_for_rate_limit()

        # Old requests should be cleaned, recent ones kept + new one
        assert len(client.request_times) == 11

    @pytest.mark.asyncio
    @patch("asyncio.sleep")
    async def test_wait_for_rate_limit_at_limit(self, mock_sleep, client):
        """Test rate limiting when at limit."""
        # Fill up to rate limit
        client.rate_limit_per_minute = 10
        base_time = datetime.now() - timedelta(seconds=30)
        for i in range(10):
            client.request_times.append(base_time + timedelta(seconds=i))

        await client._wait_for_rate_limit()

        # Should have waited
        mock_sleep.assert_called_once()
        # Wait time should be roughly 30+ seconds (to make oldest request 60s old)
        wait_time = mock_sleep.call_args[0][0]
        assert wait_time >= 29  # 60 - 30 - 1s buffer


# ==================== HTTP Request Tests ====================


class TestHTTPRequests:
    """Tests for HTTP request making."""

    @pytest.mark.asyncio
    async def test_make_request_get_success(self, client, mock_http_client, sample_recipient_data):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_recipient_data
        mock_response.raise_for_status = Mock()
        mock_http_client.get.return_value = mock_response

        result = await client._make_request("GET", "/recipients/UEI123")

        assert result == sample_recipient_data
        mock_http_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_post_success(self, client, mock_http_client, sample_recipient_data):
        """Test successful POST request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_recipient_data
        mock_response.raise_for_status = Mock()
        mock_http_client.post.return_value = mock_response

        result = await client._make_request("POST", "/search/", params={"test": "data"})

        assert result == sample_recipient_data
        mock_http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_unsupported_method(self, client):
        """Test unsupported HTTP method raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Unsupported HTTP method: PUT"):
            await client._make_request("PUT", "/test/")

    @pytest.mark.asyncio
    async def test_make_request_rate_limit_429(self, client, mock_http_client):
        """Test 429 rate limit error handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        error = httpx.HTTPStatusError("429", request=Mock(), response=mock_response)
        mock_http_client.get.side_effect = error

        with pytest.raises(RateLimitError, match="Rate limit exceeded"):
            await client._make_request("GET", "/test/")

    @pytest.mark.asyncio
    async def test_make_request_http_error_404(self, client, mock_http_client):
        """Test HTTP 404 error handling."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        error = httpx.HTTPStatusError("404", request=Mock(), response=mock_response)
        mock_http_client.get.side_effect = error

        with pytest.raises(APIError, match="HTTP 404"):
            await client._make_request("GET", "/test/")

    @pytest.mark.asyncio
    async def test_make_request_timeout(self, client, mock_http_client):
        """Test timeout error handling after retries."""
        mock_http_client.get.side_effect = httpx.TimeoutException("Timeout")

        with pytest.raises(APIError, match="Request timeout after retries"):
            await client._make_request("GET", "/test/")

    @pytest.mark.asyncio
    async def test_make_request_network_error(self, client, mock_http_client):
        """Test network error handling."""
        mock_http_client.get.side_effect = httpx.RequestError("Network error")

        with pytest.raises(APIError, match="Request error"):
            await client._make_request("GET", "/test/")

    @pytest.mark.asyncio
    async def test_make_request_with_custom_headers(self, client, mock_http_client):
        """Test request with custom headers."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.raise_for_status = Mock()
        mock_http_client.get.return_value = mock_response

        custom_headers = {"X-Custom-Header": "test-value"}
        await client._make_request("GET", "/test/", headers=custom_headers)

        call_kwargs = mock_http_client.get.call_args[1]
        assert call_kwargs["headers"]["X-Custom-Header"] == "test-value"


# ==================== Payload Hashing Tests ====================


class TestPayloadHashing:
    """Tests for payload hashing."""

    def test_compute_payload_hash_deterministic(self, client):
        """Test payload hash is deterministic."""
        payload = {"key1": "value1", "key2": "value2", "key3": 123}

        hash1 = client._compute_payload_hash(payload)
        hash2 = client._compute_payload_hash(payload)

        assert hash1 == hash2

    def test_compute_payload_hash_different_order(self, client):
        """Test hash is same regardless of key order."""
        payload1 = {"a": 1, "b": 2, "c": 3}
        payload2 = {"c": 3, "a": 1, "b": 2}

        hash1 = client._compute_payload_hash(payload1)
        hash2 = client._compute_payload_hash(payload2)

        assert hash1 == hash2

    def test_compute_payload_hash_different_values(self, client):
        """Test hash differs for different values."""
        payload1 = {"key": "value1"}
        payload2 = {"key": "value2"}

        hash1 = client._compute_payload_hash(payload1)
        hash2 = client._compute_payload_hash(payload2)

        assert hash1 != hash2

    def test_compute_payload_hash_nested_dicts(self, client):
        """Test hash works with nested dictionaries."""
        payload = {
            "outer": {"inner": {"deep": "value"}},
            "list": [1, 2, 3],
        }

        hash_value = client._compute_payload_hash(payload)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 hex length


# ==================== Delta Metadata Extraction Tests ====================


class TestDeltaMetadataExtraction:
    """Tests for delta metadata extraction."""

    def test_extract_delta_metadata_all_fields(self, client):
        """Test extraction with all delta fields."""
        payload = {
            "modification_number": "5",
            "action_date": "2023-01-15",
            "last_modified_date": "2023-01-20",
            "award_id": "AWD001",
            "piid": "PIID123",
            "other_field": "ignored",
        }

        metadata = client._extract_delta_metadata(payload)

        assert metadata["modification_number"] == "5"
        assert metadata["action_date"] == "2023-01-15"
        assert metadata["last_modified_date"] == "2023-01-20"
        assert metadata["award_id"] == "AWD001"
        assert metadata["piid"] == "PIID123"
        assert "other_field" not in metadata

    def test_extract_delta_metadata_partial_fields(self, client):
        """Test extraction with only some fields."""
        payload = {
            "modification_number": "3",
            "award_id": "AWD002",
        }

        metadata = client._extract_delta_metadata(payload)

        assert metadata["modification_number"] == "3"
        assert metadata["award_id"] == "AWD002"
        assert "action_date" not in metadata
        assert "piid" not in metadata

    def test_extract_delta_metadata_empty(self, client):
        """Test extraction with no delta fields."""
        payload = {"unrelated": "data"}

        metadata = client._extract_delta_metadata(payload)

        assert metadata == {}


# ==================== Recipient Lookup Tests ====================


class TestRecipientLookup:
    """Tests for recipient lookup methods."""

    @pytest.mark.asyncio
    async def test_get_recipient_by_uei_success(self, client, sample_recipient_data):
        """Test successful UEI lookup."""
        with patch.object(client, "_make_request", return_value=sample_recipient_data):
            result = await client.get_recipient_by_uei("UEI123456789")

        assert result == sample_recipient_data

    @pytest.mark.asyncio
    async def test_get_recipient_by_uei_not_found(self, client):
        """Test UEI lookup when not found."""
        error = APIError("HTTP 404: Not found", api_name="usaspending", endpoint="/test")
        with patch.object(client, "_make_request", side_effect=error):
            result = await client.get_recipient_by_uei("UNKNOWN")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_recipient_by_duns_success(self, client, sample_recipient_data):
        """Test successful DUNS lookup."""
        response = {"results": [sample_recipient_data]}
        with patch.object(client, "_make_request", return_value=response):
            result = await client.get_recipient_by_duns("123456789")

        assert result == sample_recipient_data

    @pytest.mark.asyncio
    async def test_get_recipient_by_duns_no_results(self, client):
        """Test DUNS lookup with no results."""
        response = {"results": []}
        with patch.object(client, "_make_request", return_value=response):
            result = await client.get_recipient_by_duns("999999999")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_recipient_by_duns_not_found(self, client):
        """Test DUNS lookup when not found."""
        error = APIError("Recipient not found", api_name="usaspending", endpoint="/test")
        with patch.object(client, "_make_request", side_effect=error):
            result = await client.get_recipient_by_duns("000000000")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_recipient_by_cage_success(self, client, sample_recipient_data):
        """Test successful CAGE lookup."""
        response = {"results": [sample_recipient_data]}
        with patch.object(client, "_make_request", return_value=response):
            result = await client.get_recipient_by_cage("ABC12")

        assert result == sample_recipient_data

    @pytest.mark.asyncio
    async def test_get_recipient_by_cage_no_results(self, client):
        """Test CAGE lookup with no results."""
        response = {"results": []}
        with patch.object(client, "_make_request", return_value=response):
            result = await client.get_recipient_by_cage("ZZZ99")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_recipient_by_cage_not_found(self, client):
        """Test CAGE lookup when not found."""
        error = APIError("Not found in database", api_name="usaspending", endpoint="/test")
        with patch.object(client, "_make_request", side_effect=error):
            result = await client.get_recipient_by_cage("XXX00")

        assert result is None


# ==================== Award Lookup Tests ====================


class TestAwardLookup:
    """Tests for award lookup methods."""

    @pytest.mark.asyncio
    async def test_get_award_by_piid_success(self, client, sample_award_data):
        """Test successful PIID lookup."""
        with patch.object(client, "_make_request", return_value=sample_award_data):
            result = await client.get_award_by_piid("PIID123")

        assert result == sample_award_data

    @pytest.mark.asyncio
    async def test_get_award_by_piid_not_found(self, client):
        """Test PIID lookup when not found."""
        error = APIError("HTTP 404: Award not found", api_name="usaspending", endpoint="/test")
        with patch.object(client, "_make_request", side_effect=error):
            result = await client.get_award_by_piid("UNKNOWN")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_award_by_piid_api_error(self, client):
        """Test PIID lookup with non-404 API error."""
        error = APIError("HTTP 500: Server error", api_name="usaspending", endpoint="/test")
        with patch.object(client, "_make_request", side_effect=error):
            with pytest.raises(APIError, match="Server error"):
                await client.get_award_by_piid("PIID123")


# ==================== Transaction Lookup Tests ====================


class TestTransactionLookup:
    """Tests for transaction lookup."""

    @pytest.mark.asyncio
    async def test_get_transactions_by_recipient_success(self, client):
        """Test successful transaction lookup."""
        transactions = [
            {"transaction_id": "TXN001", "amount": 100000},
            {"transaction_id": "TXN002", "amount": 150000},
        ]
        response = {"results": transactions}

        with patch.object(client, "_make_request", return_value=response):
            result = await client.get_transactions_by_recipient("UEI123456789")

        assert result == transactions

    @pytest.mark.asyncio
    async def test_get_transactions_by_recipient_with_date_range(self, client):
        """Test transaction lookup with date range."""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)
        transactions = [{"transaction_id": "TXN001"}]
        response = {"results": transactions}

        with patch.object(client, "_make_request", return_value=response) as mock_request:
            result = await client.get_transactions_by_recipient(
                "UEI123456789", date_range=(start_date, end_date)
            )

        assert result == transactions
        # Verify date range was passed in params
        call_args = mock_request.call_args
        params = call_args[1]["params"]
        assert "action_date__gte" in params
        assert "action_date__lte" in params

    @pytest.mark.asyncio
    async def test_get_transactions_by_recipient_api_error(self, client):
        """Test transaction lookup with API error."""
        error = APIError("Server error", api_name="usaspending", endpoint="/test")
        with patch.object(client, "_make_request", side_effect=error):
            result = await client.get_transactions_by_recipient("UEI123456789")

        # Should return empty list on error, not raise
        assert result == []


# ==================== Award Enrichment Tests ====================


class TestAwardEnrichment:
    """Tests for award enrichment with delta detection."""

    @pytest.mark.asyncio
    async def test_enrich_award_by_uei_success(self, client, sample_recipient_data):
        """Test successful enrichment by UEI."""
        with patch.object(client, "get_recipient_by_uei", return_value=sample_recipient_data):
            result = await client.enrich_award("AWD001", uei="UEI123456789")

        assert result["success"] is True
        assert result["payload"] == sample_recipient_data
        assert result["payload_hash"] is not None
        assert result["delta_detected"] is True
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_enrich_award_fallback_to_duns(self, client, sample_recipient_data):
        """Test enrichment falls back to DUNS when UEI fails."""
        with patch.object(client, "get_recipient_by_uei", return_value=None):
            with patch.object(client, "get_recipient_by_duns", return_value=sample_recipient_data):
                result = await client.enrich_award("AWD001", uei="UEI999", duns="123456789")

        assert result["success"] is True
        assert result["payload"] == sample_recipient_data

    @pytest.mark.asyncio
    async def test_enrich_award_fallback_to_cage(self, client, sample_recipient_data):
        """Test enrichment falls back to CAGE."""
        with patch.object(client, "get_recipient_by_uei", return_value=None):
            with patch.object(client, "get_recipient_by_duns", return_value=None):
                with patch.object(
                    client, "get_recipient_by_cage", return_value=sample_recipient_data
                ):
                    result = await client.enrich_award(
                        "AWD001", uei="UEI999", duns="999", cage="ABC12"
                    )

        assert result["success"] is True
        assert result["payload"] == sample_recipient_data

    @pytest.mark.asyncio
    async def test_enrich_award_fallback_to_piid(self, client, sample_award_data):
        """Test enrichment falls back to PIID."""
        with patch.object(client, "get_recipient_by_uei", return_value=None):
            with patch.object(client, "get_recipient_by_duns", return_value=None):
                with patch.object(client, "get_recipient_by_cage", return_value=None):
                    with patch.object(client, "get_award_by_piid", return_value=sample_award_data):
                        result = await client.enrich_award("AWD001", piid="PIID123")

        assert result["success"] is True
        assert result["payload"] == sample_award_data

    @pytest.mark.asyncio
    async def test_enrich_award_no_data_found(self, client):
        """Test enrichment when no data found."""
        with patch.object(client, "get_recipient_by_uei", return_value=None):
            with patch.object(client, "get_recipient_by_duns", return_value=None):
                with patch.object(client, "get_recipient_by_cage", return_value=None):
                    with patch.object(client, "get_award_by_piid", return_value=None):
                        result = await client.enrich_award("AWD001")

        assert result["success"] is False
        assert result["error"] == "No recipient/award data found"
        assert result["payload"] is None

    @pytest.mark.asyncio
    async def test_enrich_award_delta_detection_no_change(
        self, client, sample_recipient_data, freshness_record
    ):
        """Test delta detection when data hasn't changed."""
        # Compute hash for sample data
        payload_hash = client._compute_payload_hash(sample_recipient_data)
        freshness_record.payload_hash = payload_hash

        with patch.object(client, "get_recipient_by_uei", return_value=sample_recipient_data):
            result = await client.enrich_award(
                "AWD001", uei="UEI123456789", freshness_record=freshness_record
            )

        assert result["success"] is True
        assert result["delta_detected"] is False

    @pytest.mark.asyncio
    async def test_enrich_award_delta_detection_changed(
        self, client, sample_recipient_data, freshness_record
    ):
        """Test delta detection when data has changed."""
        # Set different hash in freshness record
        freshness_record.payload_hash = "different_hash"

        with patch.object(client, "get_recipient_by_uei", return_value=sample_recipient_data):
            result = await client.enrich_award(
                "AWD001", uei="UEI123456789", freshness_record=freshness_record
            )

        assert result["success"] is True
        assert result["delta_detected"] is True

    @pytest.mark.asyncio
    async def test_enrich_award_extracts_metadata(self, client, sample_award_data):
        """Test enrichment extracts delta metadata."""
        # Add modification_number to sample data
        sample_award_data["modification_number"] = "0"
        sample_award_data["action_date"] = "2023-01-15"

        with patch.object(client, "get_recipient_by_uei", return_value=sample_award_data):
            result = await client.enrich_award("AWD001", uei="UEI123456789")

        assert result["metadata"]["modification_number"] == "0"
        assert result["metadata"]["action_date"] == "2023-01-15"
        assert result["metadata"]["award_id"] == "AWD001"

    @pytest.mark.asyncio
    async def test_enrich_award_api_error(self, client):
        """Test enrichment handles API errors."""
        error = APIError("Server error", api_name="usaspending", endpoint="/test")
        with patch.object(client, "get_recipient_by_uei", side_effect=error):
            result = await client.enrich_award("AWD001", uei="UEI123")

        assert result["success"] is False
        assert "Server error" in result["error"]


# ==================== State Persistence Tests ====================


class TestStatePersistence:
    """Tests for state loading and saving."""

    def test_load_state_file_exists(self, client, tmp_path):
        """Test loading state from existing file."""
        state_data = {
            "last_cursor": "cursor123",
            "last_fetch_time": "2023-01-01T12:00:00",
        }

        state_file = tmp_path / "test_state.json"
        client.state_file = state_file
        state_file.write_text(json.dumps(state_data))

        result = client.load_state()

        assert result == state_data

    def test_load_state_file_not_exists(self, client, tmp_path):
        """Test loading state when file doesn't exist."""
        client.state_file = tmp_path / "nonexistent.json"

        result = client.load_state()

        assert result == {}

    def test_load_state_corrupt_json(self, client, tmp_path):
        """Test loading state with corrupt JSON."""
        state_file = tmp_path / "corrupt.json"
        client.state_file = state_file
        state_file.write_text("{invalid json")

        result = client.load_state()

        assert result == {}

    def test_save_state_success(self, client, tmp_path):
        """Test saving state to file."""
        state_data = {
            "cursor": "cursor456",
            "timestamp": "2023-01-15T10:00:00",
        }

        state_file = tmp_path / "save_test.json"
        client.state_file = state_file

        client.save_state(state_data)

        assert state_file.exists()
        with open(state_file) as f:
            loaded = json.load(f)
        assert loaded == state_data

    def test_save_state_creates_parent_directory(self, client, tmp_path):
        """Test save_state creates parent directory."""
        state_file = tmp_path / "nested" / "dirs" / "state.json"
        client.state_file = state_file

        client.save_state({"test": "data"})

        assert state_file.parent.exists()
        assert state_file.exists()

    def test_save_state_with_datetime_values(self, client, tmp_path):
        """Test save_state handles datetime objects."""
        state_data = {
            "timestamp": datetime(2023, 1, 1, 12, 0, 0),
        }

        state_file = tmp_path / "datetime_test.json"
        client.state_file = state_file

        client.save_state(state_data)

        # Should serialize datetime to string
        assert state_file.exists()
        with open(state_file) as f:
            loaded = json.load(f)
        assert isinstance(loaded["timestamp"], str)


# ==================== Edge Cases and Error Handling ====================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_enrich_award_all_identifiers_none(self, client):
        """Test enrichment with all identifiers as None."""
        result = await client.enrich_award("AWD001", uei=None, duns=None, cage=None, piid=None)

        assert result["success"] is False
        assert result["error"] == "No recipient/award data found"

    def test_compute_payload_hash_empty_dict(self, client):
        """Test hashing empty dictionary."""
        hash_value = client._compute_payload_hash({})

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

    def test_extract_delta_metadata_none_values(self, client):
        """Test metadata extraction with None values."""
        payload = {
            "modification_number": None,
            "action_date": None,
        }

        metadata = client._extract_delta_metadata(payload)

        assert metadata["modification_number"] is None
        assert metadata["action_date"] is None

    @pytest.mark.asyncio
    async def test_get_transactions_empty_response(self, client):
        """Test transaction lookup with empty response."""
        response = {}
        with patch.object(client, "_make_request", return_value=response):
            result = await client.get_transactions_by_recipient("UEI123")

        assert result == []

    def test_save_state_io_error(self, client, tmp_path):
        """Test save_state handles IO errors gracefully."""
        # Create read-only directory
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)

        state_file = readonly_dir / "state.json"
        client.state_file = state_file

        # Should not raise, just log error
        try:
            client.save_state({"test": "data"})
        except PermissionError:
            pass  # Expected on some systems
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)
