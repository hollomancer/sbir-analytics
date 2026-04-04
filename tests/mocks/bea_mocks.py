"""Mock factories for BEA I-O adapter testing."""

from unittest.mock import MagicMock

import pandas as pd


class BEAMocks:
    """Factory for creating mock BEA API objects for testing."""

    @staticmethod
    def mock_bea_use_table() -> pd.DataFrame:
        """Create a mock BEA Use table API response."""
        return pd.DataFrame([
            {"RowCode": "11", "ColCode": "11", "DataValue": "10", "RowDescription": "Ag", "ColDescription": "Ag"},
            {"RowCode": "11", "ColCode": "21", "DataValue": "20", "RowDescription": "Ag", "ColDescription": "Mining"},
            {"RowCode": "21", "ColCode": "11", "DataValue": "5", "RowDescription": "Mining", "ColDescription": "Ag"},
            {"RowCode": "21", "ColCode": "21", "DataValue": "10", "RowDescription": "Mining", "ColDescription": "Mining"},
        ])

    @staticmethod
    def mock_bea_va_table() -> pd.DataFrame:
        """Create a mock BEA Value Added API response."""
        return pd.DataFrame([
            {"ColCode": "11", "RowDescription": "Compensation of employees", "DataValue": "400"},
            {"ColCode": "11", "RowDescription": "Gross operating surplus", "DataValue": "300"},
            {"ColCode": "11", "RowDescription": "Taxes on production", "DataValue": "150"},
            {"ColCode": "11", "RowDescription": "Total value added", "DataValue": "850"},
            {"ColCode": "21", "RowDescription": "Compensation of employees", "DataValue": "200"},
            {"ColCode": "21", "RowDescription": "Gross operating surplus", "DataValue": "150"},
            {"ColCode": "21", "RowDescription": "Taxes on production", "DataValue": "75"},
            {"ColCode": "21", "RowDescription": "Total value added", "DataValue": "425"},
        ])

    @staticmethod
    def mock_bea_employment_table() -> pd.DataFrame:
        """Create a mock BEA Employment API response."""
        return pd.DataFrame([
            {"ColCode": "11", "DataValue": "2000", "RowDescription": "Employment"},
            {"ColCode": "21", "DataValue": "1000", "RowDescription": "Employment"},
        ])
