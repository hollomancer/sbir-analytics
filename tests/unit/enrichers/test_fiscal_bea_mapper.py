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

from sbir_etl.exceptions import ConfigurationError
from sbir_etl.enrichers.fiscal_bea_mapper import (
    BEAMappingStatistics,
    NAICSToBEAMapper,
    NAICSToBEAResult,
    enrich_awards_with_bea_sectors,
)
from tests.assertions import assert_dataframe_has_columns


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
            crosswalk_path=tmp_path / "nonexistent.csv",
            fallback_config_path=tmp_path / "nonexistent.yaml",
        )

        # Should handle missing files gracefully
        assert mapper.crosswalk_df is not None
        assert mapper.crosswalk_df.empty
        assert mapper.fallback_config == {}

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

        assert_dataframe_has_columns(enriched_df, ["bea_sector_code", "bea_mapping_confidence"])
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
        assert (
            "direct" in stats.source_distribution
            or "hierarchical_4digit" in stats.source_distribution
        )


# =============================================================================
# Prefix fallback on unpadded codes (issue #867)
# =============================================================================


@pytest.fixture
def prefix_mapper(tmp_path: Path, temp_fallback_yaml: Path) -> NAICSToBEAMapper:
    """Mapper whose crosswalk holds one entry per NAICS level.

    Padded entries (541710, 541700, 334000, 540000) and one short entry (5413)
    check that the crosswalk may store either form.
    """
    crosswalk = pd.DataFrame(
        {
            "naics_code": ["511210", "541710", "541700", "334000", "540000", "5413"],
            "bea_sector_code": [
                "5112A0/US",
                "54171X/US",
                "5417B0/US",
                "334000/US",
                "540000/US",
                "541300/US",
            ],
            "confidence": [0.90] * 6,
        }
    )
    csv_path = tmp_path / "prefix_crosswalk.csv"
    crosswalk.to_csv(csv_path, index=False)
    return NAICSToBEAMapper(csv_path, temp_fallback_yaml)


class TestUnpaddedPrefixFallback:
    """Short codes reach their prefix entry instead of the default sector."""

    def test_4_digit_code_uses_prefix_fallback_not_default(self, prefix_mapper):
        results = prefix_mapper.map_naics_to_bea("5417")

        assert len(results) == 1
        assert results[0].source == "hierarchical_4digit"
        assert results[0].bea_sector_code == "5417B0/US"
        assert results[0].naics_code == "5417"
        assert results[0].confidence == pytest.approx(0.70)

    @pytest.mark.parametrize(
        ("code", "sector", "source"),
        [
            ("511210", "5112A0/US", "direct"),
            ("541712", "54171X/US", "hierarchical_5digit"),
            ("541799", "5417B0/US", "hierarchical_4digit"),
            ("54171", "54171X/US", "hierarchical_5digit"),
            ("5417", "5417B0/US", "hierarchical_4digit"),
            ("334", "334000/US", "hierarchical_3digit"),
            ("54", "540000/US", "hierarchical_2digit"),
            ("5413", "541300/US", "direct"),
            ("541330", "541300/US", "hierarchical_4digit"),
            ("541712.0", "54171X/US", "hierarchical_5digit"),
        ],
    )
    def test_codes_of_each_length_map_to_their_sector(self, prefix_mapper, code, sector, source):
        results = prefix_mapper.map_naics_to_bea(code)

        assert [(r.bea_sector_code, r.source) for r in results] == [(sector, source)]

    @pytest.mark.parametrize("code", ["54-17", "abc", "", "1234567", "0", "005417"])
    def test_malformed_codes_get_the_default_sector(self, prefix_mapper, code):
        results = prefix_mapper.map_naics_to_bea(code)

        assert len(results) == 1
        assert results[0].source == "default_fallback"
        assert results[0].naics_code == "UNKNOWN"

    def test_short_code_does_not_match_a_longer_sibling(self, prefix_mapper):
        """A 3-digit code must not borrow a deeper entry that shares its prefix."""
        results = prefix_mapper.map_naics_to_bea("541")

        assert [(r.bea_sector_code, r.source) for r in results] == [
            ("540000/US", "hierarchical_2digit")
        ]


# =============================================================================
# Fallback config keys load as integers (issue #886)
# =============================================================================

REAL_FALLBACK_YAML = Path(__file__).resolve().parents[3] / "config/fiscal/naics_bea_mappings.yaml"


@pytest.fixture
def real_yaml_mapper(temp_crosswalk_csv: Path) -> NAICSToBEAMapper:
    """Mapper with the small test crosswalk and the real fallback YAML."""
    return NAICSToBEAMapper(temp_crosswalk_csv, REAL_FALLBACK_YAML)


