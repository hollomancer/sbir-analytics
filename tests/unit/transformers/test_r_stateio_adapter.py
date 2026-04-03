"""Unit tests for BEA I-O adapter (replaces R StateIO adapter tests)."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tests.mocks import RMocks


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_shocks():
    """Create sample shocks DataFrame for testing."""
    return pd.DataFrame(
        {
            "state": ["CA", "NY", "TX"],
            "bea_sector": ["11", "21", "31"],
            "fiscal_year": [2023, 2023, 2023],
            "shock_amount": [
                Decimal("1000000"),
                Decimal("500000"),
                Decimal("750000"),
            ],
        }
    )


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    from tests.utils.config_mocks import create_mock_pipeline_config

    config = create_mock_pipeline_config()
    if hasattr(config, "fiscal_analysis"):
        config.fiscal_analysis.stateio_model_version = "v2.1"
    config.stateio_model_version = "v2.1"
    return config


class TestBEAIOAdapterInitialization:
    """Test BEAIOAdapter initialization."""

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    def test_init_success(self, mock_client_cls, mock_config):
        """Test successful initialization with BEA API key set."""
        mock_client_cls.return_value = MagicMock()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config)
        assert adapter._api_available is True
        assert adapter.cache_enabled is True
        assert adapter.model_version == "v2.1"

    @patch(
        "sbir_etl.transformers.bea_io_adapter.BEAApiClient",
        side_effect=__import__("sbir_etl.exceptions", fromlist=["ConfigurationError"]).ConfigurationError(
            "BEA_API_KEY not set", component="test", operation="test"
        ),
    )
    def test_init_no_api_key(self, mock_client_cls, mock_config):
        """Test initialization falls back when BEA_API_KEY not set."""
        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config)
        assert adapter._api_available is False

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    def test_init_custom_cache_dir(self, mock_client_cls, mock_config, tmp_path):
        """Test initialization with custom cache directory."""
        mock_client_cls.return_value = MagicMock()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        cache_dir = tmp_path / "custom_cache"
        adapter = BEAIOAdapter(config=mock_config, cache_dir=str(cache_dir))

        assert adapter.cache_dir == cache_dir
        assert cache_dir.exists()


class TestBEAIOAdapterCaching:
    """Test caching functionality."""

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    def test_cache_key_generation(self, mock_client_cls, mock_config, sample_shocks):
        """Test cache key generation."""
        mock_client_cls.return_value = MagicMock()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config)
        cache_key = adapter._get_cache_key(sample_shocks)

        assert cache_key.startswith("bea_io_v2.1_")
        assert len(cache_key) > 15

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    def test_cache_hit(self, mock_client_cls, mock_config, sample_shocks, tmp_path):
        """Test cache hit scenario."""
        mock_client_cls.return_value = MagicMock()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        cache_dir = tmp_path / "cache"
        adapter = BEAIOAdapter(config=mock_config, cache_dir=str(cache_dir))

        cache_key = adapter._get_cache_key(sample_shocks)
        cached_result = sample_shocks.copy()
        cached_result["wage_impact"] = Decimal("100000")
        adapter._save_to_cache(cache_key, cached_result)

        loaded = adapter._load_from_cache(cache_key)
        assert loaded is not None
        assert "wage_impact" in loaded.columns

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    def test_cache_miss(self, mock_client_cls, mock_config):
        """Test cache miss scenario."""
        mock_client_cls.return_value = MagicMock()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config)
        result = adapter._load_from_cache("nonexistent_key")
        assert result is None


class TestBEAIOAdapterImpactComputation:
    """Test impact computation logic."""

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    def test_compute_placeholder_impacts(self, mock_client_cls, mock_config, sample_shocks):
        """Test placeholder computation when API unavailable."""
        from sbir_etl.exceptions import ConfigurationError

        mock_client_cls.side_effect = ConfigurationError(
            "BEA_API_KEY not set", component="test", operation="test"
        )

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config, cache_enabled=False)
        result = adapter._compute_impacts_bea(sample_shocks)

        assert len(result) == 3
        assert "wage_impact" in result.columns
        assert result["quality_flags"].iloc[0] == "placeholder_computation"

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    @patch("sbir_etl.transformers.bea_io_adapter.fetch_use_table")
    @patch("sbir_etl.transformers.bea_io_adapter.fetch_value_added")
    @patch("sbir_etl.transformers.bea_io_adapter.calculate_value_added_ratios")
    def test_compute_impacts_via_bea(
        self,
        mock_va_ratios,
        mock_fetch_va,
        mock_fetch_use,
        mock_client_cls,
        mock_config,
        sample_shocks,
    ):
        """Test BEA I-O computation path."""
        mock_client_cls.return_value = MagicMock()

        # Mock a simple 3-sector Use table
        mock_fetch_use.return_value = pd.DataFrame(
            [[10, 5, 3], [5, 10, 2], [3, 2, 10]],
            index=["11", "21", "31"],
            columns=["11", "21", "31"],
            dtype=float,
        )
        mock_fetch_va.return_value = pd.DataFrame()
        mock_va_ratios.return_value = pd.DataFrame()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config, cache_enabled=False)
        result = adapter._compute_impacts_bea(sample_shocks)

        assert len(result) == 3
        assert "wage_impact" in result.columns
        assert "production_impact" in result.columns
        assert result["model_version"].iloc[0] == "v2.1"

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    def test_ensure_impact_columns(self, mock_client_cls, mock_config, sample_shocks):
        """Test _ensure_impact_columns adds missing columns."""
        mock_client_cls.return_value = MagicMock()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        incomplete_result = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                "fiscal_year": [2023],
                "wage_impact": [400000.0],
            }
        )

        adapter = BEAIOAdapter(config=mock_config)
        complete_result = adapter._ensure_impact_columns(
            incomplete_result, sample_shocks.head(1), "v2.1"
        )

        required_cols = [
            "wage_impact",
            "proprietor_income_impact",
            "gross_operating_surplus",
            "consumption_impact",
            "tax_impact",
            "production_impact",
        ]
        for col in required_cols:
            assert col in complete_result.columns

        assert complete_result["model_version"].iloc[0] == "v2.1"


class TestBEAIOAdapterIntegration:
    """Test full compute_impacts integration."""

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    @patch("sbir_etl.transformers.bea_io_adapter.fetch_use_table")
    @patch("sbir_etl.transformers.bea_io_adapter.fetch_value_added")
    @patch("sbir_etl.transformers.bea_io_adapter.calculate_value_added_ratios")
    def test_compute_impacts_with_cache(
        self,
        mock_va_ratios,
        mock_fetch_va,
        mock_fetch_use,
        mock_client_cls,
        mock_config,
        sample_shocks,
        tmp_path,
    ):
        """Test compute_impacts uses cache when available."""
        mock_client_cls.return_value = MagicMock()
        mock_fetch_use.return_value = pd.DataFrame(
            [[10, 5, 3], [5, 10, 2], [3, 2, 10]],
            index=["11", "21", "31"],
            columns=["11", "21", "31"],
            dtype=float,
        )
        mock_fetch_va.return_value = pd.DataFrame()
        mock_va_ratios.return_value = pd.DataFrame()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(
            config=mock_config, cache_enabled=True, cache_dir=str(tmp_path)
        )

        result1 = adapter.compute_impacts(sample_shocks)
        assert len(result1) == 3

        mock_fetch_use.reset_mock()

        result2 = adapter.compute_impacts(sample_shocks)
        assert len(result2) == 3
        assert mock_fetch_use.call_count == 0

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    def test_validate_input(self, mock_client_cls, mock_config, sample_shocks):
        """Test input validation."""
        mock_client_cls.return_value = MagicMock()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config)

        adapter.validate_input(sample_shocks)

        invalid_shocks = sample_shocks.drop(columns=["state"])
        with pytest.raises(Exception, match="Missing required columns"):
            adapter.validate_input(invalid_shocks)

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    def test_is_available(self, mock_client_cls, mock_config):
        """Test is_available check."""
        mock_client_cls.return_value = MagicMock()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config)
        assert adapter.is_available() is True

    def test_backward_compat_import(self):
        """Test that the old import path still works."""
        from sbir_etl.transformers.r_stateio_adapter import RStateIOAdapter, RPY2_AVAILABLE

        assert RPY2_AVAILABLE is True
        # RStateIOAdapter is now an alias for BEAIOAdapter
        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        assert RStateIOAdapter is BEAIOAdapter
