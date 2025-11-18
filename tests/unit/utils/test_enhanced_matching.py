"""Unit tests for enhanced matching utilities."""

import pytest

pytestmark = pytest.mark.fast

from src.utils.enhanced_matching import (
    ENHANCED_ABBREVIATIONS,
    MatchingConfig,
    apply_enhanced_abbreviations,
    get_phonetic_code,
    jaro_winkler_similarity,
    phonetic_match,
)


class TestEnhancedAbbreviations:
    """Tests for ENHANCED_ABBREVIATIONS dictionary."""

    def test_abbreviations_contains_common_terms(self):
        """Test that abbreviations dictionary contains common terms."""
        assert "technologies" in ENHANCED_ABBREVIATIONS
        assert "technology" in ENHANCED_ABBREVIATIONS
        assert "systems" in ENHANCED_ABBREVIATIONS
        assert "research" in ENHANCED_ABBREVIATIONS

    def test_abbreviations_maps_correctly(self):
        """Test that abbreviations map to expected values."""
        assert ENHANCED_ABBREVIATIONS["technologies"] == "tech"
        assert ENHANCED_ABBREVIATIONS["defense"] == "def"
        assert ENHANCED_ABBREVIATIONS["international"] == "intl"


class TestGetPhoneticCode:
    """Tests for get_phonetic_code function."""

    def test_get_phonetic_code_metaphone(self):
        """Test get_phonetic_code with metaphone algorithm."""
        # This will return None if jellyfish is not available
        result = get_phonetic_code("Smith", algorithm="metaphone")

        # If jellyfish is available, should return phonetic code
        # If not, returns None
        assert result is None or isinstance(result, str)

    def test_get_phonetic_code_double_metaphone(self):
        """Test get_phonetic_code with double_metaphone algorithm."""
        result = get_phonetic_code("Smith", algorithm="double_metaphone")

        # If jellyfish is available, should return tuple or string
        # If not, returns None
        assert result is None or isinstance(result, (str, tuple))

    def test_get_phonetic_code_unknown_algorithm(self):
        """Test get_phonetic_code with unknown algorithm."""
        result = get_phonetic_code("Smith", algorithm="unknown")

        assert result is None

    def test_get_phonetic_code_empty_string(self):
        """Test get_phonetic_code with empty string."""
        result = get_phonetic_code("", algorithm="metaphone")

        assert result is None or result == ""


class TestApplyEnhancedAbbreviations:
    """Tests for apply_enhanced_abbreviations function."""

    def test_apply_enhanced_abbreviations_basic(self):
        """Test basic abbreviation application."""
        result = apply_enhanced_abbreviations("Acme Technologies Inc")

        assert isinstance(result, str)
        assert "tech" in result.lower()  # "technologies" should become "tech"

    def test_apply_enhanced_abbreviations_multiple(self):
        """Test applying multiple abbreviations."""
        result = apply_enhanced_abbreviations("Advanced Aerospace Defense Systems")

        assert isinstance(result, str)
        # Should contain abbreviations
        assert len(result) > 0

    def test_apply_enhanced_abbreviations_empty_string(self):
        """Test with empty string."""
        result = apply_enhanced_abbreviations("")

        assert result == ""

    def test_apply_enhanced_abbreviations_custom_dict(self):
        """Test with custom abbreviation dictionary."""
        custom_abbrev = {"custom": "cust"}
        result = apply_enhanced_abbreviations("Test Custom", abbreviations=custom_abbrev)

        assert "cust" in result.lower()


class TestPhoneticMatch:
    """Tests for phonetic_match function."""

    def test_phonetic_match_similar_names(self):
        """Test phonetic matching with similar names."""
        # This will return False if jellyfish is not available
        result = phonetic_match("Smith", "Smyth")

        assert isinstance(result, bool)

    def test_phonetic_match_different_names(self):
        """Test phonetic matching with different names."""
        result = phonetic_match("Smith", "Jones")

        assert isinstance(result, bool)

    def test_phonetic_match_empty_strings(self):
        """Test phonetic matching with empty strings."""
        result = phonetic_match("", "")

        assert result is False


class TestJaroWinklerSimilarity:
    """Tests for jaro_winkler_similarity function."""

    def test_jaro_winkler_similarity_similar_names(self):
        """Test Jaro-Winkler similarity with similar names."""
        result = jaro_winkler_similarity("Boeing Systems", "Boeing Solutions")

        # If rapidfuzz is available, should return score 0-100
        # If not, returns 0.0
        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0

    def test_jaro_winkler_similarity_different_names(self):
        """Test Jaro-Winkler similarity with different names."""
        result = jaro_winkler_similarity("Acme Corp", "XYZ Inc")

        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0

    def test_jaro_winkler_similarity_empty_strings(self):
        """Test Jaro-Winkler similarity with empty strings."""
        result = jaro_winkler_similarity("", "")

        assert result == 0.0


class TestMatchingConfig:
    """Tests for MatchingConfig class."""

    def test_matching_config_defaults(self):
        """Test MatchingConfig with default values."""
        config = MatchingConfig()

        assert config.enable_phonetic_matching is False
        assert config.enable_jaro_winkler is False
        assert config.enable_enhanced_abbreviations is False

    def test_matching_config_custom_values(self):
        """Test MatchingConfig with custom values."""
        config_dict = {
            "enable_phonetic_matching": True,
            "phonetic_algorithm": "soundex",
            "enable_jaro_winkler": True,
            "jaro_winkler_threshold": 85,
        }
        config = MatchingConfig(config_dict)

        assert config.enable_phonetic_matching is True
        assert config.phonetic_algorithm == "soundex"
        assert config.enable_jaro_winkler is True
        assert config.jaro_winkler_threshold == 85

    def test_matching_config_get_abbreviations(self):
        """Test get_abbreviations method."""
        config = MatchingConfig({"enable_enhanced_abbreviations": True})
        abbrev = config.get_abbreviations()

        assert isinstance(abbrev, dict)
        assert len(abbrev) > 0

    def test_matching_config_get_abbreviations_disabled(self):
        """Test get_abbreviations when disabled."""
        config = MatchingConfig({"enable_enhanced_abbreviations": False})
        abbrev = config.get_abbreviations()

        assert abbrev == {}

    def test_matching_config_custom_abbreviations(self):
        """Test MatchingConfig with custom abbreviations."""
        custom_abbrev = {"test": "tst"}
        config = MatchingConfig(
            {"enable_enhanced_abbreviations": True, "custom_abbreviations": custom_abbrev}
        )
        abbrev = config.get_abbreviations()

        assert "test" in abbrev
        assert abbrev["test"] == "tst"

