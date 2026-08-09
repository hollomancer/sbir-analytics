# Implementation Plan

## Status (2026-07-02)

**Phase 1 is fully implemented; Phase 2/3 are partially done.** The client lives at `packages/sbir-ml/sbir_ml/ml/modernbert_client.py`, the Dagster assets at `packages/sbir-analytics/sbir_analytics/assets/modernbert/embeddings.py`, and config schemas at `sbir_etl/config/schemas/domain.py` (earlier `src/...` path notes have been corrected). Verified done since the last update: performance monitoring for embedding generation and similarity computation (`performance_monitor.monitor_block` in the assets), and most documentation (`docs/ml/modernbert.md`, `docs/configuration.md`) — individual sub-items ticked below. Still open: the Neo4j `SIMILAR_TO` edge-loading asset (2.1 — the `ml.modernbert.neo4j` config block exists in `config/base.yaml` but no loading asset or `ModernBertNeo4jConfig` schema class exists), quality metrics/cohesion asset (2.3), similarity-distribution/regression asset checks (2.4 — only the two coverage checks exist), Dagster-asset-level integration tests (3.2 — client-level integration tests exist in `tests/integration/test_modernbert_client.py` and one asset materialization in `tests/functional/test_pipelines.py`), Neo4j schema documentation (3.3), and dashboards/alerting (3.4). Related history: PR #365 renamed PaECTER → ModernBERT across the pipeline; PR #413 wired ModernBERT text similarity into the transition scorer (separate from this spec's assets).

## Phase 1: Core ModernBert Infrastructure

- [x] 1.1 Implement ModernBert client wrapper for Hugging Face API
  - [x] Create `ModernBertClient` class with batch processing and caching
  - [x] Implement authentication via Bearer token from environment variable
  - [x] Support both API mode (HuggingFace) and local mode (sentence-transformers)
  - [x] Include embedding metadata (model_id, inference_mode, dimension, timestamp)
  - _Requirements: 1.1, 1.2_
  - _Status: Implemented in `packages/sbir-ml/sbir_ml/ml/modernbert_client.py`_

- [x] 1.2 Implement text preprocessing utilities
  - [x] Create text builders for patents (title + abstract) and awards (solicitation_title + abstract)
  - [x] Add field concatenation with space separator, whitespace trimming
  - [x] Static methods `prepare_patent_text()` and `prepare_award_text()`
  - _Requirements: 1.1, 1.2_
  - _Status: Implemented in `ModernBertClient` class_

- [x] 1.3 Create core Dagster assets for basic ModernBert functionality
  - [x] `modernbert_embeddings_awards` → generates embeddings for SBIR awards
  - [x] `modernbert_embeddings_patents` → generates embeddings for USPTO patents
  - [x] Include columns: award_id/patent_id, embedding, model_version, inference_mode, dimension
  - [x] Add asset checks for embedding coverage thresholds
  - _Requirements: 1.1, 1.2_
  - _Status: Implemented in `packages/sbir-analytics/sbir_analytics/assets/modernbert/embeddings.py`_

- [x] 1.4 Implement basic similarity computation
  - [x] Create `modernbert_award_patent_similarity` asset with cosine similarity computation
  - [x] Support brute-force similarity computation
  - [x] Output similarity pairs with scores above configurable threshold
  - [x] Top-k filtering (top 10 per award)
  - _Requirements: 2.1, 2.2_
  - _Status: Implemented in `packages/sbir-analytics/sbir_analytics/assets/modernbert/embeddings.py`_

- [x] 1.5 Add `ml.modernbert.*` configuration block to config/base.yaml
  - [x] use_local: false (default to API mode)
  - [x] model_name: "mpi-inno-comp/modernbert"
  - [x] batch_size: 32
  - [x] similarity_threshold: 0.80
  - [x] coverage_threshold_awards: 0.95
  - [x] coverage_threshold_patents: 0.98
  - [x] enable_cache: false
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Status: Config exists in `config/base.yaml`. Validated Pydantic schema lives in `sbir_etl/config/schemas/domain.py` with `MLConfig` and `ModernBertConfig` models wired into `PipelineConfig`._

## Phase 2: Neo4j Integration and Quality Validation

- [ ] 2.1 Implement Neo4j similarity edge loading asset
  - [ ] Create `neo4j_modernbert_similarity_edges` Dagster asset (optional, disabled by default)
  - [ ] Load similarity pairs as (Award)-[:SIMILAR_TO {score, method:"modernbert", rank, computed_at}]->(Patent)
  - [ ] Use MERGE for idempotent relationship creation
  - [ ] Include configurable batch size and transaction management
  - [ ] Add dry-run mode for testing without committing changes
  - _Requirements: 4.1, 4.2, 4.3_
  - _Status (2026-07-02): Not implemented — no `neo4j_modernbert_similarity_edges` asset or `SIMILAR_TO` loader exists in `packages/`. Only the config block (task 2.2) exists._

- [x] 2.2 Add Neo4j configuration to config/base.yaml
  - [x] ml.modernbert.neo4j.enabled: false (disabled by default)
  - [x] ml.modernbert.neo4j.batch_size: 1000
  - [x] ml.modernbert.neo4j.dry_run: false
  - [x] ml.modernbert.neo4j.prune_previous: false (optional cleanup of old edges)
  - _Requirements: 4.1, 4.2, 4.3_
  - _Status: Config added to `config/base.yaml` under `ml.modernbert.neo4j` (enabled/batch_size/dry_run/prune_previous, verified 2026-07-02). Drift note: no `ModernBertNeo4jConfig` schema class exists anymore — `ModernBertConfig` in `sbir_etl/config/schemas/domain.py` has no `neo4j` field, so the YAML block is currently unvalidated._

