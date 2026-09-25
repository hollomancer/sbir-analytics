"""Tests for OpenAlexClient (async) and SyncOpenAlexClient.

Follows the ``AsyncMock``-based pattern established in
test_orcid_client.py / test_semantic_scholar.py — no real network calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from sbir_etl.enrichers.openalex_client import (
    OpenAlexClient,
    OpenAlexRecord,
    _last_path_segment,
    _parse_author,
)
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.enrichers.sync_wrappers import SyncOpenAlexClient
from sbir_etl.exceptions import APIError

pytestmark = pytest.mark.fast


# ==================== Sample data ====================


SAMPLE_SEARCH_RESULT = {
    "id": "https://openalex.org/A5110956653",
    "display_name": "Jane McKee Smith",
    "orcid": None,
}

SAMPLE_PROFILE = {
    "id": "https://openalex.org/A5110956653",
    "display_name": "Jane McKee Smith",
    "orcid": "https://orcid.org/0000-0001-6678-1514",
    "works_count": 188,
    "cited_by_count": 6897,
    "affiliations": [
        {"institution": {"display_name": "University of Notre Dame"}},
        {"institution": {"display_name": "United States Army Corps of Engineers"}},
        {"institution": {"display_name": "University of Notre Dame"}},  # duplicate
    ],
}


# ==================== Pure parsing helpers ====================


class TestLastPathSegment:
    def test_extracts_from_url(self):
        assert _last_path_segment("https://openalex.org/A5110956653") == "A5110956653"

    def test_extracts_orcid_from_url(self):
        assert _last_path_segment("https://orcid.org/0000-0001-6678-1514") == "0000-0001-6678-1514"

    def test_passes_through_bare_id(self):
        assert _last_path_segment("A5110956653") == "A5110956653"

    def test_none_input(self):
        assert _last_path_segment(None) is None

    def test_empty_input(self):
        assert _last_path_segment("") is None


class TestParseAuthor:
    def test_extracts_id(self):
        rec = _parse_author(SAMPLE_PROFILE)
        assert rec.openalex_id == "A5110956653"

    def test_extracts_affiliations_deduped(self):
        rec = _parse_author(SAMPLE_PROFILE)
        assert rec.affiliations == [
            "University of Notre Dame",
            "United States Army Corps of Engineers",
        ]

    def test_extracts_orcid_bare(self):
        rec = _parse_author(SAMPLE_PROFILE)
        assert rec.orcid == "0000-0001-6678-1514"

    def test_missing_orcid(self):
        profile = {**SAMPLE_PROFILE, "orcid": None}
        rec = _parse_author(profile)
        assert rec.orcid is None

    def test_counts(self):
        rec = _parse_author(SAMPLE_PROFILE)
        assert rec.works_count == 188
        assert rec.cited_by_count == 6897


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
def client(mock_http_client: AsyncMock) -> OpenAlexClient:
    return OpenAlexClient(http_client=mock_http_client)


# ==================== Initialization / mailto ====================


class TestInitialization:
    def test_defaults(self, client: OpenAlexClient) -> None:
        assert client.api_name == "openalex"
        assert client.base_url == "https://api.openalex.org"
        assert client.rate_limit_per_minute == 100

    def test_inherits_from_base(self, client: OpenAlexClient) -> None:
        from sbir_etl.enrichers.base_client import BaseAsyncAPIClient

        assert isinstance(client, BaseAsyncAPIClient)

    def test_no_mailto_by_default(self, mock_http_client: AsyncMock) -> None:
        with patch.dict("os.environ", {}, clear=True):
            c = OpenAlexClient(http_client=mock_http_client)
        assert c._with_mailto({"a": 1}) == {"a": 1}

    def test_explicit_mailto(self, mock_http_client: AsyncMock) -> None:
        c = OpenAlexClient(mailto="you@example.com", http_client=mock_http_client)
        assert c._with_mailto({})["mailto"] == "you@example.com"

    def test_env_mailto(self, mock_http_client: AsyncMock) -> None:
        with patch.dict("os.environ", {"OPENALEX_MAILTO": "env@example.com"}):
            c = OpenAlexClient(http_client=mock_http_client)
        assert c._with_mailto({})["mailto"] == "env@example.com"


# ==================== Shared limiter ====================


class TestSharedLimiterOverride:
    async def test_shared_limiter_invoked(self, mock_http_client: AsyncMock) -> None:
        shared = RateLimiter(rate_limit_per_minute=30)
        shared.wait_if_needed = MagicMock()  # type: ignore[method-assign]
        c = OpenAlexClient(shared_limiter=shared, http_client=mock_http_client)
        mock_http_client.get.return_value = _mock_response(200, {"results": []})

        await c.search_authors("Smith")

        shared.wait_if_needed.assert_called_once()


# ==================== search_authors ====================


class TestSearchAuthors:
    async def test_returns_results_list(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, {"results": [SAMPLE_SEARCH_RESULT]})

        result = await client.search_authors("Jane Smith")

        assert result == [SAMPLE_SEARCH_RESULT]

    async def test_empty_results_returns_empty_list(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, {"results": []})

        assert await client.search_authors("Nobody") == []

    async def test_4xx_returns_empty(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 400
        resp.text = "bad"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "400", request=Mock(), response=resp
        )

        assert await client.search_authors("x") == []

    async def test_5xx_propagates(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 500
        resp.text = "boom"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client.search_authors("x")


# ==================== get_author_details ====================


class TestGetAuthorDetails:
    async def test_returns_profile(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_PROFILE)

        result = await client.get_author_details("A5110956653")

        assert result == SAMPLE_PROFILE

    async def test_accepts_full_url_id(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_PROFILE)

        await client.get_author_details("https://openalex.org/A5110956653")

        url = mock_http_client.get.call_args[0][0]
        assert url.endswith("/authors/A5110956653")

    async def test_404_returns_none(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 404
        resp.text = "not found"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "404", request=Mock(), response=resp
        )

        assert await client.get_author_details("GONE") is None

    async def test_500_propagates(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 500
        resp.text = "boom"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client.get_author_details("A5110956653")


# ==================== lookup ====================


class TestLookup:
    async def test_success_two_step(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.side_effect = [
            _mock_response(200, {"results": [SAMPLE_SEARCH_RESULT]}),
            _mock_response(200, SAMPLE_PROFILE),
        ]

        rec = await client.lookup("Jane Smith")

        assert rec is not None
        assert rec.openalex_id == "A5110956653"
        assert "University of Notre Dame" in rec.affiliations

    async def test_no_search_match_returns_none(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, {"results": []})

        assert await client.lookup("Nobody") is None

    async def test_empty_name_returns_none(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        assert await client.lookup("") is None
        mock_http_client.get.assert_not_called()

    async def test_missing_id_in_result_returns_none(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"results": [{"display_name": "No ID Here"}]}
        )

        assert await client.lookup("Jane Smith") is None

    async def test_profile_404_returns_none(
        self, client: OpenAlexClient, mock_http_client: AsyncMock
    ) -> None:
        resp_404 = Mock()
        resp_404.status_code = 404
        resp_404.text = "gone"
        mock_http_client.get.side_effect = [
            _mock_response(200, {"results": [SAMPLE_SEARCH_RESULT]}),
            httpx.HTTPStatusError("404", request=Mock(), response=resp_404),
        ]

        assert await client.lookup("Jane Smith") is None


# ==================== Sync facade ====================


class TestSyncFacade:
    def test_context_manager(self) -> None:
        with SyncOpenAlexClient() as client:
            assert hasattr(client, "lookup")
            assert hasattr(client, "search_authors")
            assert hasattr(client, "get_author_details")

    def test_lookup_delegates_to_async(self) -> None:
        with SyncOpenAlexClient() as client:
            client._client.lookup = AsyncMock(  # type: ignore[method-assign]
                return_value=OpenAlexRecord(openalex_id="A5110956653", works_count=188)
            )

            rec = client.lookup("Jane Smith")

            assert rec is not None
            assert rec.openalex_id == "A5110956653"
            assert rec.works_count == 188
            client._client.lookup.assert_awaited_once_with("Jane Smith")

    def test_shared_limiter_plumbs_through(self) -> None:
        shared = RateLimiter(rate_limit_per_minute=30)
        with SyncOpenAlexClient(shared_limiter=shared) as client:
            assert client._client._shared_limiter is shared

    def test_mailto_plumbs_through(self) -> None:
        with SyncOpenAlexClient(mailto="you@example.com") as client:
            assert client._client._mailto == "you@example.com"
