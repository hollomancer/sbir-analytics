# Requirements Document

## Introduction

This specification implements add-paecter-analysis-layer.

We want a robust, explainable, and retrieval-friendly analysis layer that complements our existing CET-based patent and award classifiers. PaECTER provides high-quality patent embeddings that enable semantic search, prior-art style similarity, cohort cohesion checks, and award↔patent cross-linking to improve discovery, validation, and downstream analytics.

We will use Hugging Face’s hosted Inference API by default (no local GPU required) to accelerate adoption. As a later option, we will support Hugging Face Inference Endpoints for dedicated capacity and tighter performance SLOs.

## Glossary

- **CET**: System component or technology referenced in the implementation
- **API**: System component or technology referenced in the implementation
- **GPU**: System component or technology referenced in the implementation
- **FAISS**: System component or technology referenced in the implementation
- **MERGE**: System component or technology referenced in the implementation
- **YAML**: System component or technology referenced in the implementation
- **JSON**: System component or technology referenced in the implementation
- **mpi-inno-comp/paecter**: Code component or file: mpi-inno-comp/paecter
- **paecter_embeddings_patents**: Code component or file: paecter_embeddings_patents
- **data/processed/paecter_embeddings_patents.parquet**: Code component or file: data/processed/paecter_embeddings_patents.parquet
- **patent_id**: Code component or file: patent_id
- **text_source**: Code component or file: text_source
- **embedding**: Code component or file: embedding
- **model_name**: Code component or file: model_name
- **model_revision**: Code component or file: model_revision
- **provider**: Code component or file: provider
- **computed_at**: Code component or file: computed_at
- **paecter_embeddings_awards**: Code component or file: paecter_embeddings_awards
- **data/processed/paecter_embeddings_awards.parquet**: Code component or file: data/processed/paecter_embeddings_awards.parquet
- **award_id**: Code component or file: award_id
- **solicitation_title**: Code component or file: solicitation_title
- **abstract**: Code component or file: abstract
- **paecter_award_patent_similarity**: Code component or file: paecter_award_patent_similarity
- **data/processed/paecter_award_patent_similarity.parquet**: Code component or file: data/processed/paecter_award_patent_similarity.parquet
- **cosine_sim**: Code component or file: cosine_sim
- **rank**: Code component or file: rank
- **threshold_pass**: Code component or file: threshold_pass
- **backend**: Code component or file: backend
- **paecter_classifier_cohesion_metrics**: Code component or file: paecter_classifier_cohesion_metrics
- **data/processed/paecter_classifier_cohesion.json**: Code component or file: data/processed/paecter_classifier_cohesion.json
- **neo4j_award_patent_similarity**: Code component or file: neo4j_award_patent_similarity
- **(Award)-[:SIMILAR_TO {score, method: "paecter", model, revision, computed_at, rank}]->(Patent)**: Code component or file: (Award)-[:SIMILAR_TO {score, method: "paecter", model, revision, computed_at, rank}]->(Patent)
- **paecter.provider**: Code component or file: paecter.provider
- **huggingface**: Code component or file: huggingface
- **local**: Code component or file: local
- **paecter.endpoint.type**: Code component or file: paecter.endpoint.type
- **inference_api**: Code component or file: inference_api
- **endpoint**: Code component or file: endpoint
- **paecter.endpoint.url**: Code component or file: paecter.endpoint.url
- **paecter.auth.token_env**: Code component or file: paecter.auth.token_env
- **HF_API_TOKEN**: Code component or file: HF_API_TOKEN
- **paecter.remote.batch.size**: Code component or file: paecter.remote.batch.size
- **paecter.remote.max_qps**: Code component or file: paecter.remote.max_qps
- **paecter.remote.timeout_seconds**: Code component or file: paecter.remote.timeout_seconds
- **paecter.remote.retry.max_retries**: Code component or file: paecter.remote.retry.max_retries
- **paecter.remote.retry.backoff_seconds**: Code component or file: paecter.remote.retry.backoff_seconds
- **paecter.max_length**: Code component or file: paecter.max_length
- **paecter.cache.enable**: Code component or file: paecter.cache.enable
- **paecter.text.award_fields**: Code component or file: paecter.text.award_fields
- **["solicitation_title", "abstract"]**: Code component or file: ["solicitation_title", "abstract"]
- **paecter.text.patent_fields**: Code component or file: paecter.text.patent_fields
- **["title", "abstract"]**: Code component or file: ["title", "abstract"]
- **paecter.similarity.top_k**: Code component or file: paecter.similarity.top_k
- **paecter.similarity.min_score**: Code component or file: paecter.similarity.min_score
- **paecter.join.limit_per_award**: Code component or file: paecter.join.limit_per_award
- **paecter.index.backend**: Code component or file: paecter.index.backend
- **bruteforce**: Code component or file: bruteforce
- **faiss**: Code component or file: faiss
- **paecter.index.path**: Code component or file: paecter.index.path
- **artifacts/indexes/paecter/awards_patents.faiss**: Code component or file: artifacts/indexes/paecter/awards_patents.faiss
- **paecter.enable_neo4j_edges**: Code component or file: paecter.enable_neo4j_edges
- **paecter.neo4j.prune_previous**: Code component or file: paecter.neo4j.prune_previous
- **paecter.neo4j.mark_current**: Code component or file: paecter.neo4j.mark_current
- **paecter.neo4j.max_concurrency**: Code component or file: paecter.neo4j.max_concurrency
- **paecter.neo4j.txn_batch_size**: Code component or file: paecter.neo4j.txn_batch_size
- **paecter.neo4j.dry_run**: Code component or file: paecter.neo4j.dry_run
- **paecter.validation.coverage.patents**: Code component or file: paecter.validation.coverage.patents
- **paecter.validation.coverage.awards**: Code component or file: paecter.validation.coverage.awards
- **paecter.validation.similarity.neg_mean_max**: Code component or file: paecter.validation.similarity.neg_mean_max
- **paecter.validation.similarity.pos_mean_min**: Code component or file: paecter.validation.similarity.pos_mean_min
- **paecter.validation.cohesion.margin_min**: Code component or file: paecter.validation.cohesion.margin_min
- **paecter.validation.cohesion.min_share**: Code component or file: paecter.validation.cohesion.min_share
- **paecter.validation.cohesion.min_size**: Code component or file: paecter.validation.cohesion.min_size
- **reports/benchmarks/paecter_embeddings.json**: Code component or file: reports/benchmarks/paecter_embeddings.json
- **reports/benchmarks/paecter_validation_baseline.json**: Code component or file: reports/benchmarks/paecter_validation_baseline.json
- **reports/alerts/paecter_*.json**: Code component or file: reports/alerts/paecter_*.json
- **sentence-transformers**: Code component or file: sentence-transformers
- **transformers**: Code component or file: transformers
- **torch**: Code component or file: torch
- **faiss-cpu**: Code component or file: faiss-cpu
- **model_id**: Code component or file: model_id
- **revision**: Code component or file: revision

