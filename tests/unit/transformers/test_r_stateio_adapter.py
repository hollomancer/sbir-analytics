"""Unit tests for R StateIO adapter."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from src.transformers.r_stateio_adapter import RStateIOAdapter
from src.utils.r_helpers import RFunctionError


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
def mock_r_packages():
    """Mock R packages for testing."""
    mock_stateio = MagicMock()
    mock_useeio = MagicMock()
    return mock_stateio, mock_useeio


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    config = MagicMock()
    config.stateio_model_version = "v2.1"
    return config


class TestRStateIOAdapterInitialization:
    """Test RStateIOAdapter initialization."""

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_init_success(self, mock_pandas2ri, mock_importr, mock_config):
        """Test successful initialization with R packages available."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        adapter = RStateIOAdapter(config=mock_config)
        assert adapter.stateio is not None
        assert adapter.cache_enabled is True
        assert adapter.model_version == "v2.1"

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", False)
    def test_init_no_rpy2(self, mock_config):
        """Test initialization fails when rpy2 is not available."""
        with pytest.raises(ImportError, match="rpy2 is not installed"):
            RStateIOAdapter(config=mock_config)

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_init_stateio_not_available(self, mock_pandas2ri, mock_importr, mock_config):
        """Test initialization when StateIO package is not installed."""
        mock_importr.side_effect = Exception("Package not found")

        adapter = RStateIOAdapter(config=mock_config)
        assert adapter.stateio is None

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_init_custom_cache_dir(self, mock_pandas2ri, mock_importr, mock_config, tmp_path):
        """Test initialization with custom cache directory."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        cache_dir = tmp_path / "custom_cache"
        adapter = RStateIOAdapter(config=mock_config, cache_dir=str(cache_dir))

        assert adapter.cache_dir == cache_dir
        assert cache_dir.exists()


class TestRStateIOAdapterCaching:
    """Test caching functionality."""

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_cache_key_generation(self, mock_pandas2ri, mock_importr, mock_config, sample_shocks):
        """Test cache key generation."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        adapter = RStateIOAdapter(config=mock_config)
        cache_key = adapter._get_cache_key(sample_shocks)

        assert cache_key.startswith("stateio_v2.1_")
        assert len(cache_key) > 15

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_cache_hit(self, mock_pandas2ri, mock_importr, mock_config, sample_shocks, tmp_path):
        """Test cache hit scenario."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        cache_dir = tmp_path / "cache"
        adapter = RStateIOAdapter(config=mock_config, cache_dir=str(cache_dir))

        # Create cached result
        cache_key = adapter._get_cache_key(sample_shocks)
        cached_result = sample_shocks.copy()
        cached_result["wage_impact"] = Decimal("100000")
        adapter._save_to_cache(cache_key, cached_result)

        # Load from cache
        loaded = adapter._load_from_cache(cache_key)
        assert loaded is not None
        assert "wage_impact" in loaded.columns

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_cache_miss(self, mock_pandas2ri, mock_importr, mock_config):
        """Test cache miss scenario."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        adapter = RStateIOAdapter(config=mock_config)
        result = adapter._load_from_cache("nonexistent_key")
        assert result is None


class TestRStateIOAdapterDataConversion:
    """Test pandas ↔ R data conversion."""

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_convert_shocks_to_r(self, mock_pandas2ri, mock_importr, mock_config, sample_shocks):
        """Test conversion of shocks DataFrame to R format."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        mock_r_obj = MagicMock()
        mock_pandas2ri.py2rpy.return_value = mock_r_obj

        adapter = RStateIOAdapter(config=mock_config)
        r_shocks = adapter._convert_shocks_to_r(sample_shocks)

        assert r_shocks == mock_r_obj
        mock_pandas2ri.py2rpy.assert_called_once()

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_convert_r_to_pandas(self, mock_pandas2ri, mock_importr, mock_config):
        """Test conversion of R result to pandas DataFrame."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        # Create mock R result with impact columns
        mock_r_result = MagicMock()
        result_df = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                "fiscal_year": [2023],
                "wage_impact": [400000.0],
                "proprietor_income_impact": [100000.0],
                "gross_operating_surplus": [300000.0],
                "consumption_impact": [200000.0],
                "tax_impact": [150000.0],
                "production_impact": [2000000.0],
            }
        )
        mock_pandas2ri.rpy2py.return_value = result_df

        adapter = RStateIOAdapter(config=mock_config)
        converted = adapter._convert_r_to_pandas(mock_r_result)

        assert isinstance(converted, pd.DataFrame)
        assert "wage_impact" in converted.columns
        # Check that monetary values are converted to Decimal
        assert isinstance(converted["wage_impact"].iloc[0], Decimal)


