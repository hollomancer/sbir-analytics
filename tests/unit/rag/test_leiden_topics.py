"""Tests for LeidenTopicsTool."""

from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

# sbir_analytics may not be installed in this test environment.
# Add the package source to sys.path if needed.
_pkg_path = str(__import__("pathlib").Path(__file__).resolve().parents[3] / "packages" / "sbir-analytics")
if _pkg_path not in sys.path:
    sys.path.insert(0, _pkg_path)

from sbir_analytics.tools.base import ToolMetadata
from sbir_analytics.tools.mission_a.leiden_topics import LeidenTopicsTool


@pytest.fixture
def tool():
    return LeidenTopicsTool()


@pytest.fixture
def metadata():
    return ToolMetadata(
        tool_name="leiden_topics",
        tool_version="2.0.0",
        execution_start=datetime.now(),
    )


@pytest.fixture
def communities_df():
    return pd.DataFrame([
        {
            "community_id": "comm-001",
            "level": 0,
            "title": "Quantum Sensing",
            "summary": "Quantum technologies for navigation",
            "entities": ["quantum", "navigation", "GPS"],
            "award_ids": ["AWD-001", "AWD-002", "AWD-003"],
            "num_entities": 3,
            "num_awards": 3,
            "agencies": ["DOD", "DOE"],
        },
        {
            "community_id": "comm-002",
            "level": 0,
            "title": "Autonomous Systems",
            "summary": "Self-driving platforms",
            "entities": ["autonomy", "lidar"],
            "award_ids": ["AWD-004", "AWD-005"],
            "num_entities": 2,
            "num_awards": 2,
            "agencies": ["DOD"],
        },
        {
            "community_id": "comm-003",
            "level": 1,
            "title": "Broad AI Research",
            "summary": "AI across agencies",
            "entities": ["machine learning", "neural networks", "deep learning", "NLP"],
            "award_ids": ["AWD-006", "AWD-007", "AWD-008", "AWD-009"],
            "num_entities": 4,
            "num_awards": 4,
            "agencies": ["DOD", "NSF", "DOE"],
        },
    ])


class TestLeidenTopicsTool:
    """Tests for the Leiden community-based topic clustering tool."""

    def test_basic_attributes(self, tool):
        assert tool.name == "leiden_topics"
        assert tool.version == "2.0.0"

    def test_empty_communities(self, tool, metadata):
        result = tool.execute(metadata, communities_df=pd.DataFrame())

        assert result.data["clusters"].empty
        assert "No communities provided" in metadata.warnings[0]

    def test_none_communities(self, tool, metadata):
        result = tool.execute(metadata, communities_df=None)

        assert result.data["clusters"].empty

    def test_produces_clusters(self, tool, metadata, communities_df):
        result = tool.execute(metadata, communities_df=communities_df)

        clusters = result.data["clusters"]
        assert len(clusters) == 3
        assert "cluster_id" in clusters.columns
        assert "topic_ids" in clusters.columns
        assert "agencies_involved" in clusters.columns

    def test_output_schema_compatible(self, tool, metadata, communities_df):
        """Output schema matches ClusterTopicsTool for drop-in compatibility."""
        result = tool.execute(metadata, communities_df=communities_df)
        clusters = result.data["clusters"]

        required_cols = [
            "cluster_id", "topic_ids", "agencies_involved",
            "num_agencies", "num_topics", "classification",
        ]
        for col in required_cols:
            assert col in clusters.columns, f"Missing column: {col}"

    def test_min_cluster_size_filter(self, tool, metadata, communities_df):
        result = tool.execute(
            metadata, communities_df=communities_df, min_cluster_size=3,
        )

        clusters = result.data["clusters"]
        # Only comm-001 (3 entities) and comm-003 (4 entities) pass
        assert len(clusters) == 2

    def test_level_filter(self, tool, metadata, communities_df):
        result = tool.execute(
            metadata, communities_df=communities_df, min_level=1,
        )

        clusters = result.data["clusters"]
        # Only comm-003 at level 1
        assert len(clusters) == 1
        assert clusters.iloc[0]["cluster_id"] == "comm-003"

    def test_max_level_filter(self, tool, metadata, communities_df):
        result = tool.execute(
            metadata, communities_df=communities_df, max_level=0,
        )

        clusters = result.data["clusters"]
        # comm-001 and comm-002 at level 0
        assert len(clusters) == 2

    def test_metadata_populated(self, tool, metadata, communities_df):
        result = tool.execute(metadata, communities_df=communities_df)

        assert result.metadata.record_count == 3
        assert len(result.metadata.data_sources) == 1
        assert result.metadata.data_sources[0].name == "LightRAG Leiden Communities"
        assert "lightrag_topic_communities" in result.metadata.upstream_tools

    def test_stats_output(self, tool, metadata, communities_df):
        result = tool.execute(metadata, communities_df=communities_df)

        stats = result.data["stats"]
        assert stats["total_communities"] == 3
        assert stats["included_communities"] == 3
        assert stats["cross_agency_clusters"] == 2  # comm-001, comm-003
