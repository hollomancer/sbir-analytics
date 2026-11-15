"""Unit tests for BEA I-O adapter."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


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


USE_TABLE = pd.DataFrame(
    [[10, 5, 3], [5, 10, 2], [3, 2, 10]],
    index=["11", "21", "31"],
    columns=["11", "21", "31"],
    dtype=float,
)


def _va_ratios(sectors):
    return pd.DataFrame(
        {
            "sector": sectors,
            "wage_ratio": [0.5] * len(sectors),
            "gos_ratio": [0.3] * len(sectors),
            "tax_ratio": [0.1] * len(sectors),
            "proprietor_income_ratio": [0.1] * len(sectors),
        }
    )


def _emp_coeffs(sectors):
    return pd.DataFrame(
        {
            "sector": sectors,
            "employment": [100.0] * len(sectors),
            "employment_coefficient": [5.0] * len(sectors),
        }
    )


def _bea_adapter(mock_config, va_ratios, emp_coeffs, **kwargs):
    """Build an adapter whose BEA tables come from fixed test frames."""
    from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

    with patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient"):
        adapter = BEAIOAdapter(config=mock_config, **kwargs)
    adapter._use_table_cache[2023] = USE_TABLE
    adapter._va_ratios_cache[2023] = va_ratios
    adapter._emp_coeff_cache[2023] = emp_coeffs
    return adapter


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
        side_effect=__import__(
            "sbir_etl.exceptions", fromlist=["ConfigurationError"]
        ).ConfigurationError("BEA_API_KEY not set", component="test", operation="test"),
    )
    def test_init_no_api_key(self, mock_client_cls, mock_config):
        """Test initialization records that BEA computation is unavailable."""
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
    def test_compute_impacts_requires_api(self, mock_client_cls, mock_config, sample_shocks):
        """The adapter must not synthesize impacts when the API is unavailable."""
        from sbir_etl.exceptions import ConfigurationError

        mock_client_cls.side_effect = ConfigurationError(
            "BEA_API_KEY not set", component="test", operation="test"
        )

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config, cache_enabled=False)
        with pytest.raises(ConfigurationError, match="requires BEA_API_KEY"):
            adapter._compute_impacts_bea(sample_shocks)

    def test_stale_placeholder_cache_is_discarded_and_recomputed(
        self, mock_config, sample_shocks, tmp_path
    ):
        """A cached placeholder is evicted; a working BEA computation replaces it."""
        from sbir_etl.transformers.bea_io_adapter import BEA_COMPUTED_QUALITY_FLAG

        sectors = ["11", "21", "31"]
        adapter = _bea_adapter(
            mock_config,
            _va_ratios(sectors),
            _emp_coeffs(sectors),
            cache_enabled=True,
            cache_dir=str(tmp_path),
        )
        cache_key = adapter._get_cache_key(sample_shocks)
        stale = sample_shocks.copy()
        stale["quality_flags"] = "placeholder_computation"
        adapter._save_to_cache(cache_key, stale)

        result = adapter.compute_impacts(sample_shocks)

        assert (result["quality_flags"] == BEA_COMPUTED_QUALITY_FLAG).all()
        cached_file = pd.read_parquet(tmp_path / f"{cache_key}.parquet")
        assert (cached_file["quality_flags"] == BEA_COMPUTED_QUALITY_FLAG).all()

    def test_fallback_result_error_names_cache_file(self, mock_config, sample_shocks, tmp_path):
        """A rejected fresh result is not cached, and the error names the cache path."""
        from sbir_etl.exceptions import TransformationError

        adapter = _bea_adapter(
            mock_config,
            pd.DataFrame(),
            _emp_coeffs(["11", "21", "31"]),
            cache_enabled=True,
            cache_dir=str(tmp_path),
        )
        cache_file = tmp_path / f"{adapter._get_cache_key(sample_shocks)}.parquet"

        with pytest.raises(TransformationError) as excinfo:
            adapter.compute_impacts(sample_shocks)

        assert excinfo.value.details["cache_file"] == str(cache_file)
        assert not cache_file.exists()

    @pytest.mark.parametrize(
        ("va_sectors", "emp_sectors", "shock_sector", "expected_flag"),
        [
            # Value-added table lacks the sector: fixed 0.4/0.3/0.15/0.0 ratios.
            (["21", "31"], ["11", "21", "31"], "11", "bea_api_default_ratios"),
            # Sector absent from the Leontief production results: zero production.
            (["11", "99"], ["11", "99"], "99", "bea_zero_production_fallback"),
            # No employment coefficient for the sector: ~10 jobs per $1M.
            (["11", "21", "31"], ["21", "31"], "11", "bea_default_employment_fallback"),
        ],
    )
    def test_compute_impacts_rejects_each_fallback(
        self, mock_config, va_sectors, emp_sectors, shock_sector, expected_flag
    ):
        """Every non-BEA fallback branch fails closed, each with its own flag."""
        from sbir_etl.exceptions import TransformationError

        adapter = _bea_adapter(
            mock_config, _va_ratios(va_sectors), _emp_coeffs(emp_sectors), cache_enabled=False
        )
        shocks = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": [shock_sector],
                "fiscal_year": [2023],
                "shock_amount": [Decimal("1000000")],
            }
        )

        flagged = adapter._compute_impacts_bea(shocks)
        assert flagged["quality_flags"].tolist() == [expected_flag]

        with pytest.raises(TransformationError, match="non-BEA fallback rows") as excinfo:
            adapter.compute_impacts(shocks)
        assert excinfo.value.details["quality_flags"] == [expected_flag]

    def test_fully_bea_row_is_accepted(self, mock_config):
        """Near-miss for the fallback tests: all three BEA inputs present passes."""
        from sbir_etl.transformers.bea_io_adapter import BEA_COMPUTED_QUALITY_FLAG

        adapter = _bea_adapter(
            mock_config, _va_ratios(["11"]), _emp_coeffs(["11"]), cache_enabled=False
        )
        shocks = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                "fiscal_year": [2023],
                "shock_amount": [Decimal("1000000")],
            }
        )

        result = adapter.compute_impacts(shocks)

        assert result["quality_flags"].tolist() == [BEA_COMPUTED_QUALITY_FLAG]

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
        assert "confidence" not in result.columns

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
    @patch("sbir_etl.transformers.bea_io_adapter.fetch_employment")
    @patch("sbir_etl.transformers.bea_io_adapter.calculate_employment_coefficients")
    def test_compute_impacts_with_cache(
        self,
        mock_emp_coeffs,
        mock_fetch_emp,
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
        mock_fetch_use.return_value = USE_TABLE
        mock_fetch_va.return_value = pd.DataFrame()
        mock_va_ratios.return_value = _va_ratios(["11", "21", "31"])
        mock_fetch_emp.return_value = pd.DataFrame()
        mock_emp_coeffs.return_value = _emp_coeffs(["11", "21", "31"])

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config, cache_enabled=True, cache_dir=str(tmp_path))

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

        from sbir_etl.exceptions import ValidationError

        invalid_shocks = sample_shocks.drop(columns=["state"])
        with pytest.raises(ValidationError, match="Missing required columns"):
            adapter.validate_input(invalid_shocks)

    @patch("sbir_etl.transformers.bea_io_adapter.BEAApiClient")
    def test_is_available(self, mock_client_cls, mock_config):
        """Test is_available check."""
        mock_client_cls.return_value = MagicMock()

        from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter

        adapter = BEAIOAdapter(config=mock_config)
        assert adapter.is_available() is True
