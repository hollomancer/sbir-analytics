"""Unit tests for NAICS-BEA mapper."""

import pytest

from src.transformers.naics_bea_mapper import NAICSBEAMapper


pytestmark = pytest.mark.fast


class TestNAICSBEAMapper:
    """Test NAICS to BEA sector code mapping."""

    @pytest.fixture
    def mapper(self):
        """Create mapper instance."""
        return NAICSBEAMapper()

    def test_map_agriculture(self, mapper):
        """Test mapping agriculture NAICS to BEA."""
        assert mapper.map_naics_to_bea_summary("111110") == "11"
        assert mapper.map_naics_to_bea_summary("112111") == "11"
        assert mapper.map_naics_to_bea_summary("11") == "11"

    def test_map_manufacturing(self, mapper):
        """Test mapping manufacturing NAICS to BEA."""
        # All manufacturing (31-33) should map to "31-33"
        assert mapper.map_naics_to_bea_summary("311111") == "31-33"
        assert mapper.map_naics_to_bea_summary("321113") == "31-33"
        assert mapper.map_naics_to_bea_summary("332721") == "31-33"

    def test_map_professional_services(self, mapper):
        """Test mapping professional services NAICS to BEA."""
        assert mapper.map_naics_to_bea_summary("541512") == "54"
        assert mapper.map_naics_to_bea_summary("541330") == "54"

    def test_map_information(self, mapper):
        """Test mapping information sector NAICS to BEA."""
        assert mapper.map_naics_to_bea_summary("511210") == "51"
        assert mapper.map_naics_to_bea_summary("517311") == "51"

    def test_map_2digit_naics(self, mapper):
        """Test mapping 2-digit NAICS codes."""
        assert mapper.map_naics_to_bea_summary("54") == "54"
        assert mapper.map_naics_to_bea_summary("62") == "62"

    def test_map_retail_trade(self, mapper):
        """Test mapping retail trade (combined 44-45)."""
        assert mapper.map_naics_to_bea_summary("441110") == "44-45"
        assert mapper.map_naics_to_bea_summary("452111") == "44-45"

    def test_map_transportation(self, mapper):
        """Test mapping transportation (combined 48-49)."""
        assert mapper.map_naics_to_bea_summary("481111") == "48-49"
        assert mapper.map_naics_to_bea_summary("492110") == "48-49"

    def test_map_unknown_naics(self, mapper):
        """Test mapping unknown NAICS code (uses 2-digit as fallback)."""
        # NAICS code 99 doesn't exist, should fall back to using the prefix
        result = mapper.map_naics_to_bea_summary("999999")
        assert result == "99"  # Fallback to 2-digit

    def test_map_empty_naics_raises(self, mapper):
        """Test that empty NAICS raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            mapper.map_naics_to_bea_summary("")

    def test_map_short_naics_raises(self, mapper):
        """Test that too-short NAICS raises error."""
        with pytest.raises(ValueError, match="too short"):
            mapper.map_naics_to_bea_summary("1")

    def test_map_naics_series(self, mapper):
        """Test mapping multiple NAICS codes."""
        naics_codes = ["111110", "541512", "311111", "621111"]
        expected = ["11", "54", "31-33", "62"]

        result = mapper.map_naics_series(naics_codes)
        assert result == expected

    def test_validate_bea_code(self, mapper):
        """Test BEA code validation."""
        assert mapper.validate_bea_code("54") is True
        assert mapper.validate_bea_code("31-33") is True
        assert mapper.validate_bea_code("99") is False
        assert mapper.validate_bea_code("invalid") is False

    def test_get_bea_code_description(self, mapper):
        """Test getting BEA code descriptions."""
        desc = mapper.get_bea_code_description("54")
        assert "Professional" in desc
        assert "scientific" in desc.lower()

        desc_mfg = mapper.get_bea_code_description("31-33")
        assert "Manufacturing" in desc_mfg

    def test_get_unknown_bea_description(self, mapper):
        """Test getting description for unknown BEA code."""
        desc = mapper.get_bea_code_description("99")
        assert "Unknown" in desc or "99" in desc