## Requirements

### Requirement 1

**User Story:** As a developer, I want add-paecter-analysis-layer, so that we want a robust, explainable, and retrieval-friendly analysis layer that complements our existing cet-based patent and award classifiers.

#### Acceptance Criteria

1. THE System SHALL implement add-paecter-analysis-layer
2. THE System SHALL validate the implementation of add-paecter-analysis-layer

### Requirement 2

**User Story:** As a developer, I want Add a PaECTER-powered analysis layer that is strictly additive to current classifiers (no breaking behavioral changes):, so that support the enhanced functionality described in the proposal.

#### Acceptance Criteria

1. THE System SHALL implement a paecter-powered analysis layer that is strictly additive to current classifiers (no breaking behavioral changes):
2. THE System SHALL validate the implementation of a paecter-powered analysis layer that is strictly additive to current classifiers (no breaking behavioral changes):

### Requirement 3

**User Story:** As a developer, I want Compute dense embeddings for patents and awards using `mpi-inno-comp/paecter` via Hugging Face Inference API, so that support the enhanced functionality described in the proposal.

#### Acceptance Criteria

1. THE System SHALL support compute dense embeddings for patents and awards using `mpi-inno-comp/paecter` via hugging face inference api
2. THE System SHALL ensure proper operation of compute dense embeddings for patents and awards using `mpi-inno-comp/paecter` via hugging face inference api

### Requirement 4

**User Story:** As a developer, I want Produce award↔patent semantic similarity pairs (top-k with thresholds), so that support the enhanced functionality described in the proposal.

#### Acceptance Criteria

1. THE System SHALL support produce award↔patent semantic similarity pairs (top-k with thresholds)
2. THE System SHALL ensure proper operation of produce award↔patent semantic similarity pairs (top-k with thresholds)

