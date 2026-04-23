"""Tests for SEC EDGAR API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sbir_etl.enrichers.sec_edgar.client import EdgarAPIClient


@pytest.fixture
def mock_config():
    """Minimal SEC EDGAR config for testing."""
    return {
        "base_url": "https://efts.sec.gov/LATEST",
        "facts_base_url": "https://data.sec.gov/api/xbrl",
        "filings_base_url": "https://data.sec.gov/submissions",
        "contact_email_env_var": "SEC_EDGAR_CONTACT_EMAIL",
        "rate_limit_per_minute": 600,
        "timeout_seconds": 30,
    }


@pytest.fixture
def mock_http_client():
    """Mock httpx.AsyncClient."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def client(mock_config, mock_http_client):
    """EdgarAPIClient with mocked dependencies."""
    with patch.dict("os.environ", {"SEC_EDGAR_CONTACT_EMAIL": "test@example.com"}):
        return EdgarAPIClient(config=mock_config, http_client=mock_http_client)


class TestEdgarAPIClientInit:
    def test_init_with_config(self, client):
        assert client.api_name == "sec_edgar"
        assert client.base_url == "https://efts.sec.gov/LATEST"
        assert client.rate_limit_per_minute == 600

    def test_init_sets_contact_email(self, client):
        assert client.contact_email == "test@example.com"

    def test_init_warns_without_email(self, mock_config, mock_http_client):
        with patch.dict("os.environ", {}, clear=True):
            client = EdgarAPIClient(config=mock_config, http_client=mock_http_client)
            assert client.contact_email == ""

    def test_build_headers_includes_user_agent(self, client):
        headers = client._build_headers()
        assert "SBIR-Analytics" in headers["User-Agent"]
        assert "test@example.com" in headers["User-Agent"]


class TestSearchCompanies:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, client):
        mock_response = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "ciks": ["0000012345"],
                            "display_names": ["Acme Corp  (ACME)  (CIK 0000012345)"],
                            "file_date": "2024-01-15",
                            "root_forms": ["10-K"],
                        }
                    },
                    {
                        "_source": {
                            "ciks": ["0000067890"],
                            "display_names": ["Acme Industries  (CIK 0000067890)"],
                        }
                    },
                ]
            }
        }
        client._make_request = AsyncMock(return_value=mock_response)

        results = await client.search_companies("Acme Corp")
        assert len(results) == 2
        assert results[0]["cik"] == "12345"
        assert results[0]["entity_name"] == "Acme Corp"
        assert results[0]["ticker"] == "ACME"

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, client):
        mock_response = {
            "hits": {
                "hits": [
                    {"_source": {"ciks": [f"000000{i:04d}"], "display_names": [f"Co {i}  (CIK 000000{i:04d})"]}}
                    for i in range(20)
                ]
            }
        }
        client._make_request = AsyncMock(return_value=mock_response)

        results = await client.search_companies("Co", limit=5)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self, client):
        from sbir_etl.exceptions import APIError

        client._make_request = AsyncMock(
            side_effect=APIError("Server error", api_name="sec_edgar", http_status=500)
        )

        results = await client.search_companies("Acme")
        assert results == []


class TestSearchFilingMentions:
    @pytest.mark.asyncio
    async def test_search_returns_mentions(self, client):
        mock_response = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "ciks": ["0000099999"],
                            "display_names": ["Lockheed Martin  (LMT)  (CIK 0000099999)"],
                            "root_forms": ["8-K"],
                            "file_date": "2024-06-15",
                            "file_num": "0001-24-500",
                            "file_description": "Acquisition of Small Co",
                        }
                    },
                ]
            }
        }
        client._make_request = AsyncMock(return_value=mock_response)

        results = await client.search_filing_mentions("Small Co", forms="8-K")
        assert len(results) == 1
        assert results[0]["filer_cik"] == "99999"
        assert results[0]["filer_name"] == "Lockheed Martin"

    @pytest.mark.asyncio
    async def test_uses_exact_phrase(self, client):
        """Verify the company name is quoted for exact phrase matching."""
        client._make_request = AsyncMock(return_value={"hits": {"hits": []}})

        await client.search_filing_mentions("Acme Corp")
        call_args = client._make_request.call_args
        # _make_request(method, endpoint, params) — params is positional arg 3
        params = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get("params", {})
        assert params["q"] == '"Acme Corp"'

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, client):
        from sbir_etl.exceptions import APIError

        client._make_request = AsyncMock(
            side_effect=APIError("Error", api_name="sec_edgar", http_status=500)
        )
        results = await client.search_filing_mentions("Test")
        assert results == []


