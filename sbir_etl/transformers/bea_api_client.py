"""BEA (Bureau of Economic Analysis) API client for I-O table retrieval.

Fetches Input-Output tables directly from the BEA REST API, replacing the
previous R/StateIO dependency with pure Python.

BEA API docs: https://apps.bea.gov/api/
Registration: https://apps.bea.gov/API/signup/

Required environment variable: BEA_API_KEY
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..exceptions import APIError, ConfigurationError

BEA_API_BASE_URL = "https://apps.bea.gov/api/data"

# BEA I-O table IDs used for economic impact analysis
# See: https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf
TABLE_IDS = {
    "use_summary": "259",       # Use table (Summary level, after redefinitions)
    "make_summary": "260",      # Make table (Summary level, after redefinitions)
    "va_summary": "261",        # Value Added by Industry (Summary)
    "employment": "262",        # Employment by Industry (Summary)
    "supply_summary": "256",    # Supply table (Summary)
}


class BEAApiClient:
    """Synchronous client for the BEA REST API.

    Fetches national-level Input-Output tables (Use, Make, Value Added,
    Employment) that were previously obtained via the EPA StateIO R package.

    Usage:
        >>> client = BEAApiClient()  # reads BEA_API_KEY from env
        >>> use_table = client.get_use_table(year=2020)
        >>> va_data = client.get_value_added(year=2020)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BEA_API_BASE_URL,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or os.environ.get("BEA_API_KEY", "")
        if not self.api_key:
            raise ConfigurationError(
                "BEA_API_KEY not set. Register at https://apps.bea.gov/API/signup/",
                component="transformer.bea_api_client",
                operation="init",
            )
        self.base_url = base_url
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BEAApiClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Low-level request
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True,
    )
    def _request(self, params: dict[str, str]) -> dict[str, Any]:
        """Make a request to the BEA API.

        Args:
            params: Query parameters (excluding UserID and ResultFormat).

        Returns:
            Parsed JSON response dict.
        """
        full_params = {
            "UserID": self.api_key,
            "ResultFormat": "JSON",
            **params,
        }
        resp = self._client.get(self.base_url, params=full_params)
        resp.raise_for_status()
        data = resp.json()

        # BEA wraps responses; detect API-level errors
        bea_resp = data.get("BEAAPI", {}).get("Results", {})
        if "Error" in bea_resp:
            error_detail = bea_resp["Error"]
            raise APIError(
                f"BEA API error: {error_detail}",
                component="transformer.bea_api_client",
                operation="_request",
                details={"bea_error": str(error_detail), "params": params},
            )

        return data

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rows_to_dataframe(data: dict[str, Any]) -> pd.DataFrame:
        """Extract the Data rows from a BEA API response into a DataFrame."""
        results = data.get("BEAAPI", {}).get("Results", {})

        # Handle both single-result and multi-result formats
        if isinstance(results, list):
            rows = results
        elif isinstance(results, dict):
            rows = results.get("Data", [])
        else:
            rows = []

        if not rows:
            logger.warning("BEA API returned no data rows")
            return pd.DataFrame()

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Public table accessors
    # ------------------------------------------------------------------

    def get_io_table(self, table_id: str, year: int | str) -> pd.DataFrame:
        """Fetch a BEA Input-Output table by table ID.

        Args:
            table_id: BEA table ID (see TABLE_IDS).
            year: Data year (or "All" for all available).

        Returns:
            DataFrame of table rows from the API.
        """
        params = {
            "method": "GetData",
            "DataSetName": "InputOutput",
            "TableID": table_id,
            "Year": str(year),
        }
        logger.debug(f"Fetching BEA I-O table {table_id} for year {year}")
        data = self._request(params)
        return self._rows_to_dataframe(data)

    def get_use_table(self, year: int = 2020) -> pd.DataFrame:
        """Fetch the Use table (Summary level, after redefinitions).

        Returns a DataFrame with columns like:
        RowCode, ColCode, DataValue, RowDescription, ColDescription, etc.
        """
        return self.get_io_table(TABLE_IDS["use_summary"], year)

    def get_make_table(self, year: int = 2020) -> pd.DataFrame:
        """Fetch the Make table (Summary level, after redefinitions)."""
        return self.get_io_table(TABLE_IDS["make_summary"], year)

    def get_value_added_table(self, year: int = 2020) -> pd.DataFrame:
        """Fetch the Value Added by Industry table (Summary level)."""
        return self.get_io_table(TABLE_IDS["va_summary"], year)

    def get_employment_table(self, year: int = 2020) -> pd.DataFrame:
        """Fetch Employment by Industry (Summary level)."""
        return self.get_io_table(TABLE_IDS["employment"], year)

    def get_regional_gdp(
        self,
        state_fips: str,
        year: int = 2020,
        industry: str = "ALL",
    ) -> pd.DataFrame:
        """Fetch Regional GDP data for a state (used for state-level scaling).

        Args:
            state_fips: Two-digit FIPS code (e.g. "06" for CA).
            year: Data year.
            industry: Industry filter ("ALL" for all industries).

        Returns:
            DataFrame with regional GDP by industry.
        """
        params = {
            "method": "GetData",
            "DataSetName": "Regional",
            "TableName": "SAGDP2N",
            "GeoFIPS": state_fips,
            "LineCode": "1",
            "Year": str(year),
        }
        logger.debug(f"Fetching Regional GDP for FIPS {state_fips}, year {year}")
        data = self._request(params)
        return self._rows_to_dataframe(data)


# State abbreviation → FIPS code mapping (for regional queries)
STATE_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
    "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
    "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
    "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
    "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
    "DC": "11", "PR": "72",
}
