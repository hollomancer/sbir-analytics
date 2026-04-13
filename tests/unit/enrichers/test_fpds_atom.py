"""Tests for the FPDS Atom Feed client (async) and SyncFPDSAtomClient.

After the migration to :class:`BaseAsyncAPIClient`, the client is
async-first and a thin sync facade lives in ``sync_wrappers.py``.
The pure parsing helpers (``_find_local``, ``_parse_entry``) are
module-level and unchanged.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import pytest

from sbir_etl.enrichers.fpds_atom import (
    ATOM_NS,
    FPDSAtomClient,
    FPDSRecord,
    _find_local,
    _parse_entry,
)
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.enrichers.sync_wrappers import SyncFPDSAtomClient

pytestmark = pytest.mark.fast


# ==================== Sample XML ====================

SAMPLE_ATOM_ENTRY = """\
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>SBIR PHASE I: Advanced Sensor</title>
    <content type="application/xml">
      <award xmlns:ns1="https://www.fpds.gov/FPDS">
        <ns1:PIID>FA2541-26-C-B005</ns1:PIID>
        <ns1:descriptionOfContractRequirement>Develop advanced sensor</ns1:descriptionOfContractRequirement>
        <ns1:research>SR1</ns1:research>
        <ns1:vendorName>Acme Corp</ns1:vendorName>
        <ns1:UEINumber>ABC123DEF456</ns1:UEINumber>
        <ns1:productOrServiceCode>AC12</ns1:productOrServiceCode>
        <ns1:principalNAICSCode>541715</ns1:principalNAICSCode>
        <ns1:obligatedAmount>150000.00</ns1:obligatedAmount>
        <ns1:signedDate>2026-01-15</ns1:signedDate>
        <ns1:ultimateCompletionDate>2027-01-15</ns1:ultimateCompletionDate>
        <ns1:solicitationID>SOL-001</ns1:solicitationID>
      </award>
    </content>
  </entry>
</feed>"""

EMPTY_FEED = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'

TITLE_ONLY_ENTRY = """\
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Contract title as fallback</title>
  </entry>
