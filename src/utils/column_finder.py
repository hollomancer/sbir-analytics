"""Utility for finding columns in DataFrames with consistent fallback patterns.

This module provides reusable utilities for discovering columns in pandas DataFrames
based on common naming patterns, reducing duplication across assets.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


class ColumnFinder:
    """Utility for finding columns in DataFrames with fallback patterns."""

    # Column patterns for different entity types
    ID_PATTERNS: dict[str, list[str]] = {
        "award": ["contract", "tracking", "award_id", "id"],
        "patent": ["patent", "grant_number", "grant_doc_num", "id"],
        "company": ["company_id", "uei", "duns", "organization_id"],
    }

    @staticmethod
    def find_id_column(df: pd.DataFrame, entity_type: str) -> str | None:
        """Find ID column for entity type (award, patent, company, etc.).

        Args:
            df: DataFrame to search
            entity_type: Type of entity ("award", "patent", "company")

        Returns:
            Column name if found, None otherwise

        Example:
            >>> df = pd.DataFrame({"Contract_ID": [1, 2], "name": ["A", "B"]})
            >>> ColumnFinder.find_id_column(df, "award")
            'Contract_ID'
        """
        if entity_type not in ColumnFinder.ID_PATTERNS:
            # Try generic patterns if entity type not recognized
            patterns = ["id", "ID", "_id"]
        else:
            patterns = ColumnFinder.ID_PATTERNS[entity_type]

        # Search for exact matches first (case-sensitive)
        for pattern in patterns:
            for col in df.columns:
                if col == pattern or col.lower() == pattern.lower():
                    return col

        # Search for partial matches (case-insensitive)
        for pattern in patterns:
            for col in df.columns:
                col_lower = col.lower()
                if pattern.lower() in col_lower or col_lower in pattern.lower():
                    return col

        return None

    @staticmethod
    def find_column_by_patterns(
        df: pd.DataFrame, patterns: list[str], exact_match: bool = False
    ) -> str | None:
        """Find column matching any of the provided patterns.

        Args:
            df: DataFrame to search
            patterns: List of patterns to search for (case-insensitive)
            exact_match: If True, require exact match; if False, allow partial match

        Returns:
            Column name if found, None otherwise

        Example:
            >>> df = pd.DataFrame({"Award_Title": ["A"], "Abstract_Text": ["B"]})
            >>> ColumnFinder.find_column_by_patterns(df, ["title", "award"])
            'Award_Title'
        """
        if exact_match:
            # Try exact matches first (case-insensitive)
            for pattern in patterns:
                pattern_lower = pattern.lower()
                for col in df.columns:
                    if col.lower() == pattern_lower:
                        return col

        # Try partial matches (case-insensitive)
        for pattern in patterns:
            pattern_lower = pattern.lower()
            for col in df.columns:
                col_lower = col.lower()
                if pattern_lower in col_lower:
                    return col

        return None

    @staticmethod
    def find_columns_by_patterns(
        df: pd.DataFrame, pattern_map: dict[str, list[str]]
    ) -> dict[str, str | None]:
        """Find multiple columns based on pattern mappings.

        Args:
            df: DataFrame to search
            pattern_map: Dictionary mapping result keys to pattern lists
                        e.g., {"title": ["title", "award"], "abstract": ["abstract"]}

        Returns:
            Dictionary mapping keys to found column names (or None if not found)

        Example:
            >>> df = pd.DataFrame({"Award_Title": ["A"], "Abstract": ["B"]})
            >>> ColumnFinder.find_columns_by_patterns(
            ...     df, {"title": ["title"], "abstract": ["abstract"]}
            ... )
            {'title': 'Award_Title', 'abstract': 'Abstract'}
        """
        result: dict[str, str | None] = {}
        for key, patterns in pattern_map.items():
            result[key] = ColumnFinder.find_column_by_patterns(df, patterns)
        return result

