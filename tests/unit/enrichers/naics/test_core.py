"""Tests for NAICS enrichment core utilities."""

import gzip
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.enrichers.naics.core import NAICS_RE, RECIPIENT_UEI_RE, NAICSEnricher, NAICSEnricherConfig


# ==================== Fixtures ====================


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_config(tmp_path):
    """Sample NAICS enricher config."""
    return NAICSEnricherConfig(
        zip_path=str(tmp_path / "usaspending.zip"),
        cache_path=str(tmp_path / "naics_index.parquet"),
        sample_only=True,
        max_files=6,
        max_lines_per_file=1000,
    )


@pytest.fixture
def enricher(sample_config):
    """NAICS enricher instance."""
    with patch("pathlib.Path.exists", return_value=False):
        return NAICSEnricher(sample_config)


@pytest.fixture
def sample_dump_lines():
    """Sample USAspending dump lines."""
    return [
        "123456 CONT_AWD_2023 541511 UEI12345ABCD Contract Data Systems 2023-01-15",
        "234567 CONT_AWD_2023 541512 UEI67890EFGH Software Development Corp 2023-02-20",
        "345678 CONT_AWD_2023 336411 AERO123XYZ Aerospace Manufacturing Inc 2023-03-10",
        "456789 IDV_AWD_2023 541330 UEI456TECH Engineering Services LLC 2023-04-05",
    ]


@pytest.fixture
def sample_awards_df():
    """Sample awards DataFrame."""
    return pd.DataFrame(
        {
            "award_id": ["123456", "234567", "999999"],
            "recipient_uei": ["UEI12345ABCD", "UEI67890EFGH", "UNKNOWN_UEI"],
            "company": ["Data Systems", "Software Corp", "Unknown Co"],
        }
    )


# ==================== Regex Pattern Tests ====================


class TestRegexPatterns:
    """Tests for regex pattern matching."""

    def test_naics_re_matches_valid_codes(self):
        """Test NAICS regex matches valid 2-6 digit codes."""
        text = "The company has NAICS codes 541511, 541512, and 11."
        matches = NAICS_RE.findall(text)

        assert "541511" in matches
        assert "541512" in matches
        assert "11" in matches

    def test_naics_re_excludes_single_digit(self):
        """Test NAICS regex excludes single digit."""
        text = "Code 5 is too short"
        matches = NAICS_RE.findall(text)

        assert "5" not in matches

    def test_naics_re_excludes_too_long(self):
        """Test NAICS regex matches up to 6 digits."""
        text = "Valid: 541511, Invalid: 12345678"
        matches = NAICS_RE.findall(text)

        assert "541511" in matches
        # Regex allows 2-6, so 12345678 should not match as a whole
        assert "12345678" not in matches

    def test_recipient_uei_re_matches_valid_uei(self):
        """Test UEI regex matches alphanumeric 8-20 char codes."""
        text = "UEI codes: UEI12345ABCD, VALIDUEI123456, X"
        matches = RECIPIENT_UEI_RE.findall(text)

        assert "UEI12345ABCD" in matches
        assert "VALIDUEI123456" in matches

    def test_recipient_uei_re_excludes_short(self):
        """Test UEI regex excludes codes < 8 chars."""
        text = "Short codes: ABC, XYZ12"
        matches = RECIPIENT_UEI_RE.findall(text)

        # These are too short (< 8 chars)
        assert "ABC" not in matches


# ==================== Config Tests ====================


class TestNAICSEnricherConfig:
    """Tests for NAICSEnricherConfig dataclass."""

    def test_initialization_with_defaults(self):
        """Test config initialization with defaults."""
        config = NAICSEnricherConfig(zip_path="/path/to/data.zip")

        assert config.zip_path == "/path/to/data.zip"
        assert config.cache_path == "data/processed/usaspending/naics_index.parquet"
        assert config.sample_only is True
        assert config.max_files == 6
        assert config.max_lines_per_file == 1000

    def test_initialization_with_custom_values(self):
        """Test config initialization with custom values."""
        config = NAICSEnricherConfig(
            zip_path="/custom/path.zip",
            cache_path="/custom/cache.parquet",
            sample_only=False,
            max_files=10,
            max_lines_per_file=5000,
        )

        assert config.zip_path == "/custom/path.zip"
        assert config.cache_path == "/custom/cache.parquet"
        assert config.sample_only is False
        assert config.max_files == 10
        assert config.max_lines_per_file == 5000


# ==================== Initialization Tests ====================


