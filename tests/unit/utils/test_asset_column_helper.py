"""Unit tests for asset column helper utilities.

Tests the AssetColumnHelper class which provides entity-specific column
detection for Dagster assets processing awards, patents, and companies.
"""

import pandas as pd
import pytest

from src.utils.asset_column_helper import AssetColumnHelper


pytestmark = pytest.mark.fast


class TestFindAwardIdColumn:
    """Tests for find_award_id_column method."""

    @pytest.mark.parametrize(
        "columns,expected",
        [
            ({"award_id": [1, 2], "name": ["A", "B"]}, "award_id"),
            ({"Contract_ID": [1, 2], "name": ["A", "B"]}, "Contract_ID"),
            ({"id": [1, 2], "name": ["A", "B"]}, "id"),
            ({"name": ["A", "B"], "value": [1, 2]}, None),
        ],
        ids=["exact_match", "pattern_match", "generic_fallback", "not_found"],
    )
    def test_find_award_id_column(self, columns, expected):
        """Test finding award ID column with various naming conventions."""
        df = pd.DataFrame(columns)
        result = AssetColumnHelper.find_award_id_column(df)
        assert result == expected


class TestFindPatentIdColumn:
    """Tests for find_patent_id_column method."""

    @pytest.mark.parametrize(
        "columns,expected",
        [
            ({"grant_doc_num": ["US123", "US456"], "title": ["A", "B"]}, "grant_doc_num"),
            ({"patent_number": ["123", "456"], "title": ["A", "B"]}, "patent_number"),
            ({"name": ["A", "B"], "value": [1, 2]}, None),
        ],
        ids=["grant_doc_num", "patent_number", "not_found"],
    )
    def test_find_patent_id_column(self, columns, expected):
        """Test finding patent ID column with various naming conventions."""
        df = pd.DataFrame(columns)
        result = AssetColumnHelper.find_patent_id_column(df)
        assert result == expected


class TestFindCompanyIdColumn:
    """Tests for find_company_id_column method."""

    @pytest.mark.parametrize(
        "columns,expected",
        [
            ({"company_id": ["C1", "C2"], "name": ["A", "B"]}, "company_id"),
            ({"uei": ["U1", "U2"], "name": ["A", "B"]}, "uei"),
            ({"name": ["A", "B"], "value": [1, 2]}, None),
        ],
        ids=["company_id", "uei_fallback", "not_found"],
    )
    def test_find_company_id_column(self, columns, expected):
        """Test finding company ID column with UEI fallback."""
        df = pd.DataFrame(columns)
        result = AssetColumnHelper.find_company_id_column(df)
        assert result == expected


class TestFindTextColumns:
    """Tests for find_text_columns method."""

    @pytest.mark.parametrize(
        "columns,entity_type,expected_title,expected_abstract",
        [
            (
                {"Award_Title": ["A"], "Abstract": ["B"], "Solicitation": ["C"]},
                "award",
                "Award_Title",
                "Abstract",
            ),
            ({"title": ["A"], "abstract": ["B"]}, "patent", "title", "abstract"),
            ({"Title": ["A"], "Abstract": ["B"]}, "generic", "Title", "Abstract"),
            (
                {"Title_Text": ["A"], "Abstract_Content": ["B"]},
                "award",
                "Title_Text",
                "Abstract_Content",
            ),
        ],
        ids=["award_standard", "patent_standard", "generic", "partial_match"],
    )
    def test_find_text_columns_scenarios(
        self, columns, entity_type, expected_title, expected_abstract
    ):
        """Test finding text columns for various entity types."""
        df = pd.DataFrame(columns)
        result = AssetColumnHelper.find_text_columns(df, entity_type)
        assert result["title"] == expected_title
        assert result["abstract"] == expected_abstract

    def test_find_text_columns_award_title_excludes_solicitation(self):
        """Test that award title detection excludes solicitation columns."""
        df = pd.DataFrame({"Solicitation_Title": ["A"], "Award_Title": ["B"], "Abstract": ["C"]})
        result = AssetColumnHelper.find_text_columns(df, entity_type="award")
        assert result["title"] == "Award_Title"
        assert result["solicitation"] == "Solicitation_Title"

    def test_find_text_columns_some_not_found(self):
        """Test finding text columns when some are missing."""
        df = pd.DataFrame({"Title": ["A"], "Other": ["B"]})
        result = AssetColumnHelper.find_text_columns(df, entity_type="award")
        assert result["title"] == "Title"
        assert result["abstract"] is None
        assert result["solicitation"] is None
