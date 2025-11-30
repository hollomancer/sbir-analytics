"""Unit tests for SAM.gov Extractor.

Tests cover:
- Initialization and configuration
- Parquet file loading with S3 and local paths
- Entity lookup methods (UEI, CAGE, DUNS)
- Error handling
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.extractors.sam_gov import SAMGovExtractor


pytestmark = pytest.mark.fast


@pytest.fixture(autouse=True)
def clear_config_cache():
    """Clear config cache to ensure test isolation."""
    from src.config.loader import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def sample_parquet_file(tmp_path):
    """Create a sample SAM.gov parquet file."""
    parquet_file = tmp_path / "sam_entity_records.parquet"

    # Create a minimal SAM.gov dataset
    df = pd.DataFrame(
        {
            "unique_entity_id": ["ABC123456789", "DEF987654321", "GHI111222333"],
            "cage_code": ["1ABC5", "2DEF6", "3GHI7"],
            "legal_business_name": ["Test Company LLC", "Another Corp", "Third Industries"],
            "dba_name": ["Test Co", "Another", "Third"],
            "physical_address_line_1": ["123 Main St", "456 Oak Ave", "789 Pine Rd"],
            "physical_address_city": ["Washington", "Boston", "Austin"],
            "physical_address_state_or_province": ["DC", "MA", "TX"],
            "physical_address_zip_postal_code": ["20001", "02101", "73301"],
            "primary_naics": ["541512", "541330", "541715"],
            "naics_code_string": ["541512", "541330,541519", "541715"],
        }
    )
    df.to_parquet(parquet_file)
    return parquet_file


@pytest.fixture
def mock_config():
    """Mock configuration for SAM.gov extractor."""
    config = MagicMock()
    config.extraction.sam_gov.parquet_path = "data/raw/sam_gov/sam_entity_records.parquet"
    config.extraction.sam_gov.use_s3_first = True
    config.extraction.sam_gov.batch_size = 10000
    return config


@pytest.fixture
def extractor_with_mock_config(mock_config):
    """Create extractor with mocked configuration."""
    with patch("src.extractors.sam_gov.get_config", return_value=mock_config):
        extractor = SAMGovExtractor()
        return extractor


class TestSAMGovExtractorInit:
    """Test SAM.gov extractor initialization."""

    def test_initialization(self, extractor_with_mock_config):
        """Test extractor initializes correctly."""
        assert extractor_with_mock_config is not None
        assert extractor_with_mock_config.config is not None
        assert extractor_with_mock_config.sam_config is not None


class TestParquetLoading:
    """Test parquet file loading."""

    def test_load_parquet_local(self, extractor_with_mock_config, sample_parquet_file):
        """Test loading parquet from local file."""
        df = extractor_with_mock_config.load_parquet(
            parquet_path=sample_parquet_file, use_s3_first=False
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "unique_entity_id" in df.columns
        assert "cage_code" in df.columns
        assert "legal_business_name" in df.columns

    def test_load_parquet_file_not_found(self, extractor_with_mock_config):
        """Test loading non-existent parquet file raises error."""
        with pytest.raises(FileNotFoundError):
            extractor_with_mock_config.load_parquet(
                parquet_path="/nonexistent/file.parquet", use_s3_first=False
            )

    def test_load_parquet_s3_first(
        self,
        extractor_with_mock_config,
        sample_parquet_file,
    ):
        """Test loading parquet with S3-first strategy."""
        # Read sample data first
        sample_df = pd.read_parquet(sample_parquet_file)

        # Mock S3 bucket configured
        extractor_with_mock_config.config.s3 = {"bucket": "test-bucket"}

        with patch("src.utils.cloud_storage.find_latest_sam_gov_parquet") as mock_find_latest:
            with patch("src.extractors.sam_gov.pd.read_parquet") as mock_read_parquet:
                # Mock S3 file found
                mock_find_latest.return_value = (
                    "s3://test-bucket/data/raw/sam_gov/sam_entity_records.parquet"
                )

                # Mock read_parquet to return sample data
                mock_read_parquet.return_value = sample_df

                # Don't provide parquet_path so it uses S3
                df = extractor_with_mock_config.load_parquet(parquet_path=None, use_s3_first=True)

                assert isinstance(df, pd.DataFrame)
                assert len(df) == 3
                mock_find_latest.assert_called_once()


class TestEntityLookups:
    """Test entity lookup methods."""

    @pytest.fixture
    def sample_df(self, sample_parquet_file):
        """Load sample DataFrame."""
        return pd.read_parquet(sample_parquet_file)

    def test_get_entity_by_uei_found(self, extractor_with_mock_config, sample_df):
        """Test getting entity by UEI when found."""
        result = extractor_with_mock_config.get_entity_by_uei(sample_df, "ABC123456789")

        assert result is not None
        assert isinstance(result, pd.Series)
        assert result["legal_business_name"] == "Test Company LLC"
        assert result["cage_code"] == "1ABC5"

    def test_get_entity_by_uei_not_found(self, extractor_with_mock_config, sample_df):
        """Test getting entity by UEI when not found."""
        result = extractor_with_mock_config.get_entity_by_uei(sample_df, "NONEXISTENT")

        assert result is None

    def test_get_entity_by_cage_found(self, extractor_with_mock_config, sample_df):
        """Test getting entity by CAGE code when found."""
        result = extractor_with_mock_config.get_entity_by_cage(sample_df, "2DEF6")

        assert result is not None
        assert isinstance(result, pd.Series)
        assert result["legal_business_name"] == "Another Corp"
        assert result["unique_entity_id"] == "DEF987654321"

    def test_get_entity_by_cage_not_found(self, extractor_with_mock_config, sample_df):
        """Test getting entity by CAGE code when not found."""
        result = extractor_with_mock_config.get_entity_by_cage(sample_df, "XXXXX")

        assert result is None

    def test_get_entities_by_duns_no_column(self, extractor_with_mock_config, sample_df):
        """Test getting entities by DUNS when DUNS column doesn't exist."""
        result = extractor_with_mock_config.get_entities_by_duns(sample_df, "123456789")

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0  # Empty DataFrame when DUNS column not present
