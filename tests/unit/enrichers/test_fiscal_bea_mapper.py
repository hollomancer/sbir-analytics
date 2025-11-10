"""Unit tests for fiscal BEA mapper.

Tests for NAICS-to-BEA sector mapping functionality:
- NAICSToBEAMapper: NAICS code normalization and mapping
- Direct crosswalk mapping
- Hierarchical fallback (6→4→3→2 digit)
- Fallback configuration mapping
- Default sector assignment
- DataFrame enrichment
- Mapping statistics calculation
"""

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.enrichers.fiscal_bea_mapper import (
    BEAMappingStatistics,
    NAICSToBEAMapper,
    NAICSToBEAResult,
    enrich_awards_with_bea_sectors,
)


pytestmark = pytest.mark.fast


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_crosswalk_df() -> pd.DataFrame:
    """Create sample BEA crosswalk DataFrame."""
    return pd.DataFrame(
        {
            "naics_code": ["541715", "541700", "540000", "511210"],
            "bea_sector_code": ["5417A0/US", "5417B0/US", "540000/US", "5112A0/US"],
            "bea_sector_name": [
                "R&D Scientific Services",
                "R&D and Testing Services",
                "Professional and Technical Services",
                "Software Publishers",
            ],
            "allocation_weight": [1.0, 1.0, 1.0, 1.0],
            "confidence": [0.95, 0.90, 0.85, 0.92],
        }
    )


@pytest.fixture
def sample_fallback_config() -> dict[str, Any]:
    """Create sample fallback configuration."""
    return {
        "mappings": {
            "999999": {
                "primary_sector": "UNKNOWN/US",
                "allocation_weight": 1.0,
                "confidence": 0.50,
            },
            "123456": {
                "primary_sector": "TEST01/US",
                "allocation_weight": 0.8,
                "confidence": 0.70,
                "secondary_sectors": [
                    {"sector": "TEST02/US", "weight": 0.2},
                ],
            },
        },
        "fallback_rules": {
            "default_sector": "540000/US",
            "default_confidence": 0.30,
        },
    }


@pytest.fixture
def temp_crosswalk_csv(tmp_path: Path, sample_crosswalk_df: pd.DataFrame) -> Path:
    """Create temporary crosswalk CSV file."""
    csv_path = tmp_path / "crosswalk.csv"
    sample_crosswalk_df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture
def temp_fallback_yaml(tmp_path: Path, sample_fallback_config: dict) -> Path:
    """Create temporary fallback YAML file."""
    import yaml

    yaml_path = tmp_path / "fallback.yaml"
    with yaml_path.open("w") as f:
        yaml.dump(sample_fallback_config, f)
    return yaml_path


# =============================================================================
# NAICSToBEAResult Tests
# =============================================================================


class TestNAICSToBEAResult:
    """Tests for NAICSToBEAResult dataclass."""

    def test_result_creation(self):
        """Test creating a mapping result."""
        result = NAICSToBEAResult(
            naics_code="541715",
            bea_sector_code="5417A0/US",
            bea_sector_name="R&D Services",
            allocation_weight=1.0,
            confidence=0.95,
            source="direct",
            crosswalk_version="2017",
            mapped_at=datetime(2025, 1, 1),
            metadata={"test": "value"},
        )

        assert result.naics_code == "541715"
        assert result.bea_sector_code == "5417A0/US"
        assert result.confidence == 0.95
        assert result.source == "direct"
        assert result.metadata == {"test": "value"}


# =============================================================================
# NAICSToBEAMapper Tests
# =============================================================================


