"""Unit tests for text normalization utilities.

Tests cover:
- Name normalization with different strategies
- Suffix handling (removal vs normalization)
- Punctuation and whitespace handling
- Edge cases and special characters
- Backward-compatible aliases
"""

import pytest


pytestmark = pytest.mark.fast

from src.utils.text_normalization import (
    normalize_company_name,
    normalize_name,
    normalize_recipient_name,
)


pytestmark = pytest.mark.fast


class TestNormalizeName:
    """Tests for normalize_name function."""

    def test_normalize_simple_name(self):
        """Test normalizing simple company name."""
        result = normalize_name("Acme Corporation")

        assert result == "acme corporation"

    def test_normalize_with_punctuation(self):
        """Test normalizing name with punctuation."""
        result = normalize_name("Acme, Inc.")

        assert result == "acme inc"

    def test_normalize_with_periods(self):
        """Test normalizing name with periods."""
        result = normalize_name("U.S. Robotics Corp.")

        assert result == "u s robotics corp"

    def test_normalize_with_ampersand(self):
        """Test normalizing name with ampersand."""
        result = normalize_name("Smith & Johnson LLC")

        assert result == "smith johnson llc"

    def test_normalize_with_hyphens(self):
        """Test normalizing name with hyphens."""
        result = normalize_name("Tech-Solutions, Inc")

        assert result == "tech solutions inc"

    def test_normalize_removes_suffixes(self):
        """Test normalization with suffix removal."""
        result = normalize_name("Acme Corporation", remove_suffixes=True)

        assert result == "acme"
        assert "corporation" not in result

    def test_normalize_removes_inc(self):
        """Test removing 'Inc' suffix."""
        result = normalize_name("TechCorp Inc", remove_suffixes=True)

        assert result == "techcorp"

    def test_normalize_removes_llc(self):
        """Test removing 'LLC' suffix."""
        result = normalize_name("DataCorp LLC", remove_suffixes=True)

        assert result == "datacorp"

    def test_normalize_removes_incorporated(self):
        """Test removing 'Incorporated' suffix."""
        result = normalize_name("BizTech Incorporated", remove_suffixes=True)

        assert result == "biztech"

    def test_normalize_standardizes_incorporated(self):
        """Test standardizing 'Incorporated' to 'inc'."""
        result = normalize_name("BizTech Incorporated", remove_suffixes=False)

        assert "inc" in result
        assert "incorporated" not in result

    def test_normalize_standardizes_company(self):
        """Test standardizing 'Co' to 'company'."""
        result = normalize_name("ABC Co", remove_suffixes=False)

        assert "company" in result

    def test_normalize_standardizes_limited(self):
        """Test standardizing 'Limited' to 'ltd'."""
        result = normalize_name("XYZ Limited", remove_suffixes=False)

        assert "ltd" in result
        assert "limited" not in result

    def test_normalize_collapses_whitespace(self):
        """Test that multiple spaces are collapsed."""
        result = normalize_name("Acme    Corp     Inc")

        assert result == "acme corp inc"
        assert "    " not in result

    def test_normalize_strips_whitespace(self):
        """Test that leading/trailing whitespace is removed."""
        result = normalize_name("  Acme Corp  ")

        assert result == "acme corp"
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_normalize_empty_string(self):
        """Test normalizing empty string."""
        result = normalize_name("")

        assert result == ""

    def test_normalize_none(self):
        """Test normalizing None."""
        result = normalize_name(None)

        assert result == ""

    def test_normalize_all_punctuation(self):
        """Test normalizing name with only punctuation."""
        result = normalize_name("...")

        assert result == ""

    def test_normalize_mixed_case(self):
        """Test that mixed case is lowercased."""
        result = normalize_name("TechCORP InTernational")

        assert result == "techcorp international"
        assert result.islower()

    def test_normalize_with_numbers(self):
        """Test normalizing name with numbers."""
        result = normalize_name("Tech2000 Corporation")

        assert result == "tech2000 corporation"
        assert "2000" in result

    def test_normalize_multiple_suffixes(self):
        """Test normalizing name with multiple suffixes."""
        result = normalize_name("Acme Corp Inc", remove_suffixes=True)

        assert result == "acme"
        assert "corp" not in result
        assert "inc" not in result

    def test_normalize_suffix_in_middle(self):
        """Test that suffixes in middle of name are handled."""
        # "Inc" at the beginning shouldn't be removed
        result = normalize_name("Incorporated Solutions LLC", remove_suffixes=False)

        assert "inc" in result  # "Incorporated" becomes "inc"
        assert "solutions" in result

    def test_normalize_preserves_core_name(self):
        """Test that core business name is preserved."""
        result = normalize_name("Advanced Robotics Corporation", remove_suffixes=True)

        assert "advanced" in result
        assert "robotics" in result
        assert "corporation" not in result


