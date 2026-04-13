"""Tests for LensPatentClient (async) and SyncLensPatentClient.

The legacy sync client had zero test coverage (232 lines, no tests).
These tests both document the behavior AND verify the migration
preserved it: parsing of the Lens API response shape, search methods,
no-token short-circuit, error handling, and sync facade delegation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from sbir_etl.enrichers.lens_patents import (
    LENS_API_URL,
    LensPatentClient,
    LensPatentRecord,
    _parse_records,
)
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.enrichers.sync_wrappers import SyncLensPatentClient

pytestmark = pytest.mark.fast


# ==================== Sample response fixtures ====================


SAMPLE_LENS_RESPONSE = {
    "data": [
        {
            "lens_id": "000-123-456-789-012",
            "title": [{"text": "Advanced Quantum Sensor"}],
            "applicant": [{"name": "Acme Defense Systems LLC"}],
            "inventor": [
                {"name": "Jane Doe"},
                {"name": "John Smith"},
            ],
            "filing_date": "2020-03-15",
            "date_published": "2021-06-01",
        },
        {
            "lens_id": "000-987-654-321-098",
            "title": "Compact Laser Array",  # Plain string form
            "applicant": [{"name": "Acme Defense Systems LLC"}],
            "inventor": [{"name": "Alice Wong"}],
            "filing_date": "2021-08-01",
            "date_published": "2022-11-15",
        },
    ]
}


# ==================== _parse_records (pure function) ====================


class TestParseRecords:
    def test_empty_data_returns_empty_list(self):
        assert _parse_records({}) == []
        assert _parse_records({"data": []}) == []

    def test_parses_multiple_records(self):
        records = _parse_records(SAMPLE_LENS_RESPONSE)
        assert len(records) == 2

    def test_extracts_patent_number_from_lens_id(self):
        records = _parse_records(SAMPLE_LENS_RESPONSE)
        assert records[0].patent_number == "000-123-456-789-012"

    def test_extracts_title_from_list_form(self):
        records = _parse_records(SAMPLE_LENS_RESPONSE)
        assert records[0].title == "Advanced Quantum Sensor"

    def test_extracts_title_from_plain_string(self):
        """Some Lens responses return title as a plain string rather than a list."""
        records = _parse_records(SAMPLE_LENS_RESPONSE)
        assert records[1].title == "Compact Laser Array"

    def test_extracts_assignee(self):
        records = _parse_records(SAMPLE_LENS_RESPONSE)
        assert records[0].assignee == "Acme Defense Systems LLC"

    def test_extracts_inventor_names(self):
        records = _parse_records(SAMPLE_LENS_RESPONSE)
        assert records[0].inventor_names == ["Jane Doe", "John Smith"]

    def test_extracts_dates(self):
        records = _parse_records(SAMPLE_LENS_RESPONSE)
        assert records[0].filing_date == "2020-03-15"
        assert records[0].publication_date == "2021-06-01"
        # Lens doesn't distinguish grant date — always None
        assert records[0].grant_date is None

    def test_missing_title_is_empty_string(self):
        records = _parse_records({"data": [{"lens_id": "x"}]})
        assert records[0].title == ""

    def test_missing_applicant_leaves_assignee_none(self):
        records = _parse_records({"data": [{"lens_id": "x", "title": "t"}]})
        assert records[0].assignee is None

    def test_missing_inventor_is_empty_list(self):
        records = _parse_records({"data": [{"lens_id": "x", "title": "t"}]})
        assert records[0].inventor_names == []

    def test_string_applicant_coerced(self):
        """If applicant is a string (not dict), assignee gets str() form."""
        records = _parse_records(
            {"data": [{"lens_id": "x", "title": "t", "applicant": ["Acme"]}]}
        )
        assert records[0].assignee == "Acme"


# ==================== Fixtures ====================


def _mock_response(status: int = 200, payload: dict | None = None) -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = payload or {}
    resp.text = str(payload or "")
    resp.raise_for_status = Mock()
    return resp


@pytest.fixture
def mock_http_client() -> AsyncMock:
    mock = AsyncMock(spec=httpx.AsyncClient)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def client(mock_http_client: AsyncMock) -> LensPatentClient:
    return LensPatentClient(api_token="test-token", http_client=mock_http_client)


# ==================== Initialization / headers ====================


class TestInitialization:
    def test_defaults(self, client: LensPatentClient) -> None:
        assert client.api_name == "lens_patents"
        assert client.rate_limit_per_minute == 50

    def test_inherits_from_base(self, client: LensPatentClient) -> None:
        from sbir_etl.enrichers.base_client import BaseAsyncAPIClient

        assert isinstance(client, BaseAsyncAPIClient)

    def test_token_in_auth_header(self, client: LensPatentClient) -> None:
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Content-Type"] == "application/json"

    def test_no_token_no_auth_header(
        self, mock_http_client: AsyncMock
    ) -> None:
        with patch.dict("os.environ", {}, clear=True):
            c = LensPatentClient(http_client=mock_http_client)
        headers = c._build_headers()
        assert "Authorization" not in headers
        # Content-Type always present
        assert headers["Content-Type"] == "application/json"

    def test_env_token(self, mock_http_client: AsyncMock) -> None:
        with patch.dict("os.environ", {"LENS_API_TOKEN": "env-secret"}):
            c = LensPatentClient(http_client=mock_http_client)
        headers = c._build_headers()
        assert headers["Authorization"] == "Bearer env-secret"


# ==================== Shared limiter ====================


class TestSharedLimiter:
    async def test_shared_limiter_invoked(
        self, mock_http_client: AsyncMock
    ) -> None:
        shared = RateLimiter(rate_limit_per_minute=50)
        shared.wait_if_needed = MagicMock()  # type: ignore[method-assign]
        c = LensPatentClient(
            api_token="t", shared_limiter=shared, http_client=mock_http_client
        )
        mock_http_client.post.return_value = _mock_response(200, {"data": []})

        await c.search_patents_by_assignee("Acme")

        shared.wait_if_needed.assert_called_once()


# ==================== No-token short-circuit ====================


class TestNoTokenShortCircuit:
    async def test_no_token_returns_empty_without_request(
        self, mock_http_client: AsyncMock
    ) -> None:
        """Without an API token, search methods return [] without hitting the network."""
        with patch.dict("os.environ", {}, clear=True):
            c = LensPatentClient(http_client=mock_http_client)

        result = await c.search_patents_by_assignee("Acme")

        assert result == []
        mock_http_client.post.assert_not_called()

    async def test_no_token_inventor_search_short_circuits(
        self, mock_http_client: AsyncMock
    ) -> None:
        with patch.dict("os.environ", {}, clear=True):
            c = LensPatentClient(http_client=mock_http_client)

        result = await c.search_patents_by_inventor("Jane Doe")

        assert result == []
        mock_http_client.post.assert_not_called()


# ==================== search_patents_by_assignee ====================


class TestSearchByAssignee:
    async def test_success_returns_parsed_records(
        self, client: LensPatentClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.post.return_value = _mock_response(
            200, SAMPLE_LENS_RESPONSE
        )

        records = await client.search_patents_by_assignee("Acme")

        assert len(records) == 2
        assert records[0].patent_number == "000-123-456-789-012"

    async def test_empty_results(
        self, client: LensPatentClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.post.return_value = _mock_response(200, {"data": []})

        records = await client.search_patents_by_assignee("Unknown")

        assert records == []

    async def test_api_error_returns_empty(
        self, client: LensPatentClient, mock_http_client: AsyncMock
    ) -> None:
        """API errors → empty list (preserves legacy 'errors as None/empty' contract)."""
        resp = Mock()
        resp.status_code = 500
        resp.text = "boom"
        mock_http_client.post.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        records = await client.search_patents_by_assignee("Acme")

        assert records == []

    async def test_post_body_shape(
        self, client: LensPatentClient, mock_http_client: AsyncMock
    ) -> None:
        """Verify the POST body matches the Lens query DSL."""
        mock_http_client.post.return_value = _mock_response(200, {"data": []})

        await client.search_patents_by_assignee("Acme Defense", max_results=25)

        call_args = mock_http_client.post.call_args
        body = call_args[1]["json"]
        assert body["query"]["match"]["applicant.name"] == "Acme Defense"
        assert body["size"] == 25
        assert "applicant" in body["include"]
        assert "filing_date" in body["include"]

    async def test_max_results_capped_at_100(
        self, client: LensPatentClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.post.return_value = _mock_response(200, {"data": []})

        await client.search_patents_by_assignee("Acme", max_results=500)

        body = mock_http_client.post.call_args[1]["json"]
        assert body["size"] == 100

    async def test_posts_to_absolute_url(
        self, client: LensPatentClient, mock_http_client: AsyncMock
    ) -> None:
        """Base URL is empty — absolute LENS_API_URL is passed as endpoint."""
        mock_http_client.post.return_value = _mock_response(200, {"data": []})

        await client.search_patents_by_assignee("Acme")

        called_url = mock_http_client.post.call_args[0][0]
        assert called_url == LENS_API_URL


class TestSearchByInventor:
    async def test_success(
        self, client: LensPatentClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.post.return_value = _mock_response(
            200, SAMPLE_LENS_RESPONSE
        )

        records = await client.search_patents_by_inventor("Jane Doe")

        assert len(records) == 2

    async def test_post_body_matches_inventor_field(
        self, client: LensPatentClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.post.return_value = _mock_response(200, {"data": []})

        await client.search_patents_by_inventor("Jane Doe")

        body = mock_http_client.post.call_args[1]["json"]
        assert body["query"]["match"]["inventor.name"] == "Jane Doe"

    async def test_max_results_capped_at_50(
        self, client: LensPatentClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.post.return_value = _mock_response(200, {"data": []})

        await client.search_patents_by_inventor("Jane Doe", max_results=200)

        body = mock_http_client.post.call_args[1]["json"]
        assert body["size"] == 50


# ==================== Sync facade ====================


class TestSyncFacade:
    def test_context_manager(self) -> None:
        with SyncLensPatentClient() as client:
            assert hasattr(client, "search_patents_by_assignee")
            assert hasattr(client, "search_patents_by_inventor")

    def test_search_by_assignee_delegates(self) -> None:
        with SyncLensPatentClient(api_token="t") as client:
            expected = [
                LensPatentRecord(
                    patent_number="LENS-001",
                    title="Smart Widget",
                    assignee="Acme Corp",
                )
            ]
            client._client.search_patents_by_assignee = AsyncMock(  # type: ignore[method-assign]
                return_value=expected
            )

            result = client.search_patents_by_assignee("Acme Corp")

            assert result == expected
            client._client.search_patents_by_assignee.assert_awaited_once_with(
                "Acme Corp", 100
            )

    def test_shared_limiter_plumbs_through(self) -> None:
        shared = RateLimiter(rate_limit_per_minute=50)
        with SyncLensPatentClient(shared_limiter=shared) as client:
            assert client._client._shared_limiter is shared
