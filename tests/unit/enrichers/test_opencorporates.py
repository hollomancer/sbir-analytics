"""Tests for OpenCorporates client."""

from unittest.mock import Mock, patch

import pytest

from sbir_etl.enrichers.opencorporates import OpenCorporatesClient

pytestmark = pytest.mark.fast


class TestOpenCorporatesClient:
    def _mock_client(self) -> OpenCorporatesClient:
        # Provide a token so search_companies doesn't short-circuit on missing token
        client = OpenCorporatesClient(api_token="test_token")
        client._client = Mock()
        return client

    def test_lookup_company_success(self):
        client = self._mock_client()

        # Search response
        search_resp = Mock(status_code=200)
        search_resp.json.return_value = {
            "results": {
                "companies": [
                    {
                        "company": {
                            "name": "Acme Defense Systems LLC",
                            "jurisdiction_code": "us_va",
                            "company_number": "12345678",
                            "incorporation_date": "2015-03-12",
                            "current_status": "Active",
                            "company_type": "Limited Liability Company",
                            "opencorporates_url": "https://opencorporates.com/companies/us_va/12345678",
                        }
                    }
                ]
            }
        }

        # Detail response
        detail_resp = Mock(status_code=200)
        detail_resp.json.return_value = {
            "results": {
                "company": {
                    "name": "Acme Defense Systems LLC",
                    "jurisdiction_code": "us_va",
                    "company_number": "12345678",
                    "incorporation_date": "2015-03-12",
                    "dissolution_date": None,
                    "current_status": "Active",
                    "company_type": "Limited Liability Company",
                    "registered_address": {
                        "street_address": "123 Main St",
                        "locality": "Arlington",
                        "region": "VA",
                        "postal_code": "22201",
                    },
                    "agent_name": "John Smith",
                    "corporate_groupings": [
                        {
                            "corporate_grouping": {
                                "name": "Big Defense Corp",
                                "jurisdiction_code": "us_de",
                            }
                        }
                    ],
                    "opencorporates_url": "https://opencorporates.com/companies/us_va/12345678",
                }
            }
        }

        # Officers response
        officers_resp = Mock(status_code=200)
        officers_resp.json.return_value = {
            "results": {
                "officers": [
                    {
                        "officer": {
                            "name": "Jane Doe",
                            "position": "CEO",
                            "start_date": "2015-03-12",
                        }
                    },
                    {
                        "officer": {
                            "name": "John Smith",
                            "position": "Registered Agent",
                        }
                    },
                ]
            }
        }

        client._client.get.side_effect = [search_resp, detail_resp, officers_resp]

        rec = client.lookup_company("Acme Defense Systems")
        assert rec is not None
        assert rec.company_name == "Acme Defense Systems LLC"
        assert rec.jurisdiction == "us_va"
        assert rec.incorporation_date == "2015-03-12"
        assert rec.status == "Active"
        assert rec.parent_company == "Big Defense Corp"
        assert rec.parent_jurisdiction == "us_de"
        assert rec.registered_address == "123 Main St, Arlington, VA, 22201"
        assert rec.agent_name == "John Smith"
        assert len(rec.officers) == 2
        assert rec.officers[0].name == "Jane Doe"
        assert rec.officers[0].position == "CEO"

    def test_lookup_company_not_found(self):
        client = self._mock_client()
        resp = Mock(status_code=200)
        resp.json.return_value = {"results": {"companies": []}}
        client._client.get.return_value = resp

        assert client.lookup_company("Nonexistent Corp") is None

    def test_lookup_no_parent(self):
        client = self._mock_client()

        search_resp = Mock(status_code=200)
        search_resp.json.return_value = {
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

        detail_resp = Mock(status_code=200)
        detail_resp.json.return_value = {
            "results": {
                "company": {
                    "name": "Indie Startup",
                    "jurisdiction_code": "us_de",
                    "company_number": "99999",
                    "incorporation_date": "2020-01-15",
                    "current_status": "Active",
                    "corporate_groupings": [],
                }
            }
        }

        officers_resp = Mock(status_code=200)
        officers_resp.json.return_value = {"results": {"officers": []}}

        client._client.get.side_effect = [search_resp, detail_resp, officers_resp]

        rec = client.lookup_company("Indie Startup")
        assert rec is not None
        assert rec.parent_company is None
        assert rec.officers == []

    def test_search_with_jurisdiction(self):
        client = self._mock_client()
        resp = Mock(status_code=200)
        resp.json.return_value = {"results": {"companies": []}}
        client._client.get.return_value = resp

        client.search_companies("Test Corp", jurisdiction="us_va")
        call_args = client._client.get.call_args
        assert call_args[1]["params"]["jurisdiction_code"] == "us_va"

    @patch("sbir_etl.enrichers.opencorporates.time.sleep")
    def test_retry_on_429(self, mock_sleep):
        client = self._mock_client()

        resp_429 = Mock(status_code=429)
        resp_ok = Mock(status_code=200)
        resp_ok.json.return_value = {"results": {"companies": []}}

        client._client.get.side_effect = [resp_429, resp_ok]
        result = client.search_companies("Test")
        assert result == []
        assert client._client.get.call_count == 2
        mock_sleep.assert_called_once()

    def test_context_manager(self):
        with OpenCorporatesClient() as client:
            assert hasattr(client, "lookup_company")
