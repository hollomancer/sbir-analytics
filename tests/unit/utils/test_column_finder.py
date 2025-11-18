"""Unit tests for column finder utilities."""

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from src.utils.column_finder import ColumnFinder


class TestColumnFinder:
    """Tests for ColumnFinder utility class."""

    def test_find_id_column_award(self):
        """Test finding award ID column."""
        df = pd.DataFrame({"Contract_ID": [1, 2], "name": ["A", "B"]})

        result = ColumnFinder.find_id_column(df, "award")

        assert result == "Contract_ID"

    def test_find_id_column_patent(self):
        """Test finding patent ID column."""
        df = pd.DataFrame({"grant_doc_num": ["US123", "US456"], "title": ["A", "B"]})

        result = ColumnFinder.find_id_column(df, "patent")

        assert result == "grant_doc_num"

    def test_find_id_column_company(self):
        """Test finding company ID column."""
        df = pd.DataFrame({"company_id": ["C1", "C2"], "name": ["A", "B"]})

        result = ColumnFinder.find_id_column(df, "company")

        assert result == "company_id"

    def test_find_id_column_case_insensitive(self):
        """Test finding ID column with case-insensitive matching."""
        df = pd.DataFrame({"CONTRACT_ID": [1, 2], "name": ["A", "B"]})

        result = ColumnFinder.find_id_column(df, "award")

        assert result == "CONTRACT_ID"

    def test_find_id_column_returns_none_when_not_found(self):
        """Test find_id_column returns None when column not found."""
        df = pd.DataFrame({"name": ["A", "B"], "value": [1, 2]})

        result = ColumnFinder.find_id_column(df, "award")

        assert result is None

    def test_find_id_column_unknown_entity_type(self):
        """Test find_id_column with unknown entity type uses generic patterns."""
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})

        result = ColumnFinder.find_id_column(df, "unknown_entity")

        assert result == "id"

    def test_find_column_by_patterns(self):
        """Test finding column by patterns."""
        df = pd.DataFrame({"contract_id": [1, 2], "name": ["A", "B"]})

        result = ColumnFinder.find_column_by_patterns(df, ["contract", "tracking"])

        assert result == "contract_id"

    def test_find_column_by_patterns_priority(self):
        """Test pattern matching prioritizes earlier patterns."""
        df = pd.DataFrame(
            {"tracking_id": [1, 2], "contract_id": [3, 4], "name": ["A", "B"]}
        )

        result = ColumnFinder.find_column_by_patterns(df, ["contract", "tracking"])

        assert result == "contract_id"  # "contract" comes first in patterns

    def test_find_column_by_patterns_returns_none_when_not_found(self):
        """Test find_column_by_patterns returns None when no match."""
        df = pd.DataFrame({"name": ["A", "B"], "value": [1, 2]})

        result = ColumnFinder.find_column_by_patterns(df, ["contract", "tracking"])

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

