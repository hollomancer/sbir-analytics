"""Tests for SemanticScholarClient (async) and SyncSemanticScholarClient.

After the POC migration, :class:`SemanticScholarClient` inherits from
:class:`BaseAsyncAPIClient` (retry, rate limiting, typed errors) and
a thin sync facade lives in ``sync_wrappers.py``. These tests cover
both the async and sync entry points, plus the shared-limiter override
that lets worker threads share a global rate budget.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.enrichers.semantic_scholar import (
    PublicationRecord,
    SemanticScholarClient,
)
from sbir_etl.enrichers.sync_wrappers import SyncSemanticScholarClient
from sbir_etl.exceptions import APIError

pytestmark = pytest.mark.fast


# ==================== Fixtures ====================


@pytest.fixture
def mock_http_client() -> AsyncMock:
    mock = AsyncMock(spec=httpx.AsyncClient)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def client(mock_http_client: AsyncMock) -> SemanticScholarClient:
    return SemanticScholarClient(http_client=mock_http_client)


def _mock_response(status: int = 200, json_payload: dict | None = None) -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = json_payload or {}
    resp.text = str(json_payload or "")
    resp.raise_for_status = Mock()
    return resp


# ==================== PublicationRecord dataclass ====================


class TestPublicationRecord:
    def test_fields(self) -> None:
        rec = PublicationRecord(
            total_papers=10,
            h_index=5,
            citation_count=100,
            sample_titles=["T1"],
            affiliations=["Uni"],
        )
        assert rec.total_papers == 10
        assert rec.h_index == 5
        assert rec.citation_count == 100


# ==================== Initialization / headers ====================


class TestInitialization:
    def test_defaults(self, client: SemanticScholarClient) -> None:
        assert client.api_name == "semantic_scholar"
        assert client.base_url == "https://api.semanticscholar.org/graph/v1"
        assert client.rate_limit_per_minute == 100

    def test_inherits_from_base(self, client: SemanticScholarClient) -> None:
        from sbir_etl.enrichers.base_client import BaseAsyncAPIClient

        assert isinstance(client, BaseAsyncAPIClient)

    def test_build_headers_without_api_key(
        self, mock_http_client: AsyncMock
    ) -> None:
        with patch.dict("os.environ", {}, clear=True):
            c = SemanticScholarClient(http_client=mock_http_client)
        headers = c._build_headers()
        assert "x-api-key" not in headers
        assert headers["Accept"] == "application/json"

    def test_build_headers_with_explicit_api_key(
        self, mock_http_client: AsyncMock
    ) -> None:
        c = SemanticScholarClient(api_key="secret-123", http_client=mock_http_client)
        headers = c._build_headers()
        assert headers["x-api-key"] == "secret-123"

    def test_build_headers_from_env(self, mock_http_client: AsyncMock) -> None:
        with patch.dict("os.environ", {"SEMANTIC_SCHOLAR_API_KEY": "env-key"}):
            c = SemanticScholarClient(http_client=mock_http_client)
        headers = c._build_headers()
        assert headers["x-api-key"] == "env-key"


# ==================== Shared limiter override ====================


class TestSharedLimiterOverride:
    """When a shared sync limiter is injected, it should be used via to_thread."""

    async def test_shared_limiter_called_via_to_thread(
        self, mock_http_client: AsyncMock
    ) -> None:
        shared = RateLimiter(rate_limit_per_minute=50)
        shared.wait_if_needed = MagicMock()  # type: ignore[method-assign]
        c = SemanticScholarClient(
            shared_limiter=shared, http_client=mock_http_client
        )
        mock_http_client.get.return_value = _mock_response(200, {"data": []})

        await c.search_author("Alice")

        # The shared limiter should have been called exactly once
        shared.wait_if_needed.assert_called_once()

    async def test_shared_limiter_absent_uses_base_limiter(
        self, mock_http_client: AsyncMock
    ) -> None:
        """Without shared limiter, the base client's request_times is populated."""
        c = SemanticScholarClient(http_client=mock_http_client)
        mock_http_client.get.return_value = _mock_response(200, {"data": []})

        assert c.request_times == []
        await c.search_author("Alice")
        assert len(c.request_times) == 1


# ==================== search_author ====================


