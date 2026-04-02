"""
Semantic topic clustering for cross-agency overlap detection.

Uses ModernBERT-Embed embeddings to find cross-agency topic similarity
clusters. When pre-computed embeddings are not provided, generates them
on-the-fly via the HuggingFace Inference API. High embedding similarity
is necessary but not sufficient for duplication — the LLM judgment point
distinguishes waste from healthy multi-agency investment in shared priorities.

Decision criteria for duplication vs. complementarity:
    (a) Are the operational environments different?
    (b) Are the end users different?
    (c) Are the TRL ranges different?
    If yes to any → likely complementary despite textual similarity.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


class ClusterTopicsTool(BaseTool):
    """Cluster solicitation topics by semantic similarity across agencies.

    Identifies cross-agency topic overlap and complementarity using
    embedding-based similarity with configurable thresholds.
    """

    name = "cluster_topics"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        *,
        topics_df: pd.DataFrame | None = None,
        embeddings: np.ndarray | None = None,
        similarity_threshold: float = 0.85,
        min_cluster_size: int = 2,
        cross_agency_only: bool = True,
        **kwargs: Any,
    ) -> ToolResult:
        """Cluster topics by semantic similarity.

        Args:
            metadata: Pre-initialized metadata to populate
            topics_df: DataFrame with topic_id, agency, title, description
            embeddings: Pre-computed embedding vectors (N x D array)
            similarity_threshold: Cosine similarity threshold for clustering
            min_cluster_size: Minimum topics per cluster
            cross_agency_only: If True, only form clusters spanning 2+ agencies

        Returns:
            ToolResult with cluster assignments and similarity scores
        """
        if topics_df is None or topics_df.empty:
            metadata.warnings.append("No topics provided for clustering")
            return ToolResult(
                data={"clusters": pd.DataFrame(), "similarity_matrix": None},
                metadata=metadata,
            )

        metadata.upstream_tools.append("extract_topics")

        n_topics = len(topics_df)

        if embeddings is not None and len(embeddings) == n_topics:
            # Compute cosine similarity matrix
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            normalized = embeddings / norms
            sim_matrix = normalized @ normalized.T
        else:
            # Fallback: generate embeddings on-the-fly with ModernBERT-Embed
            metadata.warnings.append(
                "No embeddings provided; generating via ModernBERT-Embed"
            )
            try:
                from sbir_ml.ml.config import PaECTERClientConfig
                from sbir_ml.ml.paecter_client import PaECTERClient

                text_col = "description" if "description" in topics_df.columns else "title"
                texts = topics_df[text_col].fillna("").tolist()

                client = PaECTERClient(config=PaECTERClientConfig(use_local=False))
                result = client.generate_embeddings(texts)
                fallback_embeddings = result.embeddings

                # Compute cosine similarity from the generated embeddings
                fb_norms = np.linalg.norm(fallback_embeddings, axis=1, keepdims=True)
                fb_norms = np.where(fb_norms == 0, 1, fb_norms)
                fb_normalized = fallback_embeddings / fb_norms
                sim_matrix = fb_normalized @ fb_normalized.T
            except Exception as e:
                metadata.warnings.append(
                    f"ModernBERT-Embed unavailable ({e}); cannot compute similarity"
                )
                return ToolResult(
                    data={"clusters": pd.DataFrame(), "similarity_matrix": None},
                    metadata=metadata,
                )

        # Greedy agglomerative clustering based on similarity threshold
        clusters: list[dict[str, Any]] = []
        assigned = set()
        cluster_id = 0

        agencies = topics_df["agency"].tolist() if "agency" in topics_df.columns else [None] * n_topics
        topic_ids = topics_df["topic_id"].tolist() if "topic_id" in topics_df.columns else list(range(n_topics))

        for i in range(n_topics):
            if i in assigned:
                continue

            # Find all topics similar to topic i
            similar_indices = []
            for j in range(i + 1, n_topics):
                if j in assigned:
                    continue
                if sim_matrix[i, j] >= similarity_threshold:
                    similar_indices.append(j)

            if not similar_indices:
                continue

            # Form candidate cluster
            candidate = [i] + similar_indices

            # Check cross-agency constraint
            if cross_agency_only:
                cluster_agencies = {agencies[idx] for idx in candidate if agencies[idx] is not None}
                if len(cluster_agencies) < 2:
                    continue

            if len(candidate) < min_cluster_size:
                continue

            # Calculate cluster statistics
            cluster_agencies = {agencies[idx] for idx in candidate if agencies[idx] is not None}
            pairwise_sims = [
                sim_matrix[a, b] for a in candidate for b in candidate if a < b
            ]
            avg_sim = float(np.mean(pairwise_sims)) if pairwise_sims else 0.0

            cluster_topics = [topic_ids[idx] for idx in candidate]
            clusters.append({
                "cluster_id": f"cluster-{cluster_id:04d}",
                "topic_ids": cluster_topics,
                "agencies_involved": sorted(a for a in cluster_agencies if a is not None),
                "num_agencies": len(cluster_agencies),
                "num_topics": len(candidate),
                "avg_similarity": round(avg_sim, 4),
                "max_similarity": round(float(max(pairwise_sims)) if pairwise_sims else 0.0, 4),
                "classification": "ambiguous",  # LLM judgment point — not resolved here
                "classification_reasoning": None,
            })

            assigned.update(candidate)
            cluster_id += 1

        clusters_df = pd.DataFrame(clusters) if clusters else pd.DataFrame(columns=[
            "cluster_id", "topic_ids", "agencies_involved", "num_agencies",
            "num_topics", "avg_similarity", "max_similarity",
            "classification", "classification_reasoning",
        ])

        metadata.record_count = len(clusters_df)
        metadata.data_sources.append(
            DataSourceRef(
                name="SBIR.gov Solicitations",
                url="https://sbir.gov",
                record_count=n_topics,
                access_method="embedding_similarity",
            )
        )

        return ToolResult(
            data={
                "clusters": clusters_df,
                "stats": {
                    "total_topics": n_topics,
                    "clustered_topics": len(assigned),
                    "unclustered_topics": n_topics - len(assigned),
                    "num_clusters": len(clusters),
                    "cross_agency_clusters": len([c for c in clusters if c["num_agencies"] >= 2]),
                    "similarity_threshold": similarity_threshold,
                },
            },
            metadata=metadata,
        )