- [ ] 2.3 Implement quality metrics and performance baselines
  - [ ] Create `modernbert_quality_metrics` asset for tracking embedding quality
  - [ ] Generate performance baselines for similarity computation
  - [ ] Add cohesion metrics to validate embeddings cluster within CET classifications
  - [ ] Implement quality gates for embedding coverage and similarity distributions
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - _Status (2026-07-02): Not implemented — no `modernbert_quality_metrics` asset or cohesion metrics exist; only the two coverage asset checks from task 1.3._

- [ ] 2.4 Add comprehensive asset checks
  - [ ] Implement similarity score distribution validation
  - [ ] Add checks for top-k similarity consistency
  - [ ] Create regression detection for similarity quality
  - [x] Add performance monitoring for embedding generation time — implemented: `performance_monitor.monitor_block("modernbert_generate_award_embeddings"/"modernbert_generate_patent_embeddings")` in `packages/sbir-analytics/sbir_analytics/assets/modernbert/embeddings.py`
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - _Status (2026-07-02): Only the performance-monitoring sub-item is done; existing asset checks are limited to the two coverage checks (`modernbert_awards_coverage_check`, `modernbert_patents_coverage_check`)._

## Phase 3: Testing and Documentation

- [x] 3.1 Unit testing for ModernBert components
  - [x] Test ModernBert client configuration and initialization
  - [x] Test text preprocessing edge cases (missing fields, empty strings)
  - [x] Test embedding caching behavior
  - [x] Test similarity computation with various input sizes
  - _Requirements: All requirements_
  - _Status: 19 tests in `tests/unit/ml/test_modernbert_client.py` covering config, text prep edge cases, caching, and similarity computation (identical, orthogonal, matrix shape)._

- [ ] 3.2 Integration testing for Dagster assets
  - [ ] Test complete embedding generation pipeline (awards → patents → similarity)
  - [ ] Test asset dependency resolution and execution order
  - [ ] Test asset checks trigger correctly on quality threshold violations
  - [ ] Test Neo4j loading with mock data (if enabled)
  - _Requirements: All requirements_
  - _Status (2026-07-02): Partial but below the bar — `tests/integration/test_modernbert_client.py` covers the awards→patents→similarity flow at the client level, and `tests/functional/test_pipelines.py` materializes the `modernbert_embeddings_awards` asset only. No multi-asset dependency/asset-check/Neo4j integration tests exist, so left unchecked._

- [ ] 3.3 Create comprehensive documentation
  - [x] Document ModernBert configuration options in config/base.yaml — implemented: `docs/ml/modernbert.md` (Configuration section) and `docs/configuration.md` (ModernBert Configuration section)
  - [x] Document Dagster asset usage and dependencies — implemented: `docs/ml/modernbert.md` (Architecture / Dagster Assets sections)
  - [ ] Document Neo4j schema for SIMILAR_TO relationships
  - [x] Create usage examples for common workflows — implemented: `docs/ml/modernbert.md` (Usage: Dagster UI, CLI, programmatic examples)
  - _Requirements: All requirements_
  - _Status (2026-07-02): Docs are comprehensive except the Neo4j `SIMILAR_TO` schema, which is undocumented (the loading asset itself — task 2.1 — is also unimplemented)._

- [ ] 3.4 Add monitoring and observability
  - [x] Implement performance metrics collection for embedding generation — implemented: `performance_monitor.monitor_block(...)` in `packages/sbir-analytics/sbir_analytics/assets/modernbert/embeddings.py` (documented in `docs/ml/modernbert.md`, Monitoring section)
  - [x] Add similarity computation performance tracking — implemented: `performance_monitor.monitor_block("modernbert_compute_similarities")` in `packages/sbir-analytics/sbir_analytics/assets/modernbert/embeddings.py`
  - [ ] Create dashboards for ModernBert pipeline health
  - [ ] Add alerting for quality threshold violations
  - _Requirements: All requirements_
  - _Status (2026-07-02): Performance instrumentation is in place; no dashboards or AlertCollector-based alerting exist for ModernBert assets._

## Future Enhancements (Optional - Not in Current Scope)

The following Bayesian MoE enhancements are documented in the design but marked as optional future work. They are NOT required for the core ModernBert functionality and should only be implemented if explicitly requested:

- [ ]* Bayesian MoE Framework Foundation (Phase 2 from original design)
  - Bayesian router framework with uncertainty quantification
  - LoRA expert pool management system
  - Uncertainty head with ECE computation and calibration
  - _Requirements: 5.1, 6.1, 7.1_

- [ ]* Stage 1: Bayesian Classification Routing (Phase 3 from original design)
  - Bayesian classification router with variational inference
  - LoRA adapters for CET/CPC classification experts
  - Classification routing Dagster asset with uncertainty metrics
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ]* Stage 2: Bayesian Similarity Routing (Phase 4 from original design)
  - Bayesian similarity router with category-conditioned routing
  - LoRA adapters for similarity experts (intra-category, cross-category, temporal)
  - Similarity routing asset with Bayesian model averaging
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ]* Stage 3: Bayesian Embedding Routing (Phase 5 from original design)
  - Bayesian embedding router with multi-stage informed routing
  - Domain-specific ModernBert LoRA adapters
  - Embedding routing asset with uncertainty propagation
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