class TestSearchAuthor:
    async def test_returns_data_list(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"data": [{"authorId": "42", "name": "Jane"}]}
        )

        result = await client.search_author("Jane")

        assert result == [{"authorId": "42", "name": "Jane"}]

    async def test_empty_data_returns_empty_list(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, {"data": []})

        result = await client.search_author("Nobody")

        assert result == []

    async def test_400_returns_empty_list(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        """Malformed query → empty list (can't find author)."""
        resp = Mock()
        resp.status_code = 400
        resp.text = "bad query"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "400", request=Mock(), response=resp
        )

        result = await client.search_author("")

        assert result == []

    async def test_500_propagates_api_error(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        """Server errors propagate — caller can distinguish from 'not found'."""
        resp = Mock()
        resp.status_code = 500
        resp.text = "server exploded"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client.search_author("Alice")

    async def test_passes_query_params(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, {"data": []})

        await client.search_author("Alice Smith", limit=10)

        call_kwargs = mock_http_client.get.call_args[1]
        assert call_kwargs["params"] == {"query": "Alice Smith", "limit": 10}


# ==================== get_author_details ====================


class TestGetAuthorDetails:
    async def test_success_returns_payload(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        payload = {"name": "Jane", "hIndex": 15, "papers": []}
        mock_http_client.get.return_value = _mock_response(200, payload)

        result = await client.get_author_details("42")

        assert result == payload

    async def test_404_returns_none(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 404
        resp.text = "not found"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "404", request=Mock(), response=resp
        )

        result = await client.get_author_details("missing")

        assert result is None

    async def test_500_propagates(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 500
        resp.text = "boom"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client.get_author_details("42")


# ==================== lookup_author (two-step) ====================


class TestLookupAuthor:
    async def test_success(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.side_effect = [
            _mock_response(200, {"data": [{"authorId": "12345", "name": "Jane"}]}),
            _mock_response(
                200,
                {
                    "name": "Jane",
                    "hIndex": 15,
                    "citationCount": 500,
                    "affiliations": ["MIT"],
                    "papers": [
                        {"title": "Paper 1", "year": 2024},
                        {"title": "Paper 2", "year": 2023},
                    ],
                },
            ),
        ]

        rec = await client.lookup_author("Jane Smith")

        assert rec is not None
        assert rec.h_index == 15
        assert rec.total_papers == 2
        assert rec.citation_count == 500
        assert rec.sample_titles == ["Paper 1", "Paper 2"]
        assert "MIT" in rec.affiliations

    async def test_no_match_returns_none(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, {"data": []})

        rec = await client.lookup_author("Nobody")

        assert rec is None

    async def test_author_id_missing_returns_none(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"data": [{"name": "Jane"}]}  # missing authorId
        )

        rec = await client.lookup_author("Jane")

        assert rec is None

    async def test_details_404_returns_none(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        """Search finds an author but details lookup returns 404 → None."""
        resp_404 = Mock()
        resp_404.status_code = 404
        resp_404.text = "gone"
        mock_http_client.get.side_effect = [
            _mock_response(200, {"data": [{"authorId": "42", "name": "Jane"}]}),
            httpx.HTTPStatusError("404", request=Mock(), response=resp_404),
        ]

        rec = await client.lookup_author("Jane")

        assert rec is None

    async def test_server_error_propagates(
        self, client: SemanticScholarClient, mock_http_client: AsyncMock
    ) -> None:
        """500 on the search propagates — caller can tell 'failed' from 'not found'."""
        resp = Mock()
        resp.status_code = 500
        resp.text = "boom"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client.lookup_author("Jane")


# ==================== Sync facade ====================


class TestSyncFacade:
    """The sync facade routes through the persistent background event loop."""

    def test_context_manager(self) -> None:
        with SyncSemanticScholarClient() as client:
            assert hasattr(client, "lookup_author")
            assert hasattr(client, "search_author")
            assert hasattr(client, "get_author_details")

    def test_lookup_author_delegates_to_async(self) -> None:
        """Verify the sync wrapper calls the underlying async method via run_sync."""
        with SyncSemanticScholarClient() as client:
            client._client.lookup_author = AsyncMock(  # type: ignore[method-assign]
                return_value=PublicationRecord(
                    total_papers=3,
                    h_index=2,
                    citation_count=10,
                    sample_titles=["A", "B"],
                    affiliations=["X"],
                )
            )

            rec = client.lookup_author("Jane Smith")

            assert rec is not None
            assert rec.total_papers == 3
            client._client.lookup_author.assert_awaited_once_with("Jane Smith")

    def test_search_author_delegates(self) -> None:
        with SyncSemanticScholarClient() as client:
            client._client.search_author = AsyncMock(  # type: ignore[method-assign]
                return_value=[{"authorId": "1"}]
            )

            result = client.search_author("Jane")

            assert result == [{"authorId": "1"}]
            client._client.search_author.assert_awaited_once_with("Jane", 5)
