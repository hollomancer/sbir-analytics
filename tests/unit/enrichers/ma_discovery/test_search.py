"""Tests for M&A SearchTool clients and the backend factory.

No live network: HTTP is mocked. Missing keys fall back to the mock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from sbir_etl.config.schemas.domain import MADiscoveryConfig
from sbir_etl.enrichers.ma_discovery.queries import generate_queries
from sbir_etl.enrichers.ma_discovery.search import (
    BraveSearchTool,
    MockSearchTool,
    TavilySearchTool,
    build_search_tool,
)
from sbir_etl.exceptions import ConfigurationError


pytestmark = pytest.mark.fast


def _mock_response(status: int = 200, json_payload: dict | None = None) -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = json_payload or {}
    resp.text = str(json_payload or "")
    resp.raise_for_status = Mock()
    return resp


@pytest.fixture
def mock_http_client() -> AsyncMock:
    mock = AsyncMock(spec=httpx.AsyncClient)
    mock.aclose = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_mock_is_case_insensitive_for_fixture_pair() -> None:
    tool = MockSearchTool()
    hits = await tool.search('"PHYSICAL OPTICS" bought by "mercury SYSTEMS"')
    assert len(hits) == 1
    assert hits[0]["link"] == "http://example.com"
    assert "Physical Optics" in hits[0]["snippet"]


@pytest.mark.asyncio
async def test_mock_matches_recipient_v1_query_string() -> None:
    query = generate_queries("Physical Optics Corporation", "Mercury Systems, Inc.")[0]
    assert "physical optics" in query
    assert "mercury systems" in query
    hits = await MockSearchTool().search(query)
    assert hits
    assert hits[0]["link"] == "http://example.com"


@pytest.mark.asyncio
async def test_mock_rejects_unrelated_query() -> None:
    assert await MockSearchTool().search("unrelated labs other holdings") == []


def test_factory_missing_key_returns_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SBIR_ETL__MA_DISCOVERY__SEARCH_API_KEY", raising=False)
    tool = build_search_tool(
        "tavily",
        api_key=None,
        config=MADiscoveryConfig(search_backend="tavily", search_api_key=None),
    )
    assert isinstance(tool, MockSearchTool)


def test_factory_known_backend_with_key_returns_client(mock_http_client: AsyncMock) -> None:
    tavily = build_search_tool("tavily", api_key="tvly-test", http_client=mock_http_client)
    brave = build_search_tool("brave", api_key="bsa-test", http_client=mock_http_client)
    assert isinstance(tavily, TavilySearchTool)
    assert isinstance(brave, BraveSearchTool)


def test_factory_unknown_name_raises() -> None:
    with pytest.raises(ConfigurationError, match="Unknown M&A search backend"):
        build_search_tool("serper", api_key="not-used")


def test_factory_mock_name_ignores_key(mock_http_client: AsyncMock) -> None:
    tool = build_search_tool("mock", api_key="ignored", http_client=mock_http_client)
    assert isinstance(tool, MockSearchTool)


@pytest.mark.asyncio
async def test_tavily_maps_response_and_sends_auth_header(
    mock_http_client: AsyncMock,
) -> None:
    mock_http_client.post.return_value = _mock_response(
        200,
        {
            "results": [
                {
                    "title": "Mercury buys Physical Optics",
                    "url": "https://example.com/deal",
                    "content": "Mercury Systems acquired Physical Optics.",
                }
            ]
        },
    )
    tool = TavilySearchTool(api_key="tvly-test", http_client=mock_http_client)
    hits = await tool.search("physical optics mercury systems")

    assert hits == [
        {
            "snippet": "Mercury Systems acquired Physical Optics.",
            "link": "https://example.com/deal",
            "title": "Mercury buys Physical Optics",
        }
    ]
    mock_http_client.post.assert_called_once()
    url = mock_http_client.post.call_args.args[0]
    headers = mock_http_client.post.call_args.kwargs["headers"]
    body = mock_http_client.post.call_args.kwargs["json"]
    assert url == "https://api.tavily.com/search"
    assert headers["Authorization"] == "Bearer tvly-test"
    assert body["query"] == "physical optics mercury systems"
    assert body["search_depth"] == "basic"


@pytest.mark.asyncio
async def test_brave_maps_response_and_sends_subscription_header(
    mock_http_client: AsyncMock,
) -> None:
    mock_http_client.get.return_value = _mock_response(
        200,
        {
            "web": {
                "results": [
                    {
                        "title": "Acquisition announced",
                        "url": "https://example.com/brave",
                        "description": "Mercury Systems bought Physical Optics.",
                    }
                ]
            }
        },
    )
    tool = BraveSearchTool(api_key="bsa-test", http_client=mock_http_client)
    hits = await tool.search("physical optics mercury systems")

    assert hits == [
        {
            "snippet": "Mercury Systems bought Physical Optics.",
            "link": "https://example.com/brave",
            "title": "Acquisition announced",
        }
    ]
    mock_http_client.get.assert_called_once()
    url = mock_http_client.get.call_args.args[0]
    headers = mock_http_client.get.call_args.kwargs["headers"]
    params = mock_http_client.get.call_args.kwargs["params"]
    assert url == "https://api.search.brave.com/res/v1/web/search"
    assert headers["X-Subscription-Token"] == "bsa-test"
    assert params["q"] == "physical optics mercury systems"


@pytest.mark.asyncio
async def test_tavily_skips_hits_without_url(mock_http_client: AsyncMock) -> None:
    mock_http_client.post.return_value = _mock_response(
        200,
        {"results": [{"title": "No link", "content": "text only"}]},
    )
    tool = TavilySearchTool(api_key="tvly-test", http_client=mock_http_client)
    assert await tool.search("anything") == []
