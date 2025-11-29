"""Unit tests for SAM.gov ingestion Dagster assets.

Tests cover:
- Asset execution with parquet files
- S3-first, local-fallback strategy
- Error handling when files unavailable
- Metadata generation
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from dagster import Output

from src.assets.sam_gov_ingestion import _import_sam_gov_entities, raw_sam_gov_entities
from tests.mocks import ContextMocks


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_sam_gov_df():
    """Create a sample SAM.gov DataFrame."""
    return pd.DataFrame(
        {
            "unique_entity_id": ["ABC123456789", "DEF987654321"],
            "cage_code": ["1ABC5", "2DEF6"],
            "legal_business_name": ["Test Company LLC", "Another Corp"],
            "dba_name": ["Test Co", "Another"],
            "primary_naics": ["541512", "541330"],
            "naics_code_string": ["541512", "541330,541519"],
        }
    )


@pytest.fixture
def sample_parquet_file(tmp_path, sample_sam_gov_df):
    """Create a sample SAM.gov parquet file."""
    parquet_file = tmp_path / "sam_entity_records.parquet"
    sample_sam_gov_df.to_parquet(parquet_file)
    return parquet_file


@pytest.fixture
def mock_context():
    """Mock AssetExecutionContext."""
    return ContextMocks.context_with_logging()


@pytest.fixture
def mock_config():
    """Mock configuration."""
    config = MagicMock()
    config.extraction.sam_gov.parquet_path = "data/raw/sam_gov/sam_entity_records.parquet"
    config.extraction.sam_gov.use_s3_first = True
    config.extraction.sam_gov.batch_size = 10000
    return config


class TestImportSAMGovEntitiesHelper:
    """Test _import_sam_gov_entities helper function."""

    @patch("src.assets.sam_gov_ingestion.SAMGovExtractor")
    @patch("src.assets.sam_gov_ingestion.get_config")
    def test_import_from_local_parquet(
        self,
        mock_get_config,
        mock_extractor_class,
        mock_context,
        mock_config,
        sample_parquet_file,
        sample_sam_gov_df,
    ):
        """Test importing SAM.gov entities from local parquet file."""
        # Setup mocks
        mock_get_config.return_value = mock_config
        mock_config.extraction.sam_gov.parquet_path = str(sample_parquet_file)
        mock_config.s3 = {}  # No S3 configured

        mock_extractor = MagicMock()
        mock_extractor.load_parquet.return_value = sample_sam_gov_df
        mock_extractor_class.return_value = mock_extractor

        # Mock Path.exists to return True for the parquet file
        with patch.object(Path, "exists", return_value=True):
            # Execute
            result = _import_sam_gov_entities(mock_context)

            # Assertions
            assert isinstance(result, Output)
            assert isinstance(result.value, pd.DataFrame)
            assert len(result.value) == 2
            assert "unique_entity_id" in result.value.columns

            # Check metadata - extract .value from Dagster metadata types
            assert result.metadata is not None
            assert "row_count" in result.metadata
            from dagster import IntMetadataValue

            if isinstance(result.metadata["row_count"], IntMetadataValue):
                assert result.metadata["row_count"].value == 2
            else:
                assert result.metadata["row_count"] == 2

    @patch("src.assets.sam_gov_ingestion.find_latest_sam_gov_parquet")
    @patch("src.assets.sam_gov_ingestion.resolve_data_path")
    @patch("src.assets.sam_gov_ingestion.SAMGovExtractor")
    @patch("src.assets.sam_gov_ingestion.get_config")
    def test_import_from_s3_parquet(
        self,
        mock_get_config,
        mock_extractor_class,
        mock_resolve_path,
        mock_find_latest,
        mock_context,
        mock_config,
        sample_parquet_file,
        sample_sam_gov_df,
    ):
        """Test importing SAM.gov entities from S3 parquet file."""
        # Setup mocks
        mock_get_config.return_value = mock_config
        mock_config.s3 = {"bucket": "test-bucket"}
        mock_config.extraction.sam_gov.use_s3_first = True

        # Mock S3 file discovery and resolution
        s3_url = "s3://test-bucket/data/raw/sam_gov/sam_entity_records.parquet"
        mock_find_latest.return_value = s3_url
        mock_resolve_path.return_value = sample_parquet_file

        mock_extractor = MagicMock()
        mock_extractor.load_parquet.return_value = sample_sam_gov_df
        mock_extractor_class.return_value = mock_extractor

        # Execute
        result = _import_sam_gov_entities(mock_context)

        # Assertions
        assert isinstance(result, Output)
        assert isinstance(result.value, pd.DataFrame)
        assert len(result.value) == 2

        # Verify S3 methods were called
        mock_find_latest.assert_called_once_with(bucket="test-bucket")
        mock_resolve_path.assert_called_once_with(s3_url)

    @patch("src.assets.sam_gov_ingestion.get_config")
    def test_import_fails_when_no_file_available(self, mock_get_config, mock_context, mock_config):
        """Test that import fails when parquet file is not available."""
        # Setup mocks
        mock_get_config.return_value = mock_config
        mock_config.s3 = {}  # No S3 configured
        mock_config.extraction.sam_gov.parquet_path = "/nonexistent/file.parquet"

        # Mock Path.exists to return False
        with patch.object(Path, "exists", return_value=False):
            # Execute and expect error
            from src.exceptions import ExtractionError

            with pytest.raises(ExtractionError) as exc_info:
                _import_sam_gov_entities(mock_context)

            assert "SAM.gov data unavailable" in str(exc_info.value)


class TestRawSAMGovEntitiesAsset:
    """Test raw_sam_gov_entities Dagster asset."""

    @patch("src.assets.sam_gov_ingestion._import_sam_gov_entities")
    def test_asset_calls_helper(self, mock_import_helper, mock_context, sample_sam_gov_df):
        """Test that asset calls the helper function."""
        # Setup mock
        mock_import_helper.return_value = Output(
            value=sample_sam_gov_df,
            metadata={
                "row_count": 2,
                "num_columns": 6,
            },
        )

        # Execute - pass context as keyword argument for Dagster
        result = raw_sam_gov_entities(context=mock_context)

        # Assertions
        assert isinstance(result, Output)
        assert isinstance(result.value, pd.DataFrame)
        mock_import_helper.assert_called_once_with(mock_context)

    @patch("src.assets.sam_gov_ingestion.SAMGovExtractor")
    @patch("src.assets.sam_gov_ingestion.get_config")
    def test_asset_metadata(
        self,
        mock_get_config,
        mock_extractor_class,
        mock_context,
        mock_config,
        sample_parquet_file,
        sample_sam_gov_df,
    ):
        """Test that asset generates proper metadata."""
        # Setup mocks
        mock_get_config.return_value = mock_config
        mock_config.extraction.sam_gov.parquet_path = str(sample_parquet_file)
        mock_config.s3 = {}  # No S3 configured

        mock_extractor = MagicMock()
        mock_extractor.load_parquet.return_value = sample_sam_gov_df
        mock_extractor_class.return_value = mock_extractor

        # Mock Path.exists to return True
        with patch.object(Path, "exists", return_value=True):
            # Execute - pass context as keyword argument
            result = raw_sam_gov_entities(context=mock_context)

            # Check metadata structure
            assert result.metadata is not None
            assert "row_count" in result.metadata
            assert "num_columns" in result.metadata
            assert "columns" in result.metadata
            assert "preview" in result.metadata
            assert "key_columns" in result.metadata

            # Verify key columns are included
            from dagster import MetadataValue

            key_columns = result.metadata["key_columns"]
            assert isinstance(key_columns, MetadataValue)
