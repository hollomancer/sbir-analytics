"""Integration tests for SAM.gov bulk data integration.

Tests the complete SAM.gov data pipeline:
- Parquet file extraction
- S3/local path resolution
- Dagster asset execution
- API client fallback (if needed)
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.assets.sam_gov_ingestion import raw_sam_gov_entities
from src.extractors.sam_gov import SAMGovExtractor


pytestmark = pytest.mark.integration


@pytest.fixture
def sample_sam_gov_parquet(tmp_path):
    """Create a sample SAM.gov parquet file with realistic data."""
    data = {
        "unique_entity_id": [
            "ABC123456789",
            "DEF987654321",
            "GHI111222333",
            "JKL444555666",
            "MNO777888999",
        ],
        "cage_code": ["1ABC5", "2DEF6", "3GHI7", "4JKL8", "5MNO9"],
        "legal_business_name": [
            "Acme Corporation",
            "Tech Innovations LLC",
            "Research Institute Inc",
            "Data Systems Group",
            "Aerospace Solutions",
        ],
        "dba_name": ["Acme", "Tech Innovations", "Research Inst", "DataSys", "AeroSol"],
        "physical_address_line_1": [
            "100 Main Street",
            "200 Innovation Drive",
            "300 Research Parkway",
            "400 Data Center Blvd",
            "500 Aerospace Way",
        ],
        "physical_address_city": [
            "Washington",
            "Boston",
            "Austin",
            "Seattle",
            "Los Angeles",
        ],
        "physical_address_state_or_province": ["DC", "MA", "TX", "WA", "CA"],
        "physical_address_zip_postal_code": ["20001", "02101", "73301", "98101", "90001"],
        "primary_naics": ["541512", "541330", "541715", "541511", "336411"],
        "naics_code_string": [
            "541512",
            "541330,541519",
            "541715",
            "541511,541512",
            "336411,541712",
        ],
    }

    df = pd.DataFrame(data)
    parquet_file = tmp_path / "sam_entity_records.parquet"
    df.to_parquet(parquet_file)
    return parquet_file


class TestSAMGovExtractorIntegration:
    """Integration tests for SAM.gov extractor."""

    def test_load_and_query_parquet(self, sample_sam_gov_parquet):
        """Test loading parquet file and querying entities."""
        # Create extractor with mock config
        with patch("src.extractors.sam_gov.get_config") as mock_config:
            mock_config.return_value.extraction.sam_gov.parquet_path = str(
                sample_sam_gov_parquet
            )
            mock_config.return_value.extraction.sam_gov.use_s3_first = False

            extractor = SAMGovExtractor()

            # Load parquet
            df = extractor.load_parquet(
                parquet_path=sample_sam_gov_parquet, use_s3_first=False
            )

            # Verify data loaded
            assert len(df) == 5
            assert "unique_entity_id" in df.columns
            assert "cage_code" in df.columns
            assert "legal_business_name" in df.columns

            # Test UEI lookup
            entity = extractor.get_entity_by_uei(df, "ABC123456789")
            assert entity is not None
            assert entity["legal_business_name"] == "Acme Corporation"
            assert entity["cage_code"] == "1ABC5"

            # Test CAGE lookup
            entity = extractor.get_entity_by_cage(df, "2DEF6")
            assert entity is not None
            assert entity["legal_business_name"] == "Tech Innovations LLC"
            assert entity["unique_entity_id"] == "DEF987654321"

            # Test not found cases
            assert extractor.get_entity_by_uei(df, "NONEXISTENT") is None
            assert extractor.get_entity_by_cage(df, "XXXXX") is None

    def test_multiple_naics_codes(self, sample_sam_gov_parquet):
        """Test handling of multiple NAICS codes in naics_code_string."""
        with patch("src.extractors.sam_gov.get_config") as mock_config:
            mock_config.return_value.extraction.sam_gov.parquet_path = str(
                sample_sam_gov_parquet
            )
            mock_config.return_value.extraction.sam_gov.use_s3_first = False

            extractor = SAMGovExtractor()
            df = extractor.load_parquet(
                parquet_path=sample_sam_gov_parquet, use_s3_first=False
            )

            # Check entity with multiple NAICS codes
            entity = extractor.get_entity_by_uei(df, "DEF987654321")
            assert entity is not None
            assert entity["naics_code_string"] == "541330,541519"

            # Verify we can split and process multiple NAICS codes
            naics_codes = entity["naics_code_string"].split(",")
            assert len(naics_codes) == 2
            assert "541330" in naics_codes
            assert "541519" in naics_codes


class TestSAMGovAssetIntegration:
    """Integration tests for SAM.gov Dagster asset."""

    def test_asset_execution_with_local_file(self, sample_sam_gov_parquet):
        """Test Dagster asset execution with local parquet file."""
        # Mock context
        context = MagicMock()
        context.log = MagicMock()

        # Mock config
        with patch("src.assets.sam_gov_ingestion.get_config") as mock_config:
            mock_config.return_value.extraction.sam_gov.parquet_path = str(
                sample_sam_gov_parquet
            )
            mock_config.return_value.extraction.sam_gov.use_s3_first = False
            mock_config.return_value.s3 = {}

            # Mock Path.exists
            with patch("src.assets.sam_gov_ingestion.Path") as mock_path:
                mock_path.return_value.exists.return_value = True

                # Mock SAMGovExtractor to return our test data
                with patch("src.assets.sam_gov_ingestion.SAMGovExtractor") as mock_extractor_class:
                    mock_extractor = MagicMock()
                    test_df = pd.read_parquet(sample_sam_gov_parquet)
                    mock_extractor.load_parquet.return_value = test_df
                    mock_extractor_class.return_value = mock_extractor

                    # Execute asset
                    result = raw_sam_gov_entities(context)

                    # Verify result
                    assert result is not None
                    assert hasattr(result, "value")
                    assert isinstance(result.value, pd.DataFrame)
                    assert len(result.value) == 5

                    # Verify metadata
                    assert result.metadata is not None
                    assert "row_count" in result.metadata
                    assert result.metadata["row_count"] == 5
                    assert "num_columns" in result.metadata
                    assert "key_columns" in result.metadata

    def test_asset_error_handling_no_file(self):
        """Test Dagster asset error handling when parquet file is missing."""
        from src.exceptions import ExtractionError

        # Mock context
        context = MagicMock()
        context.log = MagicMock()

        # Mock config with non-existent file
        with patch("src.assets.sam_gov_ingestion.get_config") as mock_config:
            mock_config.return_value.extraction.sam_gov.parquet_path = (
                "/nonexistent/file.parquet"
            )
            mock_config.return_value.extraction.sam_gov.use_s3_first = False
            mock_config.return_value.s3 = {}

            # Mock Path.exists to return False
            with patch("src.assets.sam_gov_ingestion.Path") as mock_path:
                mock_path.return_value.exists.return_value = False

                # Execute and expect error
                with pytest.raises(ExtractionError) as exc_info:
                    raw_sam_gov_entities(context)

                assert "SAM.gov data unavailable" in str(exc_info.value)


class TestSAMGovS3Integration:
    """Integration tests for S3 path resolution (mocked S3)."""

    def test_s3_path_resolution(self, sample_sam_gov_parquet):
        """Test S3 path resolution with mocked S3 client."""
        with patch("src.extractors.sam_gov.get_config") as mock_config:
            mock_config.return_value.extraction.sam_gov.parquet_path = "data/raw/sam_gov/sam_entity_records.parquet"
            mock_config.return_value.extraction.sam_gov.use_s3_first = True
            mock_config.return_value.s3 = {"bucket": "test-bucket"}

            # Mock S3 utilities
            with patch("src.extractors.sam_gov.find_latest_sam_gov_parquet") as mock_find:
                with patch("src.extractors.sam_gov.resolve_data_path") as mock_resolve:
                    # Setup mocks
                    s3_url = "s3://test-bucket/data/raw/sam_gov/sam_entity_records.parquet"
                    mock_find.return_value = s3_url
                    mock_resolve.return_value = sample_sam_gov_parquet

                    extractor = SAMGovExtractor()
                    df = extractor.load_parquet(use_s3_first=True)

                    # Verify S3 methods called
                    mock_find.assert_called_once()
                    mock_resolve.assert_called_once_with(
                        s3_url, local_fallback=Path("data/raw/sam_gov/sam_entity_records.parquet")
                    )

                    # Verify data loaded
                    assert len(df) == 5
