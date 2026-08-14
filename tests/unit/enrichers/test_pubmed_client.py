"""Tests for PubMedClient (async) and SyncPubMedClient.

Follows the ``AsyncMock``-based pattern established in
test_orcid_client.py / test_fpds_atom.py — no real network calls.
``efetch`` returns XML (like FPDS), ``esearch`` returns JSON.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from sbir_etl.enrichers.pubmed_client import (
    PubMedClient,
    PubMedRecord,
    _best_matching_author,
    _parse_efetch_xml,
)
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.enrichers.sync_wrappers import SyncPubMedClient
from sbir_etl.exceptions import APIError

pytestmark = pytest.mark.fast


# ==================== Sample data ====================


SAMPLE_ESEARCH_RESULT = {
    "esearchresult": {"idlist": ["42599173", "42598748"]},
}

SAMPLE_EFETCH_XML = """<?xml version="1.0" ?>
<PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID Version="1">42599173</PMID>
<Article><ArticleTitle>Validation of the Catatonia Quick Screen.</ArticleTitle>
<AuthorList CompleteYN="Y">
<Author ValidYN="Y"><LastName>Luccarelli</LastName><ForeName>James</ForeName><Initials>J</Initials>
<AffiliationInfo><Affiliation>Harvard Medical School, Boston, MA, USA.</Affiliation></AffiliationInfo>
</Author>
<Author ValidYN="Y"><LastName>Smith</LastName><ForeName>Joshua Ryan</ForeName><Initials>JR</Initials>
<AffiliationInfo><Affiliation>Vanderbilt University Medical Center, Nashville, TN, USA.</Affiliation></AffiliationInfo>
<AffiliationInfo><Affiliation>Vanderbilt Kennedy Center, Nashville, TN, USA.</Affiliation></AffiliationInfo>
</Author>
</AuthorList>
</Article>
</MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>
"""

SAMPLE_EFETCH_XML_NO_ARTICLE = """<?xml version="1.0" ?>
<PubmedArticleSet>
</PubmedArticleSet>
"""


# ==================== Pure parsing helpers ====================


class TestParseEfetchXml:
    def test_extracts_title(self):
        parsed = _parse_efetch_xml(SAMPLE_EFETCH_XML)
        assert parsed is not None
        assert parsed["title"] == "Validation of the Catatonia Quick Screen."

    def test_extracts_authors_and_affiliations(self):
        parsed = _parse_efetch_xml(SAMPLE_EFETCH_XML)
        assert parsed is not None
        names = [a["name"] for a in parsed["authors"]]
        assert "James Luccarelli" in names
        assert "Joshua Ryan Smith" in names
        smith = next(a for a in parsed["authors"] if a["name"] == "Joshua Ryan Smith")
        assert "Vanderbilt University Medical Center, Nashville, TN, USA." in smith["affiliations"]
        assert len(smith["affiliations"]) == 2

    def test_no_article_returns_none(self):
        assert _parse_efetch_xml(SAMPLE_EFETCH_XML_NO_ARTICLE) is None

    def test_malformed_xml_returns_none(self):
        assert _parse_efetch_xml("<not><valid") is None


class TestBestMatchingAuthor:
    def test_matches_by_last_name(self):
        authors = [
            {"name": "James Luccarelli", "affiliations": []},
            {"name": "Joshua Ryan Smith", "affiliations": ["Vanderbilt"]},
        ]
        best = _best_matching_author(authors, "Jane Smith")
        assert best is not None
        assert best["name"] == "Joshua Ryan Smith"

    def test_no_match_falls_back_to_first(self):
        authors = [{"name": "James Luccarelli", "affiliations": []}]
        best = _best_matching_author(authors, "Nobody Here")
        assert best is not None
        assert best["name"] == "James Luccarelli"

    def test_empty_authors_returns_none(self):
        assert _best_matching_author([], "Jane Smith") is None


# ==================== Fixtures ====================


def _mock_json_response(status: int = 200, payload: dict | None = None) -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = payload or {}
    resp.text = str(payload or "")
    resp.raise_for_status = Mock()
    return resp


def _mock_xml_response(status: int = 200, xml_text: str = "") -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.text = xml_text
    resp.raise_for_status = Mock()
    return resp


@pytest.fixture
def mock_http_client() -> AsyncMock:
    mock = AsyncMock(spec=httpx.AsyncClient)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def client(mock_http_client: AsyncMock) -> PubMedClient:
    return PubMedClient(http_client=mock_http_client)


# ==================== Initialization / api key ====================


class TestInitialization:
    def test_defaults_no_key(self, client: PubMedClient) -> None:
        assert client.api_name == "pubmed"
        assert client.base_url == "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        assert client.rate_limit_per_minute == 180

    def test_inherits_from_base(self, client: PubMedClient) -> None:
        from sbir_etl.enrichers.base_client import BaseAsyncAPIClient

        assert isinstance(client, BaseAsyncAPIClient)

    def test_no_key_no_param(self, mock_http_client: AsyncMock) -> None:
        with patch.dict("os.environ", {}, clear=True):
            c = PubMedClient(http_client=mock_http_client)
        assert "api_key" not in c._with_api_key({})

    def test_explicit_key_raises_default_rate_limit(self, mock_http_client: AsyncMock) -> None:
        c = PubMedClient(api_key="abc-key", http_client=mock_http_client)
        assert c._with_api_key({})["api_key"] == "abc-key"
        assert c.rate_limit_per_minute == 600

    def test_env_key(self, mock_http_client: AsyncMock) -> None:
        with patch.dict("os.environ", {"NCBI_API_KEY": "env-key"}):
            c = PubMedClient(http_client=mock_http_client)
        assert c._with_api_key({})["api_key"] == "env-key"
        assert c.rate_limit_per_minute == 600

    def test_explicit_rate_limit_overrides_key_default(self, mock_http_client: AsyncMock) -> None:
        c = PubMedClient(api_key="abc-key", rate_limit_per_minute=42, http_client=mock_http_client)
        assert c.rate_limit_per_minute == 42


# ==================== Shared limiter ====================


class TestSharedLimiterOverride:
    async def test_shared_limiter_invoked(self, mock_http_client: AsyncMock) -> None:
        shared = RateLimiter(rate_limit_per_minute=30)
        shared.wait_if_needed = MagicMock()  # type: ignore[method-assign]
        c = PubMedClient(shared_limiter=shared, http_client=mock_http_client)
        mock_http_client.get.return_value = _mock_json_response(200, SAMPLE_ESEARCH_RESULT)

        await c.search_pmids("Smith")

        shared.wait_if_needed.assert_called_once()


# ==================== search_pmids ====================


class TestSearchPmids:
    async def test_returns_pmid_list(
        self, client: PubMedClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_json_response(200, SAMPLE_ESEARCH_RESULT)

        result = await client.search_pmids("Jane Smith")

        assert result == ["42599173", "42598748"]

    async def test_empty_results_returns_empty_list(
        self, client: PubMedClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_json_response(
            200, {"esearchresult": {"idlist": []}}
        )

        assert await client.search_pmids("Nobody") == []

    async def test_4xx_returns_empty(
        self, client: PubMedClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 400
        resp.text = "bad"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "400", request=Mock(), response=resp
        )

        assert await client.search_pmids("x") == []

    async def test_5xx_propagates(self, client: PubMedClient, mock_http_client: AsyncMock) -> None:
        resp = Mock()
        resp.status_code = 500
        resp.text = "boom"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client.search_pmids("x")


# ==================== get_author_affiliations ====================


class TestGetAuthorAffiliations:
    async def test_returns_parsed_xml(
        self, client: PubMedClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_xml_response(200, SAMPLE_EFETCH_XML)

        result = await client.get_author_affiliations("42599173")

        assert result is not None
        assert result["title"] == "Validation of the Catatonia Quick Screen."
        assert len(result["authors"]) == 2

    async def test_4xx_returns_none(
        self, client: PubMedClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 404
        resp.text = "not found"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "404", request=Mock(), response=resp
        )

        assert await client.get_author_affiliations("GONE") is None

    async def test_5xx_propagates(self, client: PubMedClient, mock_http_client: AsyncMock) -> None:
        resp = Mock()
        resp.status_code = 500
        resp.text = "boom"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client.get_author_affiliations("42599173")


# ==================== lookup ====================


class TestLookup:
    async def test_success_two_step(
        self, client: PubMedClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.side_effect = [
            _mock_json_response(200, SAMPLE_ESEARCH_RESULT),
            _mock_xml_response(200, SAMPLE_EFETCH_XML),
        ]

        rec = await client.lookup("Joshua Smith")

        assert rec is not None
        assert rec.pmid == "42599173"
        assert rec.author_name == "Joshua Ryan Smith"
        assert "Vanderbilt University Medical Center, Nashville, TN, USA." in rec.affiliations
        assert rec.title == "Validation of the Catatonia Quick Screen."

    async def test_no_search_match_returns_none(
        self, client: PubMedClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_json_response(
            200, {"esearchresult": {"idlist": []}}
        )

        assert await client.lookup("Nobody") is None

    async def test_empty_name_returns_none(
        self, client: PubMedClient, mock_http_client: AsyncMock
    ) -> None:
        assert await client.lookup("") is None
        mock_http_client.get.assert_not_called()

    async def test_affiliations_fetch_failure_returns_none(
        self, client: PubMedClient, mock_http_client: AsyncMock
    ) -> None:
        resp_404 = Mock()
        resp_404.status_code = 404
        resp_404.text = "gone"
        mock_http_client.get.side_effect = [
            _mock_json_response(200, SAMPLE_ESEARCH_RESULT),
            httpx.HTTPStatusError("404", request=Mock(), response=resp_404),
        ]

        assert await client.lookup("Joshua Smith") is None


# ==================== Sync facade ====================


class TestSyncFacade:
    def test_context_manager(self) -> None:
        with SyncPubMedClient() as client:
            assert hasattr(client, "lookup")
            assert hasattr(client, "search_pmids")
            assert hasattr(client, "get_author_affiliations")

    def test_lookup_delegates_to_async(self) -> None:
        with SyncPubMedClient() as client:
            client._client.lookup = AsyncMock(  # type: ignore[method-assign]
                return_value=PubMedRecord(pmid="42599173", author_name="Joshua Ryan Smith")
            )

            rec = client.lookup("Joshua Smith")

            assert rec is not None
            assert rec.pmid == "42599173"
            client._client.lookup.assert_awaited_once_with("Joshua Smith")

    def test_shared_limiter_plumbs_through(self) -> None:
        shared = RateLimiter(rate_limit_per_minute=30)
        with SyncPubMedClient(shared_limiter=shared) as client:
            assert client._client._shared_limiter is shared
