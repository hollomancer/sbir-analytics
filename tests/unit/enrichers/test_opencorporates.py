"""Tests for OpenCorporatesClient (async) and SyncOpenCorporatesClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import pytest

from sbir_etl.enrichers.opencorporates import (
    CorporateRecord,
    Officer,
    OpenCorporatesClient,
)
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.enrichers.sync_wrappers import SyncOpenCorporatesClient
from sbir_etl.exceptions import APIError

pytestmark = pytest.mark.fast


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
def client(mock_http_client: AsyncMock) -> OpenCorporatesClient:
    return OpenCorporatesClient(api_token="test-token", http_client=mock_http_client)


@pytest.fixture
def token_less_client(mock_http_client: AsyncMock) -> OpenCorporatesClient:
    """Client constructed without a token to exercise the short-circuit path."""
    import os

    # Clear env var if set
    os.environ.pop("OPENCORPORATES_API_TOKEN", None)
    return OpenCorporatesClient(http_client=mock_http_client)


# ==================== Dataclasses ====================


class TestDataClasses:
    def test_officer_defaults(self):
        o = Officer(name="Jane Doe")
        assert o.name == "Jane Doe"
        assert o.position is None

    def test_corporate_record_defaults(self):
        r = CorporateRecord(
            company_name="Acme", jurisdiction="us_va", company_number="123"
        )
        assert r.officers == []
        assert r.parent_company is None


# ==================== Initialization ====================


class TestInitialization:
    def test_defaults(self, client: OpenCorporatesClient) -> None:
        assert client.api_name == "opencorporates"
        assert client.base_url == "https://api.opencorporates.com/v0.4"
        assert client.rate_limit_per_minute == 30

    def test_inherits_from_base(self, client: OpenCorporatesClient) -> None:
        from sbir_etl.enrichers.base_client import BaseAsyncAPIClient

        assert isinstance(client, BaseAsyncAPIClient)

    def test_token_not_in_headers(self, client: OpenCorporatesClient) -> None:
        """OpenCorporates uses query-param auth, not header auth."""
        headers = client._build_headers()
        assert "Authorization" not in headers


# ==================== Token injection ====================


class TestTokenInjection:
    async def test_token_appended_to_params(
        self, client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"results": {"companies": []}}
        )

        await client.search_companies("Test Corp")

        call_kwargs = mock_http_client.get.call_args[1]
        assert call_kwargs["params"]["api_token"] == "test-token"

    async def test_no_token_short_circuits_search(
        self, token_less_client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        """search_companies returns [] without hitting the network if no token."""
        result = await token_less_client.search_companies("Test Corp")

        assert result == []
        mock_http_client.get.assert_not_called()

    async def test_no_token_still_allows_get_company(
        self, token_less_client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        """get_company works without a token (public OpenCorporates access)."""
        mock_http_client.get.return_value = _mock_response(
            200, {"results": {"company": {"name": "X"}}}
        )

        result = await token_less_client.get_company("us_va", "123")

        assert result is not None
        call_kwargs = mock_http_client.get.call_args[1]
        assert "api_token" not in call_kwargs["params"]


# ==================== Shared limiter ====================


class TestSharedLimiter:
    async def test_shared_limiter_invoked(
        self, mock_http_client: AsyncMock
    ) -> None:
        shared = RateLimiter(rate_limit_per_minute=30)
        shared.wait_if_needed = MagicMock()  # type: ignore[method-assign]
        c = OpenCorporatesClient(
            api_token="t", shared_limiter=shared, http_client=mock_http_client
        )
        mock_http_client.get.return_value = _mock_response(
            200, {"results": {"companies": []}}
        )

        await c.search_companies("x")

        shared.wait_if_needed.assert_called_once()


# ==================== search / get / lookup ====================


class TestSearchCompanies:
    async def test_with_jurisdiction(
        self, client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"results": {"companies": []}}
        )

        await client.search_companies("Test Corp", jurisdiction="us_va")

        call_kwargs = mock_http_client.get.call_args[1]
        assert call_kwargs["params"]["jurisdiction_code"] == "us_va"

    async def test_404_returns_empty(
        self, client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 404
        resp.text = "not found"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "404", request=Mock(), response=resp
        )

        result = await client.search_companies("Ghost")

        assert result == []

    async def test_500_propagates(
        self, client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 500
        resp.text = "boom"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client.search_companies("x")


class TestLookupCompany:
    async def test_success_full_flow(
        self, client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        search_payload = {
            "results": {
                "companies": [
                    {
                        "company": {
                            "name": "Acme Defense Systems LLC",
                            "jurisdiction_code": "us_va",
                            "company_number": "12345678",
                        }
                    }
                ]
            }
        }
        detail_payload = {
            "results": {
                "company": {
                    "name": "Acme Defense Systems LLC",
                    "incorporation_date": "2015-03-12",
                    "dissolution_date": None,
                    "current_status": "Active",
                    "company_type": "LLC",
                    "registered_address": {
                        "street_address": "123 Main St",
                        "locality": "Arlington",
                        "region": "VA",
                        "postal_code": "22201",
                    },
                    "corporate_groupings": [
                        {
                            "corporate_grouping": {
                                "name": "Big Defense Corp",
                                "jurisdiction_code": "us_de",
                            }
                        }
                    ],
                }
            }
        }
        officers_payload = {
            "results": {
                "officers": [
                    {
                        "officer": {
                            "name": "Jane Doe",
                            "position": "CEO",
                            "start_date": "2015-03-12",
                        }
                    }
                ]
            }
        }

        mock_http_client.get.side_effect = [
            _mock_response(200, search_payload),
            _mock_response(200, detail_payload),
            _mock_response(200, officers_payload),
        ]

        rec = await client.lookup_company("Acme Defense Systems")

        assert rec is not None
        assert rec.company_name == "Acme Defense Systems LLC"
        assert rec.jurisdiction == "us_va"
        assert rec.incorporation_date == "2015-03-12"
        assert rec.status == "Active"
        assert rec.parent_company == "Big Defense Corp"
        assert rec.parent_jurisdiction == "us_de"
        assert rec.registered_address == "123 Main St, Arlington, VA, 22201"
        assert len(rec.officers) == 1
        assert rec.officers[0].name == "Jane Doe"
        assert rec.officers[0].position == "CEO"

    async def test_no_search_match_returns_none(
        self, client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"results": {"companies": []}}
        )

        assert await client.lookup_company("Nonexistent") is None

    async def test_minimal_record_when_missing_jurisdiction(
        self, client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        """When search results lack jurisdiction_code / company_number, return a minimal record."""
        mock_http_client.get.return_value = _mock_response(
            200,
            {
                "results": {
                    "companies": [
                        {
                            "company": {
                                "name": "Incomplete Corp",
                                "incorporation_date": "2020-01-01",
                                "current_status": "Active",
                            }
                        }
                    ]
                }
            },
        )

        rec = await client.lookup_company("Incomplete Corp")

        assert rec is not None
        assert rec.company_name == "Incomplete Corp"
        assert rec.incorporation_date == "2020-01-01"
        # Only the search call should have been made — no detail fetch
        assert mock_http_client.get.await_count == 1

    async def test_no_parent_grouping(
        self, client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        search_payload = {
            "results": {
                "companies": [
                    {
                        "company": {
                            "name": "Indie Startup",
                            "jurisdiction_code": "us_de",
                            "company_number": "99999",
                        }
                    }
                ]
            }
        }
        detail_payload = {
            "results": {
                "company": {
                    "name": "Indie Startup",
                    "incorporation_date": "2020-01-15",
                    "current_status": "Active",
                    "corporate_groupings": [],
                }
            }
        }
        officers_payload = {"results": {"officers": []}}

        mock_http_client.get.side_effect = [
            _mock_response(200, search_payload),
            _mock_response(200, detail_payload),
            _mock_response(200, officers_payload),
        ]

        rec = await client.lookup_company("Indie Startup")

        assert rec is not None
        assert rec.parent_company is None
        assert rec.officers == []


class TestGetOfficers:
    async def test_empty_returns_empty_list(
        self, client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200, {"results": {"officers": []}}
        )

        officers = await client.get_officers("us_va", "123")

        assert officers == []

    async def test_parses_officer_records(
        self, client: OpenCorporatesClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(
            200,
            {
                "results": {
                    "officers": [
                        {
                            "officer": {
                                "name": "Jane Doe",
                                "position": "CEO",
                                "start_date": "2020-01-01",
                            }
                        }
                    ]
                }
            },
        )

        officers = await client.get_officers("us_va", "123")

        assert len(officers) == 1
        assert officers[0].name == "Jane Doe"
        assert officers[0].position == "CEO"
        assert officers[0].start_date == "2020-01-01"


# ==================== Sync facade ====================


class TestSyncFacade:
    def test_context_manager(self) -> None:
        with SyncOpenCorporatesClient() as client:
            assert hasattr(client, "lookup_company")
            assert hasattr(client, "search_companies")
            assert hasattr(client, "get_officers")

    def test_lookup_delegates_to_async(self) -> None:
        with SyncOpenCorporatesClient(api_token="t") as client:
            client._client.lookup_company = AsyncMock(  # type: ignore[method-assign]
                return_value=CorporateRecord(
                    company_name="Mock Co",
                    jurisdiction="us_ca",
                    company_number="1",
                )
            )

            rec = client.lookup_company("Mock Co")

            assert rec is not None
            assert rec.company_name == "Mock Co"
            client._client.lookup_company.assert_awaited_once_with("Mock Co", None)

    def test_shared_limiter_plumbs_through(self) -> None:
        shared = RateLimiter(rate_limit_per_minute=30)
        with SyncOpenCorporatesClient(shared_limiter=shared) as client:
            assert client._client._shared_limiter is shared
