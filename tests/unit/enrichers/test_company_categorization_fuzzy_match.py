"""Unit tests for company categorization fuzzy matching enhancements."""

import pytest

from src.enrichers.company_categorization import _generate_name_variations


class TestNameVariations:
    """Test name variation generation for improved fuzzy matching."""

    def test_basic_abbreviation_expansion(self):
        """Test that common abbreviations are expanded correctly."""
        variations = _generate_name_variations("Acme Tech Corp")

        assert "Acme Tech Corp" in variations  # Original
        assert "Acme Technology Corp" in variations  # Tech → Technology
        assert "Acme Tech Corporation" in variations  # Corp → Corporation

    def test_international_abbreviation(self):
        """Test International abbreviation expansion."""
        variations = _generate_name_variations("Global Intl")

        assert "Global Intl" in variations
        assert "Global International" in variations

    def test_slash_separator(self):
        """Test slash separator handling."""
        variations = _generate_name_variations("Research/Development Associates")

        assert "Research/Development Associates" in variations
        assert "Research and Development Associates" in variations
        assert "Research Development Associates" in variations

    def test_atl_international_case(self):
        """Test the specific ATL International case from the bug report."""
        company_name = "Advanced Technologies/Laboratories Intl"
        variations = _generate_name_variations(company_name)

        # Should generate key variations
        assert "Advanced Technologies/Laboratories Intl" in variations
        assert "Advanced Technologies/Laboratories International" in variations
        assert "Advanced Technologies and Laboratories Intl" in variations
        assert "Advanced Technologies and Laboratories International" in variations

        # Should not create malformed names from partial matches
        for variation in variations:
            # Check that we didn't create names like "Technologynologies" or "Advancedanced"
            assert "Technologynologies" not in variation
            assert "Advancedanced" not in variation
            assert "Laboratoryoratories" not in variation

    def test_combined_abbreviations_and_separator(self):
        """Test combining abbreviation expansion with separator replacement."""
        variations = _generate_name_variations("Aerospace/Defense Tech Corp")

        # Should have combinations of both transformations
        assert "Aerospace and Defense Tech Corp" in variations
        assert "Aerospace and Defense Technology Corp" in variations

    def test_no_duplicates(self):
        """Test that duplicate variations are removed."""
        variations = _generate_name_variations("Simple Corp")

        # Should not have duplicates
        assert len(variations) == len(set(variations))

    def test_preserves_original_first(self):
        """Test that original name is always first in the list."""
        original = "Test Company Intl"
        variations = _generate_name_variations(original)

        assert variations[0] == original

    def test_word_boundary_matching(self):
        """Test that abbreviations only match complete words."""
        # "Technologies" contains "Tech" but should not be replaced
        variations = _generate_name_variations("Technologies Inc")

        # Should have Technologies Inc (original) and Technologies Incorporated
        # Should NOT have "Technologynologies Inc"
        assert "Technologies Inc" in variations
        assert "Technologies Incorporated" in variations

        for variation in variations:
            assert "Technologynologies" not in variation

    def test_empty_string(self):
        """Test handling of empty string."""
        variations = _generate_name_variations("")

        assert variations == [""]

    def test_no_variations_needed(self):
        """Test company name with no common abbreviations."""
        variations = _generate_name_variations("Boeing Aircraft")

        # Should only have original
        assert len(variations) == 1
        assert variations[0] == "Boeing Aircraft"

    def test_multiple_abbreviations(self):
        """Test company name with multiple abbreviations."""
        variations = _generate_name_variations("Advanced Eng Tech Sys Corp")

        # Should expand each abbreviation
        assert "Advanced Engineering Tech Sys Corp" in variations
        assert "Advanced Eng Technology Sys Corp" in variations
        assert "Advanced Eng Tech Systems Corp" in variations
        assert "Advanced Eng Tech Sys Corporation" in variations

    def test_case_sensitivity(self):
        """Test that matching is case-sensitive for abbreviations."""
        # "Intl" (capitalized) should match
        variations = _generate_name_variations("Company Intl")

        assert "Company Intl" in variations
        assert "Company International" in variations

        # Lowercase "intl" won't match (case-sensitive)
        variations_lower = _generate_name_variations("Company intl")
        # Should only have original since lowercase won't match our patterns
        assert variations_lower == ["Company intl"]
