"""Tests for ORCIDClient (async) and SyncORCIDClient.

Pure parsing helpers (``_parse_profile``) are unchanged after the
migration. The client tests use the ``AsyncMock``-based pattern
established in test_base_client / test_semantic_scholar / test_fpds_atom.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from sbir_etl.enrichers.orcid_client import (
    ORCIDClient,
    ORCIDRecord,
    _parse_profile,
)
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.enrichers.sync_wrappers import SyncORCIDClient
from sbir_etl.exceptions import APIError

pytestmark = pytest.mark.fast


# ==================== Sample data ====================


SAMPLE_PROFILE = {
    "activities-summary": {
        "employments": {
            "affiliation-group": [
                {"summaries": [{"employment-summary": {"organization": {"name": "MIT"}}}]},
                {"summaries": [{"employment-summary": {"organization": {"name": "Stanford"}}}]},
            ]
        },
        "works": {
            "group": [
                {"work-summary": [{"title": {"title": {"value": "Paper A"}}}]},
                {"work-summary": [{"title": {"title": {"value": "Paper B"}}}]},
            ]
        },
        "fundings": {"group": [{"funding-summary": [{}]}]},
    },
    "person": {
        "keywords": {"keyword": [{"content": "AI"}, {"content": "ML"}]}
    },
}


# ==================== Parsing (unchanged) ====================


class TestParseProfile:
    def test_extracts_affiliations(self):
        rec = _parse_profile(
            "0000-0001",
            {"given-names": "Jane", "family-names": "Doe"},
            SAMPLE_PROFILE,
        )
        assert "MIT" in rec.affiliations
        assert "Stanford" in rec.affiliations

    def test_extracts_works(self):
        rec = _parse_profile("0000-0001", {}, SAMPLE_PROFILE)
        assert rec.works_count == 2
        assert "Paper A" in rec.sample_work_titles

    def test_extracts_funding(self):
        rec = _parse_profile("0000-0001", {}, SAMPLE_PROFILE)
        assert rec.funding_count == 1

    def test_extracts_keywords(self):
        rec = _parse_profile("0000-0001", {}, SAMPLE_PROFILE)
        assert "AI" in rec.keywords
        assert "ML" in rec.keywords

    def test_record_fields(self):
        rec = ORCIDRecord(orcid_id="0000-0001", works_count=5, funding_count=2)
        assert rec.orcid_id == "0000-0001"
        assert rec.works_count == 5


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
def client(mock_http_client: AsyncMock) -> ORCIDClient:
    return ORCIDClient(http_client=mock_http_client)


# ==================== Initialization / headers ====================


class TestInitialization:
    def test_defaults(self, client: ORCIDClient) -> None:
        assert client.api_name == "orcid"
        assert client.base_url == "https://pub.orcid.org/v3.0"
        assert client.rate_limit_per_minute == 60

    def test_inherits_from_base(self, client: ORCIDClient) -> None:
        from sbir_etl.enrichers.base_client import BaseAsyncAPIClient

        assert isinstance(client, BaseAsyncAPIClient)

    def test_no_token_no_auth_header(self, mock_http_client: AsyncMock) -> None:
        with patch.dict("os.environ", {}, clear=True):
            c = ORCIDClient(http_client=mock_http_client)
        headers = c._build_headers()
        assert "Authorization" not in headers

    def test_explicit_token_sets_bearer_header(
        self, mock_http_client: AsyncMock
    ) -> None:
        c = ORCIDClient(access_token="abc-token", http_client=mock_http_client)
        headers = c._build_headers()
        assert headers["Authorization"] == "Bearer abc-token"

    def test_env_token(self, mock_http_client: AsyncMock) -> None:
        with patch.dict("os.environ", {"ORCID_ACCESS_TOKEN": "env-token"}):
            c = ORCIDClient(http_client=mock_http_client)
        headers = c._build_headers()
        assert headers["Authorization"] == "Bearer env-token"


# ==================== Shared limiter ====================


class TestSharedLimiterOverride:
    async def test_shared_limiter_invoked(
        self, mock_http_client: AsyncMock
    ) -> None:
        shared = RateLimiter(rate_limit_per_minute=30)
        shared.wait_if_needed = MagicMock()  # type: ignore[method-assign]
        c = ORCIDClient(shared_limiter=shared, http_client=mock_http_client)
        mock_http_client.get.return_value = _mock_response(
            200, {"expanded-result": []}
        )

        await c.search("Smith")

        shared.wait_if_needed.assert_called_once()


# ==================== search ====================


class TestSearch:
    async def test_returns_expanded_result_list(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200,
            {
                "expanded-result": [
                    {"orcid-id": "0000-0001", "given-names": "Jane"}
                ]
            },
        )

        result = await client.search("Doe", "Jane")

        assert result == [{"orcid-id": "0000-0001", "given-names": "Jane"}]

    async def test_empty_results_returns_empty_list(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"expanded-result": []}
        )

        assert await client.search("Nobody") == []

    async def test_query_with_given_names(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"expanded-result": []}
        )

        await client.search("Smith", "Jane")

        call_kwargs = mock_http_client.get.call_args[1]
        q = call_kwargs["params"]["q"]
        assert "family-name:Smith" in q
        assert "given-names:Jane" in q
        assert " AND " in q

    async def test_query_without_given_names(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"expanded-result": []}
        )

        await client.search("Smith")

        q = mock_http_client.get.call_args[1]["params"]["q"]
        assert q == "family-name:Smith"

    async def test_4xx_returns_empty(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 400
        resp.text = "bad"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "400", request=Mock(), response=resp
        )

        assert await client.search("x") == []

    async def test_5xx_propagates(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 500
        resp.text = "boom"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client.search("x")


# ==================== get_profile ====================


class TestGetProfile:
    async def test_returns_profile(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_PROFILE)

        result = await client.get_profile("0000-0001")

        assert result == SAMPLE_PROFILE

    async def test_404_returns_none(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 404
        resp.text = "not found"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "404", request=Mock(), response=resp
        )

        assert await client.get_profile("GONE") is None

    async def test_500_propagates(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 500
        resp.text = "boom"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client.get_profile("0000-0001")


# ==================== lookup ====================


class TestLookup:
    async def test_success_two_step(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.side_effect = [
            _mock_response(
                200,
                {
                    "expanded-result": [
                        {
                            "orcid-id": "0000-0001",
                            "given-names": "Jane",
                            "family-names": "Doe",
                        }
                    ]
                },
            ),
            _mock_response(200, SAMPLE_PROFILE),
        ]

        rec = await client.lookup("Jane Doe")

        assert rec is not None
        assert rec.orcid_id == "0000-0001"
        assert rec.works_count == 2
        assert "MIT" in rec.affiliations

    async def test_no_search_match_returns_none(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"expanded-result": []}
        )

        assert await client.lookup("Nobody") is None

    async def test_empty_name_returns_none(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        assert await client.lookup("") is None
        mock_http_client.get.assert_not_called()

    async def test_missing_orcid_id_in_result_returns_none(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"expanded-result": [{"given-names": "Jane"}]}
        )

        assert await client.lookup("Jane Doe") is None

    async def test_profile_404_returns_none(
        self, client: ORCIDClient, mock_http_client: AsyncMock
    ) -> None:
        resp_404 = Mock()
        resp_404.status_code = 404
        resp_404.text = "gone"
        mock_http_client.get.side_effect = [
            _mock_response(
                200,
                {
                    "expanded-result": [
                        {"orcid-id": "0000-0001", "given-names": "Jane"}
                    ]
                },
            ),
            httpx.HTTPStatusError("404", request=Mock(), response=resp_404),
        ]

        assert await client.lookup("Jane Doe") is None


# ==================== Sync facade ====================


class TestSyncFacade:
    def test_context_manager(self) -> None:
        with SyncORCIDClient() as client:
            assert hasattr(client, "lookup")
            assert hasattr(client, "search")
            assert hasattr(client, "get_profile")

    def test_lookup_delegates_to_async(self) -> None:
        with SyncORCIDClient() as client:
            client._client.lookup = AsyncMock(  # type: ignore[method-assign]
                return_value=ORCIDRecord(orcid_id="0000-0001", works_count=7)
            )

            rec = client.lookup("Jane Doe")

            assert rec is not None
            assert rec.orcid_id == "0000-0001"
            assert rec.works_count == 7
            client._client.lookup.assert_awaited_once_with("Jane Doe")

    def test_shared_limiter_plumbs_through(self) -> None:
        shared = RateLimiter(rate_limit_per_minute=30)
        with SyncORCIDClient(shared_limiter=shared) as client:
            assert client._client._shared_limiter is shared