class TestNAICSToBEAMapper:
    """Tests for the NAICS-to-BEA mapper."""

    def test_initialization_with_files(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test mapper initialization with provided files."""
        mapper = NAICSToBEAMapper(
            crosswalk_path=temp_crosswalk_csv, fallback_config_path=temp_fallback_yaml
        )

        assert mapper.crosswalk_df is not None
        assert len(mapper.crosswalk_df) == 4
        assert mapper.fallback_config is not None
        assert "mappings" in mapper.fallback_config

    def test_initialization_missing_files(self, tmp_path):
        """Test mapper initialization with missing files."""
        mapper = NAICSToBEAMapper(
            crosswalk_path=tmp_path / "nonexistent.csv", fallback_config_path=tmp_path / "nonexistent.yaml"
        )

        # Should handle missing files gracefully
        assert mapper.crosswalk_df is not None
        assert mapper.crosswalk_df.empty
        assert mapper.fallback_config == {}

    def test_normalize_naics_6_digit(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test normalizing 6-digit NAICS code."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        normalized = mapper._normalize_naics("541715")

        assert normalized == "541715"

    def test_normalize_naics_short_code(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test normalizing short NAICS code with padding."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        normalized = mapper._normalize_naics("5417")

        assert normalized == "005417"  # Padded to 6 digits

    def test_normalize_naics_with_non_digits(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test normalizing NAICS code with non-digit characters."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        normalized = mapper._normalize_naics("54-17-15")

        assert normalized == "541715"

    def test_map_direct_exact_match(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test direct mapping with exact match."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        results = mapper._map_direct("541715")

        assert results is not None
        assert len(results) == 1
        assert results[0].naics_code == "541715"
        assert results[0].bea_sector_code == "5417A0/US"
        assert results[0].source == "direct"
        assert results[0].confidence >= 0.9

    def test_map_direct_no_match(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test direct mapping with no match."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        results = mapper._map_direct("999999")

        assert results is None

    def test_map_hierarchical_4_digit(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test hierarchical fallback to 4-digit code."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        # "541799" should fall back to "541700" (4-digit match)
        results = mapper._map_hierarchical("541799")

        assert results is not None
        assert len(results) == 1
        assert results[0].naics_code == "541799"
        assert "hierarchical" in results[0].source
        assert results[0].confidence < 0.9  # Reduced confidence for fallback

    def test_map_hierarchical_disabled(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test hierarchical mapping when disabled."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)
        mapper.hierarchical_fallback = False

        results = mapper._map_hierarchical("541799")

        assert results is None

    def test_map_fallback_config_exact(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test fallback configuration mapping with exact match."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        results = mapper._map_fallback_config("999999")

        assert results is not None
        assert len(results) == 1
        assert results[0].bea_sector_code == "UNKNOWN/US"
        assert results[0].source == "fallback_config"

    def test_map_fallback_config_weighted_allocation(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test fallback configuration with weighted allocations."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        results = mapper._map_fallback_config("123456")

        assert results is not None
        assert len(results) == 2  # Primary + secondary
        assert results[0].allocation_weight == 0.8
        assert results[1].allocation_weight == 0.2
        assert results[1].source == "fallback_config_weighted"

    def test_map_default(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test default sector mapping."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        results = mapper._map_default("888888")

        assert len(results) == 1
        assert results[0].source == "default_fallback"
        assert results[0].confidence == 0.30  # From fallback config

    def test_map_naics_to_bea_direct(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test complete mapping workflow with direct match."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        results = mapper.map_naics_to_bea("541715")

        assert len(results) == 1
        assert results[0].source == "direct"
        assert results[0].confidence >= 0.9

    def test_map_naics_to_bea_hierarchical(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test complete mapping workflow with hierarchical fallback."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        results = mapper.map_naics_to_bea("541799")

        assert len(results) == 1
        assert "hierarchical" in results[0].source

    def test_map_naics_to_bea_none_input(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test mapping with None input."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        results = mapper.map_naics_to_bea(None)

        assert len(results) == 1
        assert results[0].source == "default_fallback"
        assert results[0].naics_code == "UNKNOWN"

    def test_map_naics_to_bea_caching(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test mapping result caching."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        # First call
        results1 = mapper.map_naics_to_bea("541715")
        # Second call should use cache
        results2 = mapper.map_naics_to_bea("541715")

        assert results1 == results2
        assert "541715" in mapper._mapping_cache

    def test_enrich_awards_with_bea_sectors(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test enriching awards DataFrame with BEA sectors."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        awards_df = pd.DataFrame(
            {
                "award_id": [1, 2, 3],
                "fiscal_naics_code": ["541715", "541700", "999999"],
                "amount": [100000, 200000, 150000],
            }
        )

        enriched_df = mapper.enrich_awards_with_bea_sectors(awards_df)

        assert "bea_sector_code" in enriched_df.columns
        assert "bea_mapping_confidence" in enriched_df.columns
        assert len(enriched_df) >= len(awards_df)  # May have multiple rows for weighted allocations

    def test_get_mapping_statistics(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test calculating mapping statistics."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)

        awards_df = pd.DataFrame(
            {
                "award_id": [1, 2, 3, 4],
                "fiscal_naics_code": ["541715", "541700", "999999", None],
            }
        )

        stats = mapper.get_mapping_statistics(awards_df)

        assert isinstance(stats, BEAMappingStatistics)
        assert stats.total_mappings == 4
        assert stats.successful_mappings >= 3  # All except maybe None
        assert 0 <= stats.coverage_rate <= 1.0
        assert "direct" in stats.source_distribution or "hierarchical_4digit" in stats.source_distribution


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_enrich_awards_with_bea_sectors_no_mapper(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test helper function creates mapper if not provided."""
        awards_df = pd.DataFrame(
            {
                "award_id": [1, 2],
                "fiscal_naics_code": ["541715", "541700"],
            }
        )

        with patch("src.enrichers.fiscal_bea_mapper.NAICSToBEAMapper") as mock_mapper_class:
            mock_instance = MagicMock()
            mock_instance.enrich_awards_with_bea_sectors.return_value = awards_df
            mock_instance.get_mapping_statistics.return_value = BEAMappingStatistics(
                total_mappings=2,
                successful_mappings=2,
                failed_mappings=0,
                coverage_rate=1.0,
                avg_confidence=0.9,
                min_confidence=0.85,
                max_confidence=0.95,
                source_distribution={"direct": 2},
                hierarchical_fallback_count=0,
                weighted_allocation_count=0,
            )
            mock_mapper_class.return_value = mock_instance

            enriched_df, stats = enrich_awards_with_bea_sectors(awards_df)

            assert mock_mapper_class.called
            assert len(enriched_df) == 2
            assert isinstance(stats, BEAMappingStatistics)

    def test_enrich_awards_with_bea_sectors_with_mapper(self, temp_crosswalk_csv, temp_fallback_yaml):
        """Test helper function uses provided mapper."""
        mapper = NAICSToBEAMapper(temp_crosswalk_csv, temp_fallback_yaml)
        awards_df = pd.DataFrame(
            {
                "award_id": [1],
                "fiscal_naics_code": ["541715"],
            }
        )

        enriched_df, stats = enrich_awards_with_bea_sectors(awards_df, mapper)

        assert len(enriched_df) >= 1
        assert isinstance(stats, BEAMappingStatistics)
