"""Tests for FPDS Atom Feed client."""

import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

import httpx
import pytest

from sbir_etl.enrichers.fpds_atom import (
    ATOM_NS,
    FPDSAtomClient,
    FPDSRecord,
    _find_local,
    _parse_entry,
    _text,
)

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


# ==================== Parsing Tests ====================


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
        assert entry is None  # No entry to parse


# ==================== Client Tests ====================


class TestFPDSAtomClient:
    def test_default_config(self):
        client = FPDSAtomClient()
        assert client._timeout == 30
        assert client._limiter is None

    def test_custom_config(self):
        limiter = Mock()
        client = FPDSAtomClient(rate_limiter=limiter, timeout=60)
        assert client._timeout == 60
        assert client._limiter is limiter

    def test_search_by_piid_success(self):
        client = FPDSAtomClient()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_ATOM_ENTRY

        with patch.object(client, "_get", return_value=mock_resp):
            record = client.search_by_piid("FA2541-26-C-B005")

        assert record is not None
        assert record.description == "Develop advanced sensor"
        assert record.research_code == "SR1"

    def test_search_by_piid_not_found(self):
        client = FPDSAtomClient()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = EMPTY_FEED

        with patch.object(client, "_get", return_value=mock_resp):
            record = client.search_by_piid("NONEXISTENT")

        assert record is None

    def test_search_by_piid_api_failure(self):
        client = FPDSAtomClient()

        with patch.object(client, "_get", return_value=None):
            record = client.search_by_piid("FA2541-26-C-B005")

        assert record is None

    def test_get_description(self):
        client = FPDSAtomClient()
        mock_record = FPDSRecord(piid="TEST", description="Test description")

        with patch.object(client, "search_by_piid", return_value=mock_record):
            desc = client.get_description("TEST")

        assert desc == "Test description"

    def test_get_research_code(self):
        client = FPDSAtomClient()
        mock_record = FPDSRecord(piid="TEST", research_code="SR2")

        with patch.object(client, "search_by_piid", return_value=mock_record):
            code = client.get_research_code("TEST")

        assert code == "SR2"

    def test_get_descriptions_batch(self):
        client = FPDSAtomClient()
        records = {
            "PIID-1": FPDSRecord(piid="PIID-1", description="Desc 1"),
            "PIID-2": FPDSRecord(piid="PIID-2", description="Desc 2"),
            "PIID-3": FPDSRecord(piid="PIID-3", description=None),
        }

        def mock_search(piid):
            return records.get(piid)

        with patch.object(client, "search_by_piid", side_effect=mock_search):
            result = client.get_descriptions(["PIID-1", "PIID-2", "PIID-3"])

        assert result == {"PIID-1": "Desc 1", "PIID-2": "Desc 2"}

    def test_get_descriptions_truncates_long(self):
        client = FPDSAtomClient()
        long_desc = "x" * 600
        mock_record = FPDSRecord(piid="TEST", description=long_desc)

        with patch.object(client, "search_by_piid", return_value=mock_record):
            result = client.get_descriptions(["TEST"])

        assert result["TEST"].endswith("...")
        assert len(result["TEST"]) == 503  # 500 + "..."

    def test_rate_limiter_called(self):
        limiter = Mock()
        client = FPDSAtomClient(rate_limiter=limiter)

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = EMPTY_FEED

        with patch("sbir_etl.enrichers.fpds_atom.httpx.Client") as mock_client_cls:
            mock_http = Mock()
            mock_http.get.return_value = mock_resp
            mock_http.__enter__ = Mock(return_value=mock_http)
            mock_http.__exit__ = Mock(return_value=False)
            mock_client_cls.return_value = mock_http

            client.search_by_piid("TEST")

        limiter.wait_if_needed.assert_called()

    def test_search_by_vendor_with_uei(self):
        client = FPDSAtomClient()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_ATOM_ENTRY

        with patch.object(client, "_get", return_value=mock_resp) as mock_get:
            records = client.search_by_vendor(uei="ABC123DEF456")

        assert len(records) == 1
        call_args = mock_get.call_args[0][0]
        assert "VENDOR_UEI_NUMBER" in call_args["q"]
