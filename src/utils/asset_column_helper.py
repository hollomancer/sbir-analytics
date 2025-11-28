"""Helper for discovering columns in asset DataFrames.

This module provides specialized helpers for common asset column patterns,
building on the base ColumnFinder utility.
"""

from __future__ import annotations

import pandas as pd

from .column_finder import ColumnFinder


class AssetColumnHelper:
    """Helper for discovering columns in asset DataFrames."""

    @staticmethod
    def find_award_id_column(df: pd.DataFrame) -> str | None:
        """Find award ID column with fallback logic.

        Searches for common award ID column names with priority:
        1. Exact matches: "award_id", "Contract_ID", "tracking_id"
        2. Partial matches: columns containing "contract", "tracking", "award_id"
        3. Generic "id" or "ID" columns

        Args:
            df: DataFrame to search

        Returns:
            Column name if found, None otherwise

        Example:
            >>> df = pd.DataFrame({"Contract_ID": [1, 2], "name": ["A", "B"]})
            >>> AssetColumnHelper.find_award_id_column(df)
            'Contract_ID'
        """
        # Try specific award patterns first
        award_patterns = ["contract", "tracking", "award_id"]
        col = ColumnFinder.find_column_by_patterns(df, award_patterns)
        if col:
            return col

        # Fallback to generic ID column
        return ColumnFinder.find_id_column(df, "award")

    @staticmethod
    def find_patent_id_column(df: pd.DataFrame) -> str | None:
        """Find patent ID column with fallback logic.

        Searches for common patent ID column names with priority:
        1. Exact matches: "patent_id", "grant_number", "grant_doc_num"
        2. Partial matches: columns containing "patent", "grant"
        3. Generic "id" or "ID" columns

        Args:
            df: DataFrame to search

        Returns:
            Column name if found, None otherwise

        Example:
            >>> df = pd.DataFrame({"patent_id": [1, 2], "title": ["A", "B"]})
            >>> AssetColumnHelper.find_patent_id_column(df)
            'patent_id'
        """
        # Try specific patent patterns first
        patent_patterns = ["patent", "grant_number", "grant_doc_num"]
        col = ColumnFinder.find_column_by_patterns(df, patent_patterns)
        if col:
            return col

        # Fallback to generic ID column
        return ColumnFinder.find_id_column(df, "patent")

    @staticmethod
    def find_company_id_column(df: pd.DataFrame) -> str | None:
        """Find company ID column with fallback logic.

        Searches for common company ID column names with priority:
        1. Exact matches: "company_id", "uei", "duns"
        2. Partial matches: columns containing "company", "uei", "duns"
        3. Generic "id" or "ID" columns

        Args:
            df: DataFrame to search

        Returns:
            Column name if found, None otherwise

        Example:
            >>> df = pd.DataFrame({"uei": ["U1", "U2"], "name": ["A", "B"]})
            >>> AssetColumnHelper.find_company_id_column(df)
            'uei'
        """
        # Try specific company patterns first
        company_patterns = ["company_id", "uei", "duns"]
        col = ColumnFinder.find_column_by_patterns(df, company_patterns)
        if col:
            return col

        # Fallback to generic ID column
        return ColumnFinder.find_id_column(df, "company")

    @staticmethod
    def find_text_columns(df: pd.DataFrame, entity_type: str = "award") -> dict[str, str | None]:
        """Find common text columns (title, abstract, solicitation).

        Args:
            df: DataFrame to search
            entity_type: Type of entity ("award" or "patent")

        Returns:
            Dictionary with keys "title", "abstract", "solicitation" (if applicable)
            mapping to column names (or None if not found)

        Example:
            >>> df = pd.DataFrame({
            ...     "Award_Title": ["A"], "Abstract": ["B"], "Solicitation": ["C"]
            ... })
            >>> AssetColumnHelper.find_text_columns(df, "award")
            {'title': 'Award_Title', 'abstract': 'Abstract', 'solicitation': 'Solicitation'}
        """
        if entity_type == "award":
            pattern_map = {
                "title": ["award", "title"],
                "abstract": ["abstract"],
                "solicitation": ["solicitation", "topic"],
            }
            # For award titles, exclude "solicitation" from title matches
            result = ColumnFinder.find_columns_by_patterns(df, pattern_map)

            # Special handling: title should not match "solicitation"
            title_col = result.get("title")
            if title_col:
                if "solicitation" in title_col.lower():
                    # Try to find a better title column
                    title_patterns = ["award", "title"]
                    for pattern in title_patterns:
                        for col in df.columns:
                            col_lower = col.lower()
                            if (
                                pattern in col_lower
                                and "solicitation" not in col_lower
                                and col != result.get("solicitation")
                            ):
                                result["title"] = col
                                break
                        title_col_check = result.get("title")
                        if title_col_check and "solicitation" not in title_col_check.lower():
                            break

            return result

        elif entity_type == "patent":
            pattern_map = {
                "title": ["title"],
                "abstract": ["abstract"],
            }
            return ColumnFinder.find_columns_by_patterns(df, pattern_map)

        else:
            # Generic text columns
            pattern_map = {
                "title": ["title"],
                "abstract": ["abstract"],
            }
            return ColumnFinder.find_columns_by_patterns(df, pattern_map)