class TestRStateIOAdapterImpactComputation:
    """Test impact computation logic."""

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    @patch("src.transformers.r_stateio_adapter.call_r_function")
    def test_compute_impacts_success(
        self,
        mock_call_r_function,
        mock_pandas2ri,
        mock_importr,
        mock_config,
        sample_shocks,
    ):
        """Test successful impact computation using R functions."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        # Mock R function call returning result DataFrame
        mock_r_result = pd.DataFrame(
            {
                "state": ["CA", "NY", "TX"],
                "bea_sector": ["11", "21", "31"],
                "fiscal_year": [2023, 2023, 2023],
                "wage_impact": [400000.0, 200000.0, 300000.0],
                "proprietor_income_impact": [100000.0, 50000.0, 75000.0],
                "production_impact": [2000000.0, 1000000.0, 1500000.0],
            }
        )
        mock_call_r_function.return_value = mock_r_result
        mock_pandas2ri.rpy2py.return_value = mock_r_result

        adapter = RStateIOAdapter(config=mock_config, cache_enabled=False)
        result = adapter._compute_impacts_r(sample_shocks)

        assert len(result) == 3
        assert "wage_impact" in result.columns
        assert "production_impact" in result.columns
        assert result["model_version"].iloc[0] == "v2.1"

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    @patch("src.transformers.r_stateio_adapter.call_r_function")
    def test_compute_impacts_fallback_to_placeholder(
        self,
        mock_call_r_function,
        mock_pandas2ri,
        mock_importr,
        mock_config,
        sample_shocks,
    ):
        """Test fallback to placeholder when R functions fail."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        # Mock all R function calls failing
        mock_call_r_function.side_effect = RFunctionError("Function not found")

        adapter = RStateIOAdapter(config=mock_config, cache_enabled=False)
        result = adapter._compute_impacts_r(sample_shocks)

        # Should return placeholder results
        assert len(result) == 3
        assert "wage_impact" in result.columns
        assert result["quality_flags"].iloc[0] == "placeholder_computation"

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_compute_impacts_stateio_not_loaded(
        self, mock_pandas2ri, mock_importr, mock_config, sample_shocks
    ):
        """Test error when StateIO package is not loaded."""
        mock_importr.side_effect = Exception("Package not found")

        adapter = RStateIOAdapter(config=mock_config)
        assert adapter.stateio is None

        with pytest.raises(RuntimeError, match="StateIO R package not loaded"):
            adapter._compute_impacts_r(sample_shocks)

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_ensure_impact_columns(self, mock_pandas2ri, mock_importr, mock_config, sample_shocks):
        """Test _ensure_impact_columns adds missing columns."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        # Create incomplete result DataFrame
        incomplete_result = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                "fiscal_year": [2023],
                "wage_impact": [400000.0],
                # Missing other impact columns
            }
        )

        adapter = RStateIOAdapter(config=mock_config)
        complete_result = adapter._ensure_impact_columns(
            incomplete_result, sample_shocks.head(1), "v2.1"
        )

        # Check all required columns exist
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
        assert complete_result["quality_flags"].iloc[0] == "r_computation"


class TestRStateIOAdapterIntegration:
    """Test full compute_impacts integration."""

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    @patch("src.transformers.r_stateio_adapter.call_r_function")
    def test_compute_impacts_with_cache(
        self,
        mock_call_r_function,
        mock_pandas2ri,
        mock_importr,
        mock_config,
        sample_shocks,
        tmp_path,
    ):
        """Test compute_impacts uses cache when available."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        adapter = RStateIOAdapter(config=mock_config, cache_enabled=True, cache_dir=str(tmp_path))

        # First call - should compute and cache
        result1 = adapter.compute_impacts(sample_shocks)
        assert len(result1) == 3

        # Reset mock to track calls
        mock_call_r_function.reset_mock()

        # Second call - should use cache
        result2 = adapter.compute_impacts(sample_shocks)
        assert len(result2) == 3
        # R function should not be called again
        assert mock_call_r_function.call_count == 0

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_validate_input(self, mock_pandas2ri, mock_importr, mock_config, sample_shocks):
        """Test input validation."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        adapter = RStateIOAdapter(config=mock_config)

        # Valid input should pass
        adapter.validate_input(sample_shocks)

        # Missing column should fail
        invalid_shocks = sample_shocks.drop(columns=["state"])
        with pytest.raises(ValueError, match="Missing required columns"):
            adapter.validate_input(invalid_shocks)

    @patch("src.transformers.r_stateio_adapter.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_adapter.importr")
    @patch("src.transformers.r_stateio_adapter.pandas2ri")
    def test_is_available(self, mock_pandas2ri, mock_importr, mock_config):
        """Test is_available check."""
        mock_stateio = MagicMock()
        mock_importr.side_effect = lambda pkg: mock_stateio if pkg == "stateior" else MagicMock()

        adapter = RStateIOAdapter(config=mock_config)
        assert adapter.is_available() is True

        # When package not loaded
        adapter.stateio = None
        assert adapter.is_available() is False
