"""Tests for NAICS to BEA mapper."""

import csv
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.transformers.naics_to_bea import NAICSToBEAMapper


class TestNAICSToBEAMapperInitialization:
    """Tests for NAICSToBEAMapper initialization."""

    def test_initialization_default_paths(self):
        """Test initialization with default paths."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()

                assert mapper.mapping_path == "data/reference/naics_to_bea.csv"
                assert "BEA-Industry-and-Commodity-Codes" in mapper.bea_excel_path
                assert isinstance(mapper.map, dict)
                assert isinstance(mapper.multi_map, dict)

    def test_initialization_custom_paths(self):
        """Test initialization with custom paths."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper(
                    mapping_path="custom/path/mapping.csv", bea_excel_path="custom/path/bea.xlsx"
                )

                assert mapper.mapping_path == "custom/path/mapping.csv"
                assert mapper.bea_excel_path == "custom/path/bea.xlsx"

    def test_initialization_calls_load_methods(self):
        """Test that initialization calls load methods."""
        with patch.object(NAICSToBEAMapper, "_load") as mock_load:
            with patch.object(NAICSToBEAMapper, "_load_bea_excel") as mock_load_bea:
                NAICSToBEAMapper()

                mock_load.assert_called_once()
                mock_load_bea.assert_called_once()


class TestNAICSToBEAMapperCSVLoading:
    """Tests for CSV loading functionality."""

    def test_load_nonexistent_file(self):
        """Test loading when CSV file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent_path = Path(tmpdir) / "nonexistent.csv"

            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper(mapping_path=str(nonexistent_path))

                # Should not raise error, just return empty map
                assert mapper.map == {}

    def test_load_valid_csv(self):
        """Test loading valid CSV file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=["naics_prefix", "bea_sector"])
            writer.writeheader()
            writer.writerow({"naics_prefix": "11", "bea_sector": "Agriculture"})
            writer.writerow({"naics_prefix": "21", "bea_sector": "Mining"})
            f.flush()

            try:
                with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                    mapper = NAICSToBEAMapper(mapping_path=f.name)

                    assert "11" in mapper.map
                    assert mapper.map["11"] == "Agriculture"
                    assert "21" in mapper.map
                    assert mapper.map["21"] == "Mining"
            finally:
                Path(f.name).unlink()

    def test_load_csv_with_whitespace(self):
        """Test loading CSV handles whitespace."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=["naics_prefix", "bea_sector"])
            writer.writeheader()
            writer.writerow({"naics_prefix": "  11  ", "bea_sector": "  Agriculture  "})
            f.flush()

            try:
                with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                    mapper = NAICSToBEAMapper(mapping_path=f.name)

                    # Should strip whitespace
                    assert "11" in mapper.map
                    assert mapper.map["11"] == "Agriculture"
            finally:
                Path(f.name).unlink()

    def test_load_csv_missing_fields(self):
        """Test loading CSV with missing required fields."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=["naics_prefix", "bea_sector"])
            writer.writeheader()
            writer.writerow({"naics_prefix": "", "bea_sector": "Agriculture"})
            writer.writerow({"naics_prefix": "21", "bea_sector": ""})
            f.flush()

            try:
                with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                    mapper = NAICSToBEAMapper(mapping_path=f.name)

                    # Should skip rows with empty required fields
                    assert len(mapper.map) == 0
            finally:
                Path(f.name).unlink()


