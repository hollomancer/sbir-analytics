"""Tests for ORCID client."""

from unittest.mock import Mock

import pytest

from sbir_etl.enrichers.orcid_client import ORCIDClient, ORCIDRecord, _parse_profile

pytestmark = pytest.mark.fast


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


class TestParseProfile:
    def test_extracts_affiliations(self):
        rec = _parse_profile("0000-0001", {"given-names": "Jane", "family-names": "Doe"}, SAMPLE_PROFILE)
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


class TestORCIDClient:
    def test_lookup_success(self):
        mock_http = Mock()
        # Search response
        search_resp = Mock()
        search_resp.status_code = 200
        search_resp.json.return_value = {
            "expanded-result": [
                {"orcid-id": "0000-0001", "given-names": "Jane", "family-names": "Doe"}
            ]
        }
        # Profile response
        profile_resp = Mock()
        profile_resp.status_code = 200
        profile_resp.json.return_value = SAMPLE_PROFILE

        mock_http.get.side_effect = [search_resp, profile_resp]

        client = ORCIDClient()
        client._client = mock_http
        rec = client.lookup("Jane Doe")

        assert rec is not None
        assert rec.orcid_id == "0000-0001"
        assert rec.works_count == 2

    def test_lookup_not_found(self):
        mock_http = Mock()
        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = {"expanded-result": []}
        mock_http.get.return_value = resp

        client = ORCIDClient()
        client._client = mock_http
        assert client.lookup("Nobody") is None

    def test_context_manager(self):
        with ORCIDClient() as client:
            assert hasattr(client, "lookup")

    def test_orcid_record_fields(self):
        rec = ORCIDRecord(orcid_id="0000-0001", works_count=5, funding_count=2)
        assert rec.orcid_id == "0000-0001"
