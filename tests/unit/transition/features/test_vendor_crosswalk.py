"""
Tests for the current package module: transition/features/vendor_crosswalk.py
"""

import pytest

from sbir_ml.transition.features.vendor_crosswalk import _fuzzy_score


pytestmark = pytest.mark.fast


class TestUtilityFunctions:
    """Tests for utility functions."""

    @pytest.mark.parametrize(
        "str1,str2,min_score,max_score",
        [
            ("Acme Corporation", "Acme Corporation", 1.0, 1.0),
            ("Acme Corporation", "Acme Corp", 0.7, 1.0),
            ("Acme Corporation", "Different Company", 0.0, 0.5),
            ("", "Acme", 0.0, 0.0),
            ("Acme", "", 0.0, 0.0),
        ],
        ids=["exact", "similar", "different", "empty_first", "empty_second"],
    )
    def test_fuzzy_score(self, str1, str2, min_score, max_score):
        """Test fuzzy score returns expected ranges for various inputs."""
        score = _fuzzy_score(str1, str2)
        assert min_score <= score <= max_score