class TestNAICSToBEAMapperExcelLoading:
    """Tests for Excel loading functionality."""

    @patch("pandas.read_excel")
    def test_load_bea_excel_nonexistent(self, mock_read_excel):
        """Test loading when Excel file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent_path = Path(tmpdir) / "nonexistent.xlsx"

            with patch.object(NAICSToBEAMapper, "_load"):
                mapper = NAICSToBEAMapper(bea_excel_path=str(nonexistent_path))

                # Should not raise error, just return empty multi_map
                assert mapper.multi_map == {}
                # read_excel should not be called
                mock_read_excel.assert_not_called()

    @patch("pandas.read_excel")
    @patch("pathlib.Path.exists")
    def test_load_bea_excel_read_error(self, mock_exists, mock_read_excel):
        """Test handling of Excel read errors."""
        mock_exists.return_value = True
        mock_read_excel.side_effect = Exception("Read error")

        with patch.object(NAICSToBEAMapper, "_load"):
            mapper = NAICSToBEAMapper(bea_excel_path="test.xlsx")

            # Should handle error gracefully
            assert mapper.multi_map == {}

    @patch("pandas.read_excel")
    @patch("pathlib.Path.exists")
    def test_load_bea_excel_valid(self, mock_exists, mock_read_excel):
        """Test loading valid Excel file."""
        mock_exists.return_value = True
        mock_df = pd.DataFrame(
            {
                "BEA Code": ["11", "21", "22"],
                "BEA Industry": ["Agriculture", "Mining", "Utilities"],
                "NAICS Code": ["111, 112", "211", "221"],
                "NAICS Description": ["Crop, Animal", "Oil and Gas", "Utilities"],
            }
        )
        mock_read_excel.return_value = mock_df

        with patch.object(NAICSToBEAMapper, "_load"):
            mapper = NAICSToBEAMapper(bea_excel_path="test.xlsx")

            assert "11" in mapper.multi_map
            assert "111" in mapper.multi_map["11"]
            assert "112" in mapper.multi_map["11"]
            assert "21" in mapper.multi_map
            assert "211" in mapper.multi_map["21"]

    @patch("pandas.read_excel")
    @patch("pathlib.Path.exists")
    def test_load_bea_excel_semicolon_separator(self, mock_exists, mock_read_excel):
        """Test loading Excel with semicolon-separated NAICS codes."""
        mock_exists.return_value = True
        mock_df = pd.DataFrame(
            {
                "BEA Code": ["11"],
                "BEA Industry": ["Agriculture"],
                "NAICS Code": ["111; 112; 113"],
                "NAICS Description": ["Agriculture"],
            }
        )
        mock_read_excel.return_value = mock_df

        with patch.object(NAICSToBEAMapper, "_load"):
            mapper = NAICSToBEAMapper(bea_excel_path="test.xlsx")

            assert "111" in mapper.multi_map["11"]
            assert "112" in mapper.multi_map["11"]
            assert "113" in mapper.multi_map["11"]

    @patch("pandas.read_excel")
    @patch("pathlib.Path.exists")
    def test_load_bea_excel_empty_fields(self, mock_exists, mock_read_excel):
        """Test loading Excel with empty fields."""
        mock_exists.return_value = True
        mock_df = pd.DataFrame(
            {
                "BEA Code": ["", "21"],
                "BEA Industry": ["", "Mining"],
                "NAICS Code": ["111", ""],
                "NAICS Description": ["", ""],
            }
        )
        mock_read_excel.return_value = mock_df

        with patch.object(NAICSToBEAMapper, "_load"):
            mapper = NAICSToBEAMapper(bea_excel_path="test.xlsx")

            # Should skip rows with empty required fields
            assert len(mapper.multi_map) == 0


class TestNAICSToBEAMapperCodeMapping:
    """Tests for map_code functionality."""

    def test_map_code_empty(self):
        """Test mapping empty NAICS code."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {"11": "Agriculture"}

                result = mapper.map_code("")
                assert result is None

    def test_map_code_none(self):
        """Test mapping None NAICS code."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {"11": "Agriculture"}

                result = mapper.map_code(None)
                assert result is None

    def test_map_code_exact_match(self):
        """Test mapping with exact prefix match."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {"111": "Crop Production"}

                result = mapper.map_code("111")
                assert result == "Crop Production"

    def test_map_code_longest_prefix(self):
        """Test mapping uses longest prefix match."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {
                    "11": "Agriculture",
                    "111": "Crop Production",
                    "1111": "Oilseed Farming",
                }

                # Should match longest prefix
                result = mapper.map_code("111150")
                assert result == "Oilseed Farming"

    def test_map_code_fallback_to_shorter_prefix(self):
        """Test mapping falls back to shorter prefix."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {
                    "11": "Agriculture",
                    "111": "Crop Production",
                }

                # Should match '111' prefix
                result = mapper.map_code("111999")
                assert result == "Crop Production"

    def test_map_code_two_digit_fallback(self):
        """Test mapping falls back to 2-digit prefix."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {"11": "Agriculture"}

                result = mapper.map_code("119999")
                assert result == "Agriculture"

    def test_map_code_no_match(self):
        """Test mapping with no matching prefix."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {"11": "Agriculture"}

                result = mapper.map_code("999999")
                assert result is None

    def test_map_code_whitespace_handling(self):
        """Test mapping handles whitespace in code."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {"111": "Crop Production"}

                result = mapper.map_code("  111  ")
                assert result == "Crop Production"

    def test_map_code_bea_vintage(self):
        """Test mapping with BEA vintage uses multi_map."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.multi_map = {
                    "11": ["111", "112", "113"],
                    "21": ["211", "212"],
                }

                result = mapper.map_code("111", vintage="bea")
                assert result == ["11"]

    def test_map_code_bea_vintage_multiple_matches(self):
        """Test BEA vintage mapping can return multiple matches."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.multi_map = {
                    "11": ["111", "112"],
                    "11-CA": ["111", "113"],  # Overlapping
                }

                result = mapper.map_code("111", vintage="bea")
                assert isinstance(result, list)
                assert "11" in result

    def test_map_code_bea_vintage_no_match(self):
        """Test BEA vintage mapping with no match."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.multi_map = {"11": ["111", "112"]}

                result = mapper.map_code("999", vintage="bea")
                assert result is None


class TestNAICSToBEAMapperEdgeCases:
    """Tests for edge cases in NAICS to BEA mapping."""

    def test_single_digit_code(self):
        """Test mapping with single digit code."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {"1": "Agriculture Sector"}

                # Single digit codes won't match (loop starts at len-1, min 2)
                result = mapper.map_code("1")
                assert result is None

    def test_very_long_code(self):
        """Test mapping with very long NAICS code."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {"111": "Crop Production"}

                result = mapper.map_code("111111111111")
                assert result == "Crop Production"

    def test_numeric_string_code(self):
        """Test mapping preserves numeric strings."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {"111": "Crop Production"}

                result = mapper.map_code("111000")
                assert isinstance(result, str)
                assert result == "Crop Production"

    def test_multiple_bea_codes_same_naics(self):
        """Test multi_map with same NAICS code in multiple BEA codes."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.multi_map = {
                    "11": ["111", "112"],
                    "11-CA": ["111"],  # 111 appears in both
                }

                result = mapper.map_code("111", vintage="bea")
                assert isinstance(result, list)
                assert len(result) >= 1

    def test_empty_multi_map(self):
        """Test BEA vintage with empty multi_map."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.multi_map = {}

                result = mapper.map_code("111", vintage="bea")
                assert result is None

    def test_default_vintage_with_multi_map_populated(self):
        """Test default vintage ignores multi_map."""
        with patch.object(NAICSToBEAMapper, "_load"):
            with patch.object(NAICSToBEAMapper, "_load_bea_excel"):
                mapper = NAICSToBEAMapper()
                mapper.map = {"111": "Crop Production"}
                mapper.multi_map = {"11": ["111", "112"]}

                # Default vintage should use map, not multi_map
                result = mapper.map_code("111")
                assert result == "Crop Production"
                assert not isinstance(result, list)
