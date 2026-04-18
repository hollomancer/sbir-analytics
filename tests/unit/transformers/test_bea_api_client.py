"""Unit tests for the BEA API client."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from sbir_etl.exceptions import APIError, ConfigurationError


pytestmark = pytest.mark.fast


class TestBEAApiClientInit:
    """Test BEA API client initialization."""

    def test_init_no_api_key(self):
        """Test that missing API key raises ConfigurationError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigurationError, match="BEA_API_KEY not set"):
                from sbir_etl.transformers.bea_api_client import BEAApiClient

                BEAApiClient(api_key="")

    def test_init_with_api_key(self):
        """Test successful initialization with API key."""
        from sbir_etl.transformers.bea_api_client import BEAApiClient

        client = BEAApiClient(api_key="test-key-123")
        assert client.api_key == "test-key-123"
        client.close()

    def test_init_from_env(self):
        """Test initialization reads from environment."""
        with patch.dict("os.environ", {"BEA_API_KEY": "env-key-456"}):
            from sbir_etl.transformers.bea_api_client import BEAApiClient

            client = BEAApiClient()
            assert client.api_key == "env-key-456"
            client.close()


class TestBEAApiClientRequests:
    """Test BEA API client request handling."""

    def test_rows_to_dataframe(self):
        """Test parsing BEA API response rows."""
        from sbir_etl.transformers.bea_api_client import BEAApiClient

        data = {
            "BEAAPI": {
                "Results": {
                    "Data": [
                        {"RowCode": "11", "ColCode": "21", "DataValue": "100"},
                        {"RowCode": "21", "ColCode": "11", "DataValue": "50"},
                    ]
                }
            }
        }

        df = BEAApiClient._rows_to_dataframe(data)
        assert len(df) == 2
        assert "RowCode" in df.columns
        assert "DataValue" in df.columns

    def test_rows_to_dataframe_empty(self):
        """Test parsing empty BEA API response."""
        from sbir_etl.transformers.bea_api_client import BEAApiClient

        data = {"BEAAPI": {"Results": {"Data": []}}}
        df = BEAApiClient._rows_to_dataframe(data)
        assert df.empty

    @patch("httpx.Client.get")
    def test_request_success(self, mock_get):
        """Test successful API request."""
        from sbir_etl.transformers.bea_api_client import BEAApiClient

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "BEAAPI": {
                "Results": {
                    "Data": [{"RowCode": "11", "DataValue": "100"}]
                }
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = BEAApiClient(api_key="test-key")
        result = client._request({"method": "GetData", "DataSetName": "InputOutput"})

        assert "BEAAPI" in result
        client.close()

    @patch("httpx.Client.get")
    def test_request_bea_error(self, mock_get):
        """Test BEA API-level error handling."""
        from sbir_etl.transformers.bea_api_client import BEAApiClient

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "BEAAPI": {
                "Results": {
                    "Error": {"APIErrorCode": "40", "APIErrorDescription": "Invalid table"}
                }
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = BEAApiClient(api_key="test-key")
        with pytest.raises(APIError, match="BEA API error"):
            client._request({"method": "GetData"})
        client.close()


class TestBEAApiClientTableAccessors:
    """Test high-level table accessor methods."""

    @patch("httpx.Client.get")
    def test_get_use_table(self, mock_get):
        """Test get_use_table method."""
        from sbir_etl.transformers.bea_api_client import BEAApiClient

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "BEAAPI": {
                "Results": {
                    "Data": [
                        {"RowCode": "11", "ColCode": "21", "DataValue": "100"},
                    ]
                }
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = BEAApiClient(api_key="test-key")
        df = client.get_use_table(year=2020)

        assert len(df) == 1
        assert df.iloc[0]["RowCode"] == "11"
        client.close()


class TestStateFIPS:
    """Test state FIPS code mapping."""

    def test_common_states(self):
        """Test FIPS codes for common states."""
        from sbir_etl.transformers.bea_api_client import STATE_FIPS

        assert STATE_FIPS["CA"] == "06"
        assert STATE_FIPS["NY"] == "36"
        assert STATE_FIPS["TX"] == "48"
        assert STATE_FIPS["DC"] == "11"

    def test_all_50_states_plus_dc(self):
        """Test that we have all 50 states + DC."""
        from sbir_etl.transformers.bea_api_client import STATE_FIPS

        # 50 states + DC + PR = 52
        assert len(STATE_FIPS) == 52