class TestNAICSEnricherInitialization:
    """Tests for NAICSEnricher initialization."""

    def test_initialization_without_reference_file(self, sample_config):
        """Test initialization when NAICS reference file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            enricher = NAICSEnricher(sample_config)

        assert enricher.config == sample_config
        assert enricher.award_map == {}
        assert enricher.recipient_map == {}
        assert enricher.valid_naics_set == set()

    def test_initialization_with_reference_file(self, sample_config, tmp_path):
        """Test initialization with NAICS reference file."""
        Path("data/reference/naics_codes.txt")
        naics_codes = ["541511", "541512", "336411", "541330"]

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value="\n".join(naics_codes)):
                enricher = NAICSEnricher(sample_config)

        assert enricher.valid_naics_set == set(naics_codes)

    def test_initialization_handles_reference_file_error(self, sample_config):
        """Test initialization handles error reading reference file."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", side_effect=OSError("Read error")):
                enricher = NAICSEnricher(sample_config)

        # Should gracefully handle error and continue with empty set
        assert enricher.valid_naics_set == set()


# ==================== Line Processing Tests ====================


class TestLineProcessing:
    """Tests for _process_line heuristic extraction."""

    def test_process_line_extracts_award_and_naics(self, enricher):
        """Test line processing extracts award ID and NAICS code."""
        line = "123456 CONT_AWD_2023 541511 Data Corp 2023-01-15"

        enricher._process_line(line)

        assert "123456" in enricher.award_map
        assert "541511" in enricher.award_map["123456"]

    def test_process_line_filters_year_tokens(self, enricher):
        """Test line processing filters out year tokens (1900-2099)."""
        line = "123456 CONT_AWD 541511 2023 1995 2050"

        enricher._process_line(line)

        assert "541511" in enricher.award_map["123456"]
        assert "2023" not in enricher.award_map["123456"]
        assert "1995" not in enricher.award_map["123456"]
        assert "2050" not in enricher.award_map["123456"]

    def test_process_line_filters_invalid_naics(self, enricher):
        """Test line processing filters invalid NAICS codes."""
        # 2-digit codes < 11, 3+ digit codes < 100
        line = "123456 CONT 05 99 11 541511"

        enricher._process_line(line)

        assert "05" not in enricher.award_map["123456"]
        assert "99" not in enricher.award_map["123456"]
        assert "11" in enricher.award_map["123456"]  # Valid 2-digit
        assert "541511" in enricher.award_map["123456"]

    def test_process_line_extracts_recipient_uei(self, enricher):
        """Test line processing extracts recipient UEI tokens."""
        line = "123456 CONT 541511 UEI12345ABCD Company"

        enricher._process_line(line)

        assert "UEI12345ABCD" in enricher.recipient_map
        assert "541511" in enricher.recipient_map["UEI12345ABCD"]

    def test_process_line_skips_empty_lines(self, enricher):
        """Test line processing skips empty lines."""
        enricher._process_line("")
        enricher._process_line("   ")

        assert enricher.award_map == {}
        assert enricher.recipient_map == {}

    def test_process_line_skips_lines_without_naics(self, enricher):
        """Test line processing skips lines without NAICS codes."""
        line = "Some text without any numeric codes"

        enricher._process_line(line)

        assert enricher.award_map == {}

    def test_process_line_normalizes_naics_codes(self, enricher):
        """Test line processing normalizes NAICS codes (drops leading zeros)."""
        line = "123456 CONT 0541511 00336411"

        enricher._process_line(line)

        # Should normalize to string without leading zeros
        assert "541511" in enricher.award_map["123456"]
        assert "336411" in enricher.award_map["123456"]

    def test_process_line_filters_overly_large_codes(self, enricher):
        """Test line processing filters codes > 999999."""
        line = "123456 CONT 541511 9999999"

        enricher._process_line(line)

        assert "541511" in enricher.award_map["123456"]
        assert "9999999" not in enricher.award_map["123456"]

    def test_process_line_maps_to_multiple_recipients(self, enricher):
        """Test line processing maps NAICS to multiple recipient candidates."""
        line = "123456 541511 UEI123ALPHA UEI456BETA"

        enricher._process_line(line)

        assert "541511" in enricher.recipient_map["UEI123ALPHA"]
        assert "541511" in enricher.recipient_map["UEI456BETA"]

    def test_process_line_finds_award_id_in_first_three_tokens(self, enricher):
        """Test award ID extraction looks at first 3 tokens only."""
        # Award ID should be found in first 3 tokens
        line1 = "123456 CONT AWD 541511"
        line2 = "PREFIX 234567 CONT 541512"
        line3 = "X Y 345678 CONT 541330"
        line4 = "A B C 456789 CONT 541511"  # 4th position, should not find

        enricher._process_line(line1)
        enricher._process_line(line2)
        enricher._process_line(line3)
        enricher._process_line(line4)

        assert "123456" in enricher.award_map
        assert "234567" in enricher.award_map
        assert "345678" in enricher.award_map
        assert "456789" not in enricher.award_map  # Too far in


