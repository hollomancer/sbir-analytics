"""Unit tests for ColumnFinder utility."""

import pandas as pd
import pytest

from src.utils.column_finder import ColumnFinder


class TestColumnFinder:
    """Test ColumnFinder utility methods."""

    def test_find_id_column_award_exact_match(self):
        """Test finding award ID column with exact match."""
        df = pd.DataFrame({"Contract_ID": [1, 2], "name": ["A", "B"]})
        result = ColumnFinder.find_id_column(df, "award")
        assert result == "Contract_ID"

    def test_find_id_column_award_partial_match(self):
        """Test finding award ID column with partial match."""
        df = pd.DataFrame({"award_tracking_id": [1, 2], "name": ["A", "B"]})
        result = ColumnFinder.find_id_column(df, "award")
        assert result == "award_tracking_id"

    def test_find_id_column_patent_exact_match(self):
        """Test finding patent ID column with exact match."""
        df = pd.DataFrame({"patent_id": [1, 2], "title": ["A", "B"]})
        result = ColumnFinder.find_id_column(df, "patent")
        assert result == "patent_id"

    def test_find_id_column_patent_partial_match(self):
        """Test finding patent ID column with partial match."""
        df = pd.DataFrame({"grant_number": [1, 2], "title": ["A", "B"]})
        result = ColumnFinder.find_id_column(df, "patent")
        assert result == "grant_number"

    def test_find_id_column_company_exact_match(self):
        """Test finding company ID column with exact match."""
        df = pd.DataFrame({"company_id": [1, 2], "name": ["A", "B"]})
        result = ColumnFinder.find_id_column(df, "company")
        assert result == "company_id"

    def test_find_id_column_not_found(self):
        """Test when ID column is not found."""
        df = pd.DataFrame({"name": ["A", "B"], "value": [1, 2]})
        result = ColumnFinder.find_id_column(df, "award")
        assert result is None

    def test_find_id_column_unknown_entity_type(self):
        """Test finding ID column for unknown entity type."""
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        result = ColumnFinder.find_id_column(df, "unknown")
        assert result == "id"

    def test_find_column_by_patterns_exact_match(self):
        """Test finding column by patterns with exact match."""
        df = pd.DataFrame({"Award_Title": ["A"], "Abstract": ["B"]})
        result = ColumnFinder.find_column_by_patterns(df, ["title", "award"], exact_match=True)
        assert result == "Award_Title"

    def test_find_column_by_patterns_partial_match(self):
        """Test finding column by patterns with partial match."""
        df = pd.DataFrame({"Award_Title": ["A"], "Abstract_Text": ["B"]})
        result = ColumnFinder.find_column_by_patterns(df, ["title"])
        assert result == "Award_Title"

    def test_find_column_by_patterns_not_found(self):
        """Test when column matching patterns is not found."""
        df = pd.DataFrame({"name": ["A"], "value": [1]})
        result = ColumnFinder.find_column_by_patterns(df, ["title", "abstract"])
        assert result is None

    def test_find_columns_by_patterns(self):
        """Test finding multiple columns by pattern mappings."""
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
        """Test finding multiple columns with partial matches."""
        df = pd.DataFrame({"Title_Text": ["A"], "Abstract_Content": ["B"]})
        pattern_map = {"title": ["title"], "abstract": ["abstract"]}
        result = ColumnFinder.find_columns_by_patterns(df, pattern_map)
        assert result["title"] == "Title_Text"
        assert result["abstract"] == "Abstract_Content"

    def test_find_columns_by_patterns_some_not_found(self):
        """Test finding columns when some are not found."""
        df = pd.DataFrame({"Title": ["A"], "Other": ["B"]})
        pattern_map = {"title": ["title"], "abstract": ["abstract"]}
        result = ColumnFinder.find_columns_by_patterns(df, pattern_map)
        assert result["title"] == "Title"
        assert result["abstract"] is None

