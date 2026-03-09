"""
Extract solicitation topics from SBIR.gov.

Pulls topic text, agency requirements, and solicitation cycles to build
the topic universe that feeds overlap and gap analysis.

Data source: SBIR.gov solicitations
Access method: Scrape / bulk download
Refresh cadence: Per solicitation cycle
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


class ExtractTopicsTool(BaseTool):
    """Extract solicitation topics from SBIR.gov for portfolio analysis.

    Topics are the unit of analysis for overlap detection. Each topic has:
    - Agency and solicitation cycle
    - Topic title and description text
    - NAICS codes and technology areas
    - Fiscal year and phase
    """

    name = "extract_topics"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        awards_df: pd.DataFrame | None = None,
        solicitation_data_path: str | None = None,
        fiscal_years: list[int] | None = None,
        agencies: list[str] | None = None,
    ) -> ToolResult:
        """Extract topics from SBIR.gov award abstracts and solicitation data.

        Topics can be derived from two sources:
        1. Award abstracts (always available) — grouped by solicitation topic
        2. Solicitation data files (if available) — richer topic descriptions

        Args:
            metadata: Pre-initialized metadata to populate
            awards_df: DataFrame of SBIR awards with abstracts and topic info
            solicitation_data_path: Path to solicitation data file (optional)
            fiscal_years: Filter to these fiscal years
            agencies: Filter to these agencies

        Returns:
            ToolResult with DataFrame of extracted topics
        """
        topics: list[dict[str, Any]] = []

        # Extract topics from award data (primary path)
        if awards_df is not None and not awards_df.empty:
            df = awards_df.copy()

            # Apply filters
            if fiscal_years:
                fy_col = next(
                    (c for c in ["fiscal_year", "award_year", "fy"] if c in df.columns),
                    None,
                )
                if fy_col:
                    df = df[df[fy_col].isin(fiscal_years)]

            if agencies:
                agency_col = next(
                    (c for c in ["agency", "awarding_agency", "agency_name"] if c in df.columns),
                    None,
                )
                if agency_col:
                    agencies_upper = [a.upper() for a in agencies]
                    df = df[df[agency_col].str.upper().isin(agencies_upper)]

            # Group awards by solicitation topic to extract topic-level data
            topic_col = next(
                (c for c in ["solicitation_topic", "topic_code", "topic_number", "solicitation_id"]
                 if c in df.columns),
                None,
            )

            if topic_col:
                for topic_key, group in df.groupby(topic_col):
                    abstract_col = next(
                        (c for c in ["abstract", "award_abstract", "description"] if c in group.columns),
                        None,
                    )
                    agency_col = next(
                        (c for c in ["agency", "awarding_agency"] if c in group.columns),
                        None,
                    )
                    title_col = next(
                        (c for c in ["solicitation_title", "topic_title", "title"] if c in group.columns),
                        None,
                    )

                    # Concatenate abstracts for this topic (for embedding)
                    abstracts = []
                    if abstract_col:
                        abstracts = group[abstract_col].dropna().tolist()

                    topics.append({
                        "topic_id": str(topic_key),
                        "agency": group[agency_col].iloc[0] if agency_col and agency_col in group.columns else None,
                        "title": group[title_col].iloc[0] if title_col and title_col in group.columns else str(topic_key),
                        "description": " ".join(abstracts[:5]) if abstracts else None,
                        "award_count": len(group),
                        "total_amount": group["award_amount"].sum() if "award_amount" in group.columns else None,
                        "fiscal_years": sorted(group[next((c for c in ["fiscal_year", "award_year", "fy"] if c in group.columns), "fiscal_year")].dropna().unique().tolist()) if any(c in group.columns for c in ["fiscal_year", "award_year", "fy"]) else [],
                        "companies": group[next((c for c in ["company", "company_name"] if c in group.columns), "company")].nunique() if any(c in group.columns for c in ["company", "company_name"]) else 0,
                    })
            else:
                # No topic column — create pseudo-topics from agency + abstract clustering
                metadata.warnings.append(
                    "No solicitation topic column found; topic extraction is limited"
                )
                # Fall back to agency-level grouping
                agency_col = next(
                    (c for c in ["agency", "awarding_agency"] if c in df.columns),
                    None,
                )
                if agency_col:
                    for agency, group in df.groupby(agency_col):
                        topics.append({
                            "topic_id": f"agency-{agency}",
                            "agency": agency,
                            "title": f"All {agency} topics",
                            "description": None,
                            "award_count": len(group),
                            "total_amount": group["award_amount"].sum() if "award_amount" in group.columns else None,
                            "fiscal_years": [],
                            "companies": 0,
                        })

        # Load solicitation data file if provided
        if solicitation_data_path:
            try:
                sol_df = pd.read_csv(solicitation_data_path)
                logger.info(f"Loaded {len(sol_df)} solicitation records from {solicitation_data_path}")
                metadata.data_sources.append(
                    DataSourceRef(
                        name="SBIR.gov Solicitations (file)",
                        url="https://sbir.gov",
                        record_count=len(sol_df),
                        access_method="csv_file",
                    )
                )
            except Exception as e:
                logger.warning(f"Could not load solicitation data: {e}")
                metadata.warnings.append(f"Solicitation file load failed: {e}")

        topics_df = pd.DataFrame(topics) if topics else pd.DataFrame(columns=[
            "topic_id", "agency", "title", "description", "award_count",
            "total_amount", "fiscal_years", "companies",
        ])

        metadata.data_sources.append(
            DataSourceRef(
                name="SBIR.gov Awards",
                url="https://sbir.gov/api",
                version=datetime.utcnow().strftime("%Y-%m-%d"),
                record_count=len(topics_df),
                access_method="award_abstract_extraction",
            )
        )
        metadata.record_count = len(topics_df)

        return ToolResult(data=topics_df, metadata=metadata)