# ==================== Index Loading Tests ====================


class TestIndexLoading:
    """Tests for load_usaspending_index."""

    def test_load_from_cache_success(self, enricher, tmp_path):
        """Test loading index from cached Parquet file."""
        cache_data = pd.DataFrame(
            [
                {"key_type": "award", "key": "123456", "naics_candidates": ["541511", "541512"]},
                {"key_type": "recipient", "key": "UEI12345ABCD", "naics_candidates": ["336411"]},
            ]
        )

        cache_path = tmp_path / "naics_index.parquet"
        cache_data.to_parquet(cache_path)
        enricher.config.cache_path = str(cache_path)

        enricher.load_usaspending_index()

        assert "123456" in enricher.award_map
        assert enricher.award_map["123456"] == {"541511", "541512"}
        assert "UEI12345ABCD" in enricher.recipient_map
        assert enricher.recipient_map["UEI12345ABCD"] == {"336411"}

    def test_load_from_cache_handles_none_naics(self, enricher, tmp_path):
        """Test loading handles None in naics_candidates."""
        cache_data = pd.DataFrame(
            [
                {"key_type": "award", "key": "123456", "naics_candidates": None},
            ]
        )

        cache_path = tmp_path / "naics_index.parquet"
        cache_data.to_parquet(cache_path)
        enricher.config.cache_path = str(cache_path)

        enricher.load_usaspending_index()

        assert "123456" in enricher.award_map
        assert enricher.award_map["123456"] == set()

    def test_load_from_cache_handles_json_strings(self, enricher, tmp_path):
        """Test loading handles JSON string format."""
        cache_data = pd.DataFrame(
            [
                {"key_type": "award", "key": "123456", "naics_candidates": '["541511", "541512"]'},
            ]
        )

        cache_path = tmp_path / "naics_index.parquet"
        cache_data.to_parquet(cache_path)
        enricher.config.cache_path = str(cache_path)

        enricher.load_usaspending_index()

        assert "123456" in enricher.award_map
        assert enricher.award_map["123456"] == {"541511", "541512"}

    def test_load_from_zip_missing_file(self, enricher):
        """Test loading raises error when zip file doesn't exist."""
        enricher.config.cache_path = "/nonexistent/cache.parquet"
        enricher.config.zip_path = "/nonexistent/data.zip"

        with pytest.raises(FileNotFoundError, match="USAspending zip not found"):
            enricher.load_usaspending_index()

    def test_load_from_zip_processes_files(self, enricher, tmp_path, sample_dump_lines):
        """Test loading builds index from zip file."""
        # Create test zip with gzipped dump file
        zip_path = tmp_path / "usaspending.zip"
        enricher.config.zip_path = str(zip_path)
        enricher.config.cache_path = str(tmp_path / "cache.parquet")

        with zipfile.ZipFile(zip_path, "w") as zf:
            # Create gzipped content
            gz_content = gzip.compress("\n".join(sample_dump_lines).encode("utf-8"))
            zf.writestr("pruned_data_store_api_dump/test.dat.gz", gz_content)

        enricher.load_usaspending_index()

        # Should have extracted NAICS codes from sample lines
        assert "123456" in enricher.award_map
        assert "541511" in enricher.award_map["123456"]

    def test_load_from_zip_respects_sample_limits(self, enricher, tmp_path):
        """Test loading respects sample_only limits."""
        enricher.config.sample_only = True
        enricher.config.max_files = 1
        enricher.config.max_lines_per_file = 2

        zip_path = tmp_path / "usaspending.zip"
        enricher.config.zip_path = str(zip_path)
        enricher.config.cache_path = str(tmp_path / "cache.parquet")

        lines = [f"{100000 + i} CONT {541511 + i} UEITEST{i}" for i in range(10)]

        with zipfile.ZipFile(zip_path, "w") as zf:
            for i in range(5):
                gz_content = gzip.compress("\n".join(lines).encode("utf-8"))
                zf.writestr(f"pruned_data_store_api_dump/file{i}.dat.gz", gz_content)

        enricher.load_usaspending_index()

        # Should process only 1 file, 2 lines per file
        assert len(enricher.award_map) <= 2

    def test_load_from_zip_filters_invalid_naics(self, enricher, tmp_path):
        """Test loading filters invalid NAICS codes before persisting."""
        enricher.config.zip_path = str(tmp_path / "usaspending.zip")
        enricher.config.cache_path = str(tmp_path / "cache.parquet")

        lines = [
            "123456 CONT 541511 999999",  # Valid and invalid
            "234567 CONT 05 99",  # Both invalid
        ]

        with zipfile.ZipFile(tmp_path / "usaspending.zip", "w") as zf:
            gz_content = gzip.compress("\n".join(lines).encode("utf-8"))
            zf.writestr("pruned_data_store_api_dump/test.dat.gz", gz_content)

        enricher.load_usaspending_index()

        # Load persisted cache to verify filtering
        cache_df = pd.read_parquet(enricher.config.cache_path)

        # Should only have valid codes
        award_row = cache_df[cache_df["key"] == "123456"]
        if not award_row.empty:
            candidates = award_row.iloc[0]["naics_candidates"]
            assert "541511" in candidates
            assert 999999 not in candidates  # Too large

    def test_load_force_rebuild(self, enricher, tmp_path):
        """Test force=True rebuilds index even if cache exists."""
        cache_path = tmp_path / "cache.parquet"
        old_data = pd.DataFrame(
            [
                {"key_type": "award", "key": "OLD", "naics_candidates": ["999999"]},
            ]
        )
        old_data.to_parquet(cache_path)

        enricher.config.cache_path = str(cache_path)
        enricher.config.zip_path = str(tmp_path / "usaspending.zip")

        # Create new zip with different data
        with zipfile.ZipFile(tmp_path / "usaspending.zip", "w") as zf:
            gz_content = gzip.compress(b"123456 CONT 541511")
            zf.writestr("pruned_data_store_api_dump/new.dat.gz", gz_content)

        enricher.load_usaspending_index(force=True)

        # Should rebuild from zip, not load old cache
        assert "123456" in enricher.award_map
        assert "OLD" not in enricher.award_map


