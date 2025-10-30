# Design Document

## Overview



## Architecture

- New Dagster assets (additive):
  - paecter_embeddings_patents → data/processed/paecter_embeddings_patents.parquet
  - paecter_embeddings_awards → data/processed/paecter_embeddings_awards.parquet
  - paecter_award_patent_similarity → data/processed/paecter_award_patent_similarity.parquet
  - paecter_classifier_cohesion_metrics → data/processed/paecter_classifier_cohesion.json
  - neo4j_award_patent_similarity (optional; off by default)

- Data Flow:
  1) Transform patents → build text (title [+ abstract]) → remote embeddings
  2) Enriched awards → build text (solicitation_title [+ abstract]) → remote embeddings
  3) Similarity: compute award→patent top‑k cosine (brute-force; FAISS optional later)
  4) Cohesion: compute intra-/inter-class metrics per CET label
  5) Optional: load thresholded similarity edges to Neo4j

- Outputs and Observability:
  - Parquet for embeddings and similarity; JSON for metrics and checks
  - Checks JSON adjacent to primary artifacts for asset gating
  - Performance baselines and alerts under reports/{benchmarks,alerts}/

## Components and Interfaces



## Data Models



## Error Handling



## Testing Strategy


