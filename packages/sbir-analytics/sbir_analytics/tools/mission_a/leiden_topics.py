"""Graph-based topic clustering using LightRAG Leiden communities.

Replacement for :class:`ClusterTopicsTool`.  Instead of greedy agglomerative
clustering on raw embedding similarity, this tool queries pre-computed Leiden
communities from the LightRAG knowledge graph.  Communities are formed by
shared extracted entities (technologies, methods, problems) — giving
explainable, multi-resolution clusters that naturally span agencies.

Advantages over ClusterTopicsTool:
    - Clusters on shared entities, not opaque cosine similarity
    - Hierarchical multi-resolution communities via ``max_community_levels``
    - Explainable via entity co-occurrence
    - Cross-agency naturally without a ``cross_agency_only`` flag
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


class LeidenTopicsTool(BaseTool):
    """Cluster topics using LightRAG Leiden communities.

    Queries the ``__community__`` nodes in Neo4j (populated by LightRAG
    during document ingestion) and maps them to the same output schema
    as :class:`ClusterTopicsTool` for drop-in compatibility.
    """

    name = "leiden_topics"
    version = "2.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        *,
        communities_df: pd.DataFrame | None = None,
        min_cluster_size: int = 2,
        min_level: int = 0,
        max_level: int | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Build topic clusters from Leiden communities.

        Args:
            metadata: Pre-initialized metadata to populate.
            communities_df: DataFrame from ``lightrag_topic_communities`` asset
                with columns: community_id, level, title, entities, award_ids, agencies.
            min_cluster_size: Minimum entities per community to include.
            min_level: Minimum community hierarchy level (0 = finest).
            max_level: Maximum community hierarchy level (None = all).

        Returns:
            ToolResult with cluster assignments matching ClusterTopicsTool schema.
        """
        if communities_df is None or communities_df.empty:
            metadata.warnings.append("No communities provided for clustering")
            return ToolResult(
                data={
                    "clusters": pd.DataFrame(),
                    "stats": {
                        "total_communities": 0,
                        "included_communities": 0,
                        "total_entities": 0,
                    },
                },
                metadata=metadata,
            )

        metadata.upstream_tools.append("lightrag_topic_communities")

        # Filter by hierarchy level
        filtered = communities_df.copy()
        if "level" in filtered.columns:
            filtered = filtered[filtered["level"] >= min_level]
            if max_level is not None:
                filtered = filtered[filtered["level"] <= max_level]

        # Filter by minimum cluster size (entities)
        if "num_entities" in filtered.columns:
            filtered = filtered[filtered["num_entities"] >= min_cluster_size]

        # Build output matching ClusterTopicsTool schema
        clusters = []
        for _, row in filtered.iterrows():
            agencies = row.get("agencies", [])
            if agencies is None:
                agencies = []

            clusters.append({
                "cluster_id": str(row.get("community_id", "")),
                "topic_ids": row.get("award_ids", []) or [],
                "agencies_involved": sorted(a for a in agencies if a),
                "num_agencies": len([a for a in agencies if a]),
                "num_topics": row.get("num_awards", 0),
                "num_entities": row.get("num_entities", 0),
                "avg_similarity": None,  # Not applicable — graph-based
                "max_similarity": None,
                "community_title": row.get("title"),
                "community_summary": row.get("summary"),
                "entities": row.get("entities", []),
                "level": row.get("level"),
                "classification": "ambiguous",  # LLM judgment point
                "classification_reasoning": None,
            })

        clusters_df = pd.DataFrame(clusters) if clusters else pd.DataFrame(columns=[
            "cluster_id", "topic_ids", "agencies_involved", "num_agencies",
            "num_topics", "num_entities", "avg_similarity", "max_similarity",
            "community_title", "community_summary", "entities", "level",
            "classification", "classification_reasoning",
        ])

        metadata.record_count = len(clusters_df)
        metadata.data_sources.append(
            DataSourceRef(
                name="LightRAG Leiden Communities",
                url="neo4j://__community__",
                record_count=len(communities_df),
                access_method="graph_query",
            )
        )

        total_entities = int(filtered["num_entities"].sum()) if len(filtered) > 0 else 0
        cross_agency = len([c for c in clusters if c["num_agencies"] >= 2])

        return ToolResult(
            data={
                "clusters": clusters_df,
                "stats": {
                    "total_communities": len(communities_df),
                    "included_communities": len(clusters_df),
                    "filtered_by_level": len(communities_df) - len(filtered),
                    "filtered_by_size": len(filtered) - len(clusters_df),
                    "total_entities": total_entities,
                    "cross_agency_clusters": cross_agency,
                },
            },
            metadata=metadata,
        )