# ==================== Award Enrichment Tests ====================


class TestAwardEnrichment:
    """Tests for enrich_awards method."""

    def test_enrich_awards_by_award_id(self, enricher, sample_awards_df):
        """Test enrichment using award-level NAICS mapping."""
        enricher.award_map = {
            "123456": {"541511", "541512"},
            "234567": {"336411"},
        }

        result = enricher.enrich_awards(sample_awards_df)

        assert result.loc[0, "naics_assigned"] == "541511"  # First sorted candidate
        assert result.loc[0, "naics_origin"] == "usaspending_award"
        assert result.loc[0, "naics_confidence"] == 0.85
        assert result.loc[1, "naics_assigned"] == "336411"

    def test_enrich_awards_fallback_to_recipient(self, enricher, sample_awards_df):
        """Test enrichment falls back to recipient-level mapping."""
        enricher.award_map = {}  # No award-level mappings
        enricher.recipient_map = {
            "UEI12345ABCD": {"541330"},
            "UEI67890EFGH": {"541519"},
        }

        result = enricher.enrich_awards(sample_awards_df)

        assert result.loc[0, "naics_assigned"] == "541330"
        assert result.loc[0, "naics_origin"] == "usaspending_recipient"
        assert result.loc[0, "naics_confidence"] == 0.7
        assert result.loc[1, "naics_assigned"] == "541519"

    def test_enrich_awards_missing_data(self, enricher, sample_awards_df):
        """Test enrichment handles missing NAICS data."""
        enricher.award_map = {}
        enricher.recipient_map = {}

        result = enricher.enrich_awards(sample_awards_df)

        assert pd.isna(result.loc[0, "naics_assigned"])
        assert result.loc[0, "naics_origin"] == "unknown"
        assert result.loc[0, "naics_confidence"] == 0.0
        assert "missing" in result.loc[0, "naics_quality_flags"]

    def test_enrich_awards_includes_trace(self, enricher, sample_awards_df):
        """Test enrichment includes trace information."""
        enricher.award_map = {
            "123456": {"541511", "541512", "541519"},
        }

        result = enricher.enrich_awards(sample_awards_df)

        trace = json.loads(result.loc[0, "naics_trace"])
        assert trace[0]["source"] == "usaspending_award"
        assert "541511" in trace[0]["candidates"]
        assert "541512" in trace[0]["candidates"]

    def test_enrich_awards_with_custom_columns(self, enricher):
        """Test enrichment with custom column names."""
        df = pd.DataFrame(
            {
                "custom_award": ["123456"],
                "custom_uei": ["UEI12345ABCD"],
            }
        )
        enricher.award_map = {"123456": {"541511"}}

        result = enricher.enrich_awards(
            df,
            award_id_col="custom_award",
            recipient_uei_col="custom_uei",
        )

        assert result.loc[0, "naics_assigned"] == "541511"

    def test_enrich_awards_returns_copy(self, enricher, sample_awards_df):
        """Test enrichment returns a copy, not modifying original."""
        original_cols = sample_awards_df.columns.tolist()
        enricher.award_map = {"123456": {"541511"}}

        result = enricher.enrich_awards(sample_awards_df)

        # Original should be unchanged
        assert sample_awards_df.columns.tolist() == original_cols
        assert "naics_assigned" not in sample_awards_df.columns
        assert "naics_assigned" in result.columns

    def test_enrich_awards_sorts_candidates(self, enricher, sample_awards_df):
        """Test enrichment uses first sorted candidate."""
        enricher.award_map = {
            "123456": {"541519", "336411", "541511"},  # Unsorted
        }

        result = enricher.enrich_awards(sample_awards_df)

        # Should pick first after sorting: 336411 < 541511 < 541519
        assert result.loc[0, "naics_assigned"] == "336411"