</feed>"""


# ==================== Parsing Tests (unchanged) ====================


class TestFindLocal:
    def test_finds_namespaced_element(self):
        xml = '<root><ns:child xmlns:ns="http://example.com">text</ns:child></root>'
        root = ET.fromstring(xml)
        el = _find_local(root, "child")
        assert el is not None
        assert el.text == "text"

    def test_finds_unnamespaced_element(self):
        xml = "<root><child>text</child></root>"
        root = ET.fromstring(xml)
        el = _find_local(root, "child")
        assert el is not None
        assert el.text == "text"

    def test_returns_none_for_missing(self):
        xml = "<root><other>text</other></root>"
        root = ET.fromstring(xml)
        assert _find_local(root, "child") is None


class TestParseEntry:
    @pytest.fixture
    def entry(self):
        root = ET.fromstring(SAMPLE_ATOM_ENTRY)
        return root.find("atom:entry", ATOM_NS)

    def test_extracts_description(self, entry):
        record = _parse_entry(entry, "FA2541-26-C-B005")
        assert record.description == "Develop advanced sensor"

    def test_extracts_research_code(self, entry):
        record = _parse_entry(entry, "FA2541-26-C-B005")
        assert record.research_code == "SR1"

    def test_extracts_vendor_info(self, entry):
        record = _parse_entry(entry, "FA2541-26-C-B005")
        assert record.vendor_name == "Acme Corp"
        assert record.vendor_uei == "ABC123DEF456"

    def test_extracts_classification(self, entry):
        record = _parse_entry(entry, "FA2541-26-C-B005")
        assert record.psc_code == "AC12"
        assert record.naics_code == "541715"

    def test_extracts_financial(self, entry):
        record = _parse_entry(entry, "FA2541-26-C-B005")
        assert record.obligated_amount == 150000.0

    def test_extracts_dates(self, entry):
        record = _parse_entry(entry, "FA2541-26-C-B005")
        assert record.signed_date == "2026-01-15"
        assert record.completion_date == "2027-01-15"

    def test_extracts_solicitation(self, entry):
        record = _parse_entry(entry, "FA2541-26-C-B005")
        assert record.solicitation_id == "SOL-001"

    def test_title_fallback_when_no_content(self):
        root = ET.fromstring(TITLE_ONLY_ENTRY)
        entry = root.find("atom:entry", ATOM_NS)
        record = _parse_entry(entry, "TEST-001")
        assert record.description == "Contract title as fallback"
        assert record.research_code is None

    def test_empty_feed_returns_none_from_client(self):
        root = ET.fromstring(EMPTY_FEED)
        entry = root.find("atom:entry", ATOM_NS)
        assert entry is None


# ==================== Async client tests ====================


def _mock_response(status: int = 200, text: str = "") -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.text = text
    resp.raise_for_status = Mock()
    return resp


@pytest.fixture
def mock_http_client() -> AsyncMock:
    mock = AsyncMock(spec=httpx.AsyncClient)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def client(mock_http_client: AsyncMock) -> FPDSAtomClient:
    return FPDSAtomClient(http_client=mock_http_client)


class TestInitialization:
    def test_defaults(self, client: FPDSAtomClient) -> None:
        assert client.api_name == "fpds_atom"
        assert client.base_url == "https://www.fpds.gov/ezsearch"
        assert client.rate_limit_per_minute == 60

    def test_inherits_from_base(self, client: FPDSAtomClient) -> None:
        from sbir_etl.enrichers.base_client import BaseAsyncAPIClient

        assert isinstance(client, BaseAsyncAPIClient)


class TestSharedLimiterOverride:
    async def test_shared_limiter_invoked(
        self, mock_http_client: AsyncMock
    ) -> None:
        shared = RateLimiter(rate_limit_per_minute=30)
        shared.wait_if_needed = MagicMock()  # type: ignore[method-assign]
        c = FPDSAtomClient(shared_limiter=shared, http_client=mock_http_client)
        mock_http_client.get.return_value = _mock_response(200, EMPTY_FEED)

        await c.search_by_piid("ANY")

        shared.wait_if_needed.assert_called_once()

    async def test_shared_limiter_absent_uses_base_limiter(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, EMPTY_FEED)
        assert client.request_times == []
        await client.search_by_piid("ANY")
        assert len(client.request_times) == 1


class TestSearchByPiid:
    async def test_success_returns_parsed_record(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_ATOM_ENTRY)

        record = await client.search_by_piid("FA2541-26-C-B005")

        assert record is not None
        assert record.description == "Develop advanced sensor"
        assert record.research_code == "SR1"
        assert record.vendor_name == "Acme Corp"

    async def test_empty_feed_returns_none(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, EMPTY_FEED)

        record = await client.search_by_piid("NONEXISTENT")

        assert record is None

    async def test_api_error_returns_none(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        """APIError from the base layer is caught — public API preserves None contract."""
        resp = Mock()
        resp.status_code = 500
        resp.text = "server error"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        record = await client.search_by_piid("ANY")

        assert record is None

    async def test_404_returns_none(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 404
        resp.text = "not found"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "404", request=Mock(), response=resp
        )

        record = await client.search_by_piid("GONE")

        assert record is None

    async def test_malformed_xml_returns_none(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, "<not-xml")

        record = await client.search_by_piid("ANY")

        assert record is None

    async def test_query_builds_both_piid_and_ref_idv_piid(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, EMPTY_FEED)

        await client.search_by_piid("TEST-001")

        call_kwargs = mock_http_client.get.call_args[1]
        query = call_kwargs["params"]["q"]
        assert 'PIID:"TEST-001"' in query
        assert 'REF_IDV_PIID:"TEST-001"' in query


class TestSearchByVendor:
    async def test_with_uei(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_ATOM_ENTRY)

        records = await client.search_by_vendor(uei="ABC123DEF456")

        assert len(records) == 1
        call_kwargs = mock_http_client.get.call_args[1]
        assert "VENDOR_UEI_NUMBER" in call_kwargs["params"]["q"]

    async def test_with_name(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, EMPTY_FEED)

        await client.search_by_vendor(name="Acme Corp")

        call_kwargs = mock_http_client.get.call_args[1]
        assert "VENDOR_FULL_NAME" in call_kwargs["params"]["q"]

    async def test_no_criteria_returns_empty(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        result = await client.search_by_vendor()
        assert result == []
        mock_http_client.get.assert_not_called()


class TestConvenienceMethods:
    async def test_get_description(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_ATOM_ENTRY)

        desc = await client.get_description("FA2541-26-C-B005")

        assert desc == "Develop advanced sensor"

    async def test_get_research_code(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_ATOM_ENTRY)

        code = await client.get_research_code("FA2541-26-C-B005")

        assert code == "SR1"

    async def test_get_descriptions_batch(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_ATOM_ENTRY)

        result = await client.get_descriptions(["PIID-1", "PIID-2"])

        # Same sample data returns for both PIIDs since they share a mock response
        assert "PIID-1" in result
        assert "PIID-2" in result

    async def test_get_descriptions_truncates_long(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        long_desc = "x" * 600
        xml = f"""<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <content type="application/xml">
      <award xmlns:ns1="https://www.fpds.gov/FPDS">
        <ns1:descriptionOfContractRequirement>{long_desc}</ns1:descriptionOfContractRequirement>
      </award>
    </content>
  </entry>
</feed>"""
        mock_http_client.get.return_value = _mock_response(200, xml)

        result = await client.get_descriptions(["TEST"])

        assert result["TEST"].endswith("...")
        assert len(result["TEST"]) == 503  # 500 + "..."

    async def test_get_descriptions_skips_missing(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, EMPTY_FEED)

        result = await client.get_descriptions(["GHOST"])

        assert result == {}


class TestLifecycle:
    async def test_aclose_delegates_to_http_client(
        self, client: FPDSAtomClient, mock_http_client: AsyncMock
    ) -> None:
        await client.aclose()
        mock_http_client.aclose.assert_awaited_once()


# ==================== Sync facade ====================


class TestSyncFacade:
    def test_context_manager(self) -> None:
        with SyncFPDSAtomClient() as client:
            assert hasattr(client, "search_by_piid")
            assert hasattr(client, "get_descriptions")

    def test_search_by_piid_delegates_to_async(self) -> None:
        with SyncFPDSAtomClient() as client:
            client._client.search_by_piid = AsyncMock(  # type: ignore[method-assign]
                return_value=FPDSRecord(piid="X", description="hello")
            )

            record = client.search_by_piid("X")

            assert record is not None
            assert record.description == "hello"
            client._client.search_by_piid.assert_awaited_once_with("X")

    def test_get_descriptions_delegates(self) -> None:
        with SyncFPDSAtomClient() as client:
            client._client.get_descriptions = AsyncMock(  # type: ignore[method-assign]
                return_value={"A": "desc A"}
            )

            result = client.get_descriptions(["A"])

            assert result == {"A": "desc A"}
            client._client.get_descriptions.assert_awaited_once_with(["A"])

    def test_shared_limiter_plumbs_through(self) -> None:
        shared = RateLimiter(rate_limit_per_minute=50)
        with SyncFPDSAtomClient(shared_limiter=shared) as client:
            assert client._client._shared_limiter is shared
