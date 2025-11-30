"""Unit tests for column finder utilities.

Tests the ColumnFinder class which provides flexible column name detection
for DataFrames with varying column naming conventions.
"""

import pandas as pd
import pytest

from src.utils.column_finder import ColumnFinder


pytestmark = pytest.mark.fast


class TestColumnFinderIdColumn:
    """Tests for find_id_column method."""

    @pytest.mark.parametrize(
        "columns,entity_type,expected",
        [
            ({"Contract_ID": [1, 2], "name": ["A", "B"]}, "award", "Contract_ID"),
            ({"grant_doc_num": ["US123", "US456"], "title": ["A", "B"]}, "patent", "grant_doc_num"),
            ({"company_id": ["C1", "C2"], "name": ["A", "B"]}, "company", "company_id"),
            ({"CONTRACT_ID": [1, 2], "name": ["A", "B"]}, "award", "CONTRACT_ID"),
            ({"id": [1, 2], "name": ["A", "B"]}, "unknown_entity", "id"),
        ],
        ids=["award", "patent", "company", "case_insensitive", "unknown_entity"],
    )
    def test_find_id_column_scenarios(self, columns, entity_type, expected):
        """Test finding ID columns for various entity types and naming conventions."""
        df = pd.DataFrame(columns)
        result = ColumnFinder.find_id_column(df, entity_type)
        assert result == expected

    def test_find_id_column_returns_none_when_not_found(self):
        """Test find_id_column returns None when no matching column exists."""
        df = pd.DataFrame({"name": ["A", "B"], "value": [1, 2]})
        result = ColumnFinder.find_id_column(df, "award")
        assert result is None


class TestColumnFinderByPatterns:
    """Tests for find_column_by_patterns method."""

    @pytest.mark.parametrize(
        "columns,patterns,expected",
        [
            ({"contract_id": [1, 2], "name": ["A", "B"]}, ["contract", "tracking"], "contract_id"),
            (
                {"tracking_id": [1, 2], "contract_id": [3, 4], "name": ["A", "B"]},
                ["contract", "tracking"],
                "contract_id",
            ),
            ({"name": ["A", "B"], "value": [1, 2]}, ["contract", "tracking"], None),
        ],
        ids=["single_match", "priority_order", "no_match"],
    )
    def test_find_column_by_patterns(self, columns, patterns, expected):
        """Test finding columns by pattern matching with priority."""
        df = pd.DataFrame(columns)
        result = ColumnFinder.find_column_by_patterns(df, patterns)
        assert result == expected


class TestColumnFinderMultiplePatterns:
    """Tests for find_columns_by_patterns method."""

    def test_find_columns_by_patterns_all_found(self):
        """Test finding multiple columns when all patterns match."""
        df = pd.DataFrame({"Award_Title": ["A"], "Abstract": ["B"], "Solicitation": ["C"]})
        pattern_map = {
            "title": ["title"],
            "abstract": ["abstract"],
            "solicitation": ["solicitation"],
        }
        result = ColumnFinder.find_columns_by_patterns(df, pattern_map)
        assert result["title"] == "Award_Title"
        assert result["abstract"] == "Abstract"
        assert result["solicitation"] == "Solicitation"

    def test_find_columns_by_patterns_partial_match(self):
        """Test finding columns with partial pattern matches."""
        df = pd.DataFrame({"Title_Text": ["A"], "Abstract_Content": ["B"]})
        pattern_map = {"title": ["title"], "abstract": ["abstract"]}
        result = ColumnFinder.find_columns_by_patterns(df, pattern_map)
        assert result["title"] == "Title_Text"
        assert result["abstract"] == "Abstract_Content"

    def test_find_columns_by_patterns_some_not_found(self):
        """Test finding columns when some patterns don't match."""
        df = pd.DataFrame({"Title": ["A"], "Other": ["B"]})
        pattern_map = {"title": ["title"], "abstract": ["abstract"]}
        result = ColumnFinder.find_columns_by_patterns(df, pattern_map)
        assert result["title"] == "Title"
        assert result["abstract"] is None