# ==================== Edge Cases and Error Handling ====================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_process_line_handles_decode_errors(self, enricher):
        """Test line processing handles decode errors gracefully."""
        # Should not raise, just skip malformed data
        enricher._process_line(b"\xff\xfe invalid bytes".decode("utf-8", errors="ignore"))

        # Should continue without crashing
        assert enricher.award_map == {}

    def test_load_handles_corrupt_zip_member(self, enricher, tmp_path):
        """Test loading handles corrupt zip members gracefully."""
        zip_path = tmp_path / "corrupt.zip"
        enricher.config.zip_path = str(zip_path)
        enricher.config.cache_path = str(tmp_path / "cache.parquet")

        with zipfile.ZipFile(zip_path, "w") as zf:
            # Add member that can't be decompressed
            zf.writestr("pruned_data_store_api_dump/corrupt.dat.gz", b"not gzipped")

        # Should handle error and continue
        enricher.load_usaspending_index()

        # Should still create cache (even if empty)
        assert Path(enricher.config.cache_path).exists()

    def test_enrich_awards_empty_dataframe(self, enricher):
        """Test enrichment handles empty DataFrame."""
        empty_df = pd.DataFrame()

        result = enricher.enrich_awards(empty_df)

        # Should return empty DataFrame with new columns
        assert len(result) == 0
        assert "naics_assigned" in result.columns

    def test_enrich_awards_missing_columns(self, enricher):
        """Test enrichment handles missing expected columns."""
        df = pd.DataFrame({"other_col": ["value"]})
        enricher.award_map = {}
        enricher.recipient_map = {}

        result = enricher.enrich_awards(df, award_id_col="missing", recipient_uei_col="missing")

        # Should handle gracefully with missing flags
        assert pd.isna(result.loc[0, "naics_assigned"])
        assert "missing" in result.loc[0, "naics_quality_flags"]

    def test_process_line_no_award_id_but_has_naics(self, enricher):
        """Test line processing when NAICS found but no award ID."""
        # Use a 5-digit NAICS code so it doesn't match the 6+ digit award ID pattern
        line = "SHORT 54151 UEI12345ABCD"  # No 6+ digit award ID

        enricher._process_line(line)

        # Should still map to recipient
        assert "UEI12345ABCD" in enricher.recipient_map
        assert enricher.award_map == {}

    def test_load_cache_creates_parent_directory(self, enricher, tmp_path):
        """Test loading creates cache parent directory if needed."""
        nested_cache = tmp_path / "nested" / "dirs" / "cache.parquet"
        enricher.config.cache_path = str(nested_cache)
        enricher.config.zip_path = str(tmp_path / "usaspending.zip")

        # Create minimal zip
        with zipfile.ZipFile(tmp_path / "usaspending.zip", "w") as zf:
            gz_content = gzip.compress(b"123456 CONT 541511")
            zf.writestr("pruned_data_store_api_dump/test.dat.gz", gz_content)

        enricher.load_usaspending_index()

        assert nested_cache.parent.exists()
        assert nested_cache.exists()
