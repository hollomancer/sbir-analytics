"""Unit tests for asset column helper utilities."""

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from src.utils.asset_column_helper import AssetColumnHelper


class TestAssetColumnHelper:
    """Tests for AssetColumnHelper utility class."""

    def test_find_award_id_column_exact_match(self):
        """Test finding award ID column with exact match."""
        df = pd.DataFrame({"award_id": [1, 2], "name": ["A", "B"]})

        result = AssetColumnHelper.find_award_id_column(df)

        assert result == "award_id"

    def test_find_award_id_column_pattern_match(self):
        """Test finding award ID column with pattern match."""
        df = pd.DataFrame({"Contract_ID": [1, 2], "name": ["A", "B"]})

        result = AssetColumnHelper.find_award_id_column(df)

        assert result == "Contract_ID"

    def test_find_award_id_column_fallback_to_generic(self):
        """Test finding award ID column falls back to generic ID."""
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})

        result = AssetColumnHelper.find_award_id_column(df)

        assert result == "id"

    def test_find_award_id_column_returns_none_when_not_found(self):
        """Test find_award_id_column returns None when not found."""
        df = pd.DataFrame({"name": ["A", "B"], "value": [1, 2]})

        result = AssetColumnHelper.find_award_id_column(df)

        assert result is None

    def test_find_patent_id_column(self):
        """Test finding patent ID column."""
        df = pd.DataFrame({"grant_doc_num": ["US123", "US456"], "title": ["A", "B"]})

        result = AssetColumnHelper.find_patent_id_column(df)

        assert result == "grant_doc_num"

    def test_find_company_id_column(self):
        """Test finding company ID column."""
        df = pd.DataFrame({"company_id": ["C1", "C2"], "name": ["A", "B"]})

        result = AssetColumnHelper.find_company_id_column(df)

        assert result == "company_id"

    def test_find_company_id_column_uei_fallback(self):
        """Test finding company ID column with UEI fallback."""
        df = pd.DataFrame({"uei": ["U1", "U2"], "name": ["A", "B"]})

        result = AssetColumnHelper.find_company_id_column(df)

        assert result == "uei"

    def test_find_text_columns_award(self):
        """Test finding text columns for awards."""
        df = pd.DataFrame(
            {
                "Award_Title": ["Title A"],
                "Abstract": ["Abstract A"],
                "Solicitation": ["Solicitation A"],
            }
        )

        result = AssetColumnHelper.find_text_columns(df, "award")

        assert result.get("title") is not None
        assert result.get("abstract") is not None
        assert result.get("solicitation") is not None

    def test_find_text_columns_patent(self):
        """Test finding text columns for patents."""
        df = pd.DataFrame({"title": ["Title A"], "abstract": ["Abstract A"]})

        result = AssetColumnHelper.find_text_columns(df, "patent")

        assert result.get("title") is not None
        assert result.get("abstract") is not None