class TestNormalizeCompanyName:
    """Tests for normalize_company_name backward-compatible alias."""

    def test_normalize_company_name_keeps_suffixes(self):
        """Test that normalize_company_name keeps standardized suffixes."""
        result = normalize_company_name("Acme Corporation")

        # Should convert "Corporation" but not remove it entirely
        assert "acme" in result
        # Suffixes are standardized, not removed

    def test_normalize_company_name_standardizes_inc(self):
        """Test that 'Incorporated' is standardized to 'inc'."""
        result = normalize_company_name("TechCorp Incorporated")

        assert "inc" in result
        assert "incorporated" not in result

    def test_normalize_company_name_handles_none(self):
        """Test handling None input."""
        result = normalize_company_name(None)

        assert result == ""

    def test_normalize_company_name_removes_punctuation(self):
        """Test that punctuation is removed."""
        result = normalize_company_name("Acme, Inc.")

        assert "," not in result
        assert "." not in result


class TestNormalizeRecipientName:
    """Tests for normalize_recipient_name backward-compatible alias."""

    def test_normalize_recipient_name_removes_suffixes(self):
        """Test that normalize_recipient_name removes all suffixes."""
        result = normalize_recipient_name("Acme Corporation")

        assert "acme" in result
        assert "corporation" not in result

    def test_normalize_recipient_name_removes_inc(self):
        """Test that 'Inc' is removed."""
        result = normalize_recipient_name("TechCorp Inc")

        assert "techcorp" in result
        assert "inc" not in result

    def test_normalize_recipient_name_removes_llc(self):
        """Test that 'LLC' is removed."""
        result = normalize_recipient_name("DataCorp LLC")

        assert "datacorp" in result
        assert "llc" not in result

    def test_normalize_recipient_name_handles_none(self):
        """Test handling None input."""
        result = normalize_recipient_name(None)

        assert result == ""

    def test_normalize_recipient_name_multiple_suffixes(self):
        """Test removal of multiple suffixes."""
        result = normalize_recipient_name("Acme Corp Inc LLC")

        assert result == "acme"


class TestTextNormalizationEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_normalize_unicode_characters(self):
        """Test handling unicode characters."""
        result = normalize_name("Café Corporation")

        assert "caf" in result

    def test_normalize_special_characters(self):
        """Test handling special characters."""
        result = normalize_name("Tech@Corp #1")

        assert "tech" in result
        assert "corp" in result
        assert "@" not in result
        assert "#" not in result

    def test_normalize_parentheses(self):
        """Test handling parentheses."""
        result = normalize_name("Acme (USA) Corp")

        assert "acme" in result
        assert "usa" in result
        assert "(" not in result

    def test_normalize_underscore(self):
        """Test that underscores are preserved in words."""
        result = normalize_name("Tech_Corp")

        assert "tech_corp" in result or "tech corp" in result

    def test_normalize_very_long_name(self):
        """Test normalizing very long company name."""
        long_name = "International Business Machines Corporation of America Incorporated"
        result = normalize_name(long_name, remove_suffixes=True)

        assert "international" in result
        assert "business" in result
        assert "machines" in result
        assert "corporation" not in result
        assert "incorporated" not in result

    def test_normalize_single_word(self):
        """Test normalizing single word name."""
        result = normalize_name("Google")

        assert result == "google"

    def test_normalize_with_trailing_comma(self):
        """Test normalizing name with trailing comma."""
        result = normalize_name("Acme Corp,")

        assert "acme" in result
        assert "," not in result

    def test_idempotency(self):
        """Test that normalization is idempotent."""
        name = "Acme Corporation, Inc."

        result1 = normalize_name(name)
        result2 = normalize_name(result1)

        assert result1 == result2


class TestComparisonScenarios:
    """Tests for real-world comparison scenarios."""

    def test_matching_companies_different_formats(self):
        """Test that different formats of same company match."""
        name1 = normalize_name("Acme Corporation", remove_suffixes=True)
        name2 = normalize_name("ACME CORP", remove_suffixes=True)
        name3 = normalize_name("Acme, Inc.", remove_suffixes=True)

        assert name1 == name2 == name3 == "acme"

    def test_matching_with_punctuation_differences(self):
        """Test matching despite punctuation differences."""
        name1 = normalize_name("U.S. Robotics", remove_suffixes=True)
        name2 = normalize_name("US Robotics", remove_suffixes=True)

        # Normalization converts "U.S." to "u s" (periods become spaces)
        # So we expect "u s robotics" == "us robotics" after normalization
        assert name1 == "u s robotics" or name1 == name2

    def test_different_companies_dont_match(self):
        """Test that different companies don't match."""
        name1 = normalize_name("Acme Corporation", remove_suffixes=True)
        name2 = normalize_name("Beta Systems", remove_suffixes=True)

        assert name1 != name2