class TestSearchFormDFilings:
    @pytest.mark.asyncio
    async def test_finds_form_d(self, client):
        mock_response = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "ciks": ["0000055555"],
                            "display_names": ["Startup Inc  (CIK 0000055555)"],
                            "file_date": "2023-09-15",
                        }
                    },
                ]
            }
        }
        client._make_request = AsyncMock(return_value=mock_response)

        results = await client.search_form_d_filings("Startup Inc")
        assert len(results) == 1
        assert results[0]["cik"] == "55555"
        assert results[0]["form_type"] == "D"

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, client):
        from sbir_etl.exceptions import APIError

        client._make_request = AsyncMock(
            side_effect=APIError("Error", api_name="sec_edgar", http_status=500)
        )
        results = await client.search_form_d_filings("Test")
        assert results == []


class TestGetCompanyFacts:
    @pytest.mark.asyncio
    async def test_returns_facts(self, client, mock_http_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"cik": 12345, "facts": {"us-gaap": {}}}
        mock_resp.raise_for_status = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_resp)

        result = await client.get_company_facts("12345")
        assert result is not None
        assert result["cik"] == 12345

    @pytest.mark.asyncio
    async def test_returns_none_on_404(self, client, mock_http_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_http_client.get = AsyncMock(return_value=mock_resp)

        result = await client.get_company_facts("99999")
        assert result is None


class TestGetRecentFilings:
    @pytest.mark.asyncio
    async def test_returns_filings(self, client, mock_http_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "filings": {
                "recent": {
                    "form": ["10-K", "8-K", "10-Q"],
                    "filingDate": ["2024-03-15", "2024-02-01", "2024-01-15"],
                    "accessionNumber": ["0001-24-001", "0001-24-002", "0001-24-003"],
                    "primaryDocument": ["doc1.htm", "doc2.htm", "doc3.htm"],
                    "primaryDocDescription": ["Annual Report", "Current Report", "Quarterly"],
                }
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_resp)

        filings = await client.get_recent_filings("12345")
        assert len(filings) == 3
        assert filings[0]["form_type"] == "10-K"
        assert filings[1]["form_type"] == "8-K"

    @pytest.mark.asyncio
    async def test_filters_by_type(self, client, mock_http_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "filings": {
                "recent": {
                    "form": ["10-K", "8-K", "10-Q", "4"],
                    "filingDate": ["2024-03-15", "2024-02-01", "2024-01-15", "2024-01-10"],
                    "accessionNumber": ["001", "002", "003", "004"],
                    "primaryDocument": ["a", "b", "c", "d"],
                    "primaryDocDescription": ["a", "b", "c", "d"],
                }
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_resp)

        filings = await client.get_recent_filings("12345", filing_types=["8-K"])
        assert len(filings) == 1
        assert filings[0]["form_type"] == "8-K"

    @pytest.mark.asyncio
    async def test_returns_empty_on_404(self, client, mock_http_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_http_client.get = AsyncMock(return_value=mock_resp)

        filings = await client.get_recent_filings("99999")
        assert filings == []


class TestFetchFormDXml:
    @pytest.mark.asyncio
    async def test_fetch_form_d_xml_success(self, client, mock_http_client):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = (
            "<edgarSubmission><primaryIssuer><entityName>TEST</entityName>"
            "</primaryIssuer></edgarSubmission>"
        )
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await client.fetch_form_d_xml("1145986", "0001145986-11-000003")
        assert result is not None
        assert "<entityName>TEST</entityName>" in result

    @pytest.mark.asyncio
    async def test_fetch_form_d_xml_404_returns_none(self, client, mock_http_client):
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await client.fetch_form_d_xml("0000000", "0000000000-00-000000")
        assert result is None