class TestRealFallbackConfig:
    """Codes in config/fiscal/naics_bea_mappings.yaml reach the fallback-config step."""

    def test_real_yaml_keys_are_canonical_strings(self, real_yaml_mapper):
        mappings = real_yaml_mapper.fallback_config["mappings"]
        assert "541712" in mappings
        assert "5415" in mappings
        assert all(isinstance(key, str) for key in mappings)
        category_defaults = real_yaml_mapper.fallback_config["fallback_rules"]["category_defaults"]
        assert all(isinstance(key, str) for key in category_defaults)

    def test_code_only_in_fallback_config_maps_through_it(self, real_yaml_mapper):
        crosswalk_codes = set(real_yaml_mapper.crosswalk_df["naics_code"])
        assert "336411" not in crosswalk_codes

        results = real_yaml_mapper.map_naics_to_bea("336411")

        assert [(r.bea_sector_code, r.source) for r in results] == [
            ("336411/US", "fallback_config")
        ]
        assert results[0].confidence == pytest.approx(0.95)

    def test_without_crosswalk_yaml_code_maps_through_fallback_config(self, tmp_path):
        mapper = NAICSToBEAMapper(tmp_path / "missing.csv", REAL_FALLBACK_YAML)

        results = mapper.map_naics_to_bea("541712")

        assert [(r.bea_sector_code, r.source) for r in results] == [
            ("540000/US", "fallback_config")
        ]
        assert results[0].confidence == pytest.approx(0.90)

    def test_6_digit_code_reaches_4_digit_fallback_entry(self, real_yaml_mapper):
        """336419 is not listed, so it uses the weighted 3364 entry."""
        results = real_yaml_mapper.map_naics_to_bea("336419")

        assert [(r.bea_sector_code, r.allocation_weight, r.source) for r in results] == [
            ("336411/US", 0.40, "fallback_config"),
            ("336412/US", 0.30, "fallback_config_weighted"),
            ("336413/US", 0.20, "fallback_config_weighted"),
            ("336414/US", 0.10, "fallback_config_weighted"),
        ]
        assert all(r.confidence == pytest.approx(0.80) for r in results)
        assert results[0].metadata["fallback_config_key"] == "3364"

    def test_code_absent_from_both_falls_to_default(self, real_yaml_mapper):
        """611310 is in neither the crosswalk nor the fallback config."""
        results = real_yaml_mapper.map_naics_to_bea("611310")

        assert [(r.bea_sector_code, r.source) for r in results] == [
            ("540000/US", "default_fallback")
        ]
        assert results[0].confidence == pytest.approx(0.30)

    def test_sibling_code_without_prefix_entry_falls_to_default(self, real_yaml_mapper):
        """336999 shares only the 336/33 prefixes with listed codes; neither is an entry."""
        results = real_yaml_mapper.map_naics_to_bea("336999")

        assert [(r.bea_sector_code, r.source) for r in results] == [
            ("540000/US", "default_fallback")
        ]
        assert results[0].bea_sector_name == "R&D and related services"

    @pytest.mark.parametrize(
        ("code", "expected_names"),
        [
            ("336411", ["Manufacturing"]),
            ("541712", ["Professional, scientific, and technical services"]),
            ("541519", ["Professional, scientific, and technical services"]),
            ("336419", ["Manufacturing"] * 4),
        ],
    )
    def test_fallback_config_rows_carry_summary_sector_name(self, tmp_path, code, expected_names):
        """Primary and secondary rows are named by their BEA Summary sector."""
        mapper = NAICSToBEAMapper(tmp_path / "missing.csv", REAL_FALLBACK_YAML)

        results = mapper.map_naics_to_bea(code)

        assert {r.source for r in results} <= {"fallback_config", "fallback_config_weighted"}
        assert [r.bea_sector_name for r in results] == expected_names

    def test_fallback_config_sector_with_unknown_summary_has_empty_name(self, tmp_path):
        """A sector code with no Summary entry gets no invented name."""
        path = tmp_path / "fallback.yaml"
        path.write_text("mappings:\n  541712:\n    primary_sector: 990000/US\n")
        mapper = NAICSToBEAMapper(tmp_path / "missing.csv", path)

        results = mapper.map_naics_to_bea("541712")

        assert [(r.source, r.bea_sector_name) for r in results] == [("fallback_config", "")]

    def test_short_code_does_not_borrow_longer_fallback_entry(self, tmp_path):
        """336 must not match 3364; only shorter prefixes are tried."""
        mapper = NAICSToBEAMapper(tmp_path / "missing.csv", REAL_FALLBACK_YAML)

        results = mapper.map_naics_to_bea("336")

        assert [r.source for r in results] == ["default_fallback"]

    def test_prefix_lookup_off_when_hierarchical_disabled(self, tmp_path):
        mapper = NAICSToBEAMapper(tmp_path / "missing.csv", REAL_FALLBACK_YAML)
        mapper.hierarchical_fallback = False

        assert mapper._map_fallback_config("336419") is None
        assert mapper._map_fallback_config("3364") is not None


class TestFallbackConfigKeyValidation:
    """Bad keys in the fallback YAML fail loudly instead of falling back."""

    @staticmethod
    def _write(tmp_path: Path, text: str) -> Path:
        path = tmp_path / "fallback.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_keys_that_collapse_to_one_code_raise(self, tmp_path):
        path = self._write(
            tmp_path,
            "mappings:\n"
            "  541712:\n    primary_sector: A/US\n"
            '  "541712":\n    primary_sector: B/US\n',
        )
        with pytest.raises(ConfigurationError, match="both normalize to '541712'"):
            NAICSToBEAMapper(tmp_path / "missing.csv", path)

    @pytest.mark.parametrize("key", ['"54-17"', "abc", '"005417"', "1234567"])
    def test_key_that_is_not_a_naics_code_raises(self, tmp_path, key):
        path = self._write(tmp_path, f"mappings:\n  {key}:\n    primary_sector: A/US\n")
        with pytest.raises(ConfigurationError, match="not a NAICS code"):
            NAICSToBEAMapper(tmp_path / "missing.csv", path)

    def test_bad_category_defaults_key_raises(self, tmp_path):
        path = self._write(
            tmp_path,
            "mappings: {}\nfallback_rules:\n  category_defaults:\n    51: A/US\n    '51': B/US\n",
        )
        with pytest.raises(ConfigurationError, match="category_defaults"):
            NAICSToBEAMapper(tmp_path / "missing.csv", path)


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

        with patch("sbir_etl.enrichers.fiscal_bea_mapper.NAICSToBEAMapper") as mock_mapper_class:
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

    def test_enrich_awards_with_bea_sectors_with_mapper(
        self, temp_crosswalk_csv, temp_fallback_yaml
    ):
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
