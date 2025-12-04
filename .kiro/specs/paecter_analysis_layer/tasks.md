# Implementation Plan

## Phase 1: Core PaECTER Infrastructure

- [x] 1.1 Implement PaECTER client wrapper for Hugging Face API
  - [x] Create `PaECTERClient` class with batch processing and caching
  - [x] Implement authentication via Bearer token from environment variable
  - [x] Support both API mode (HuggingFace) and local mode (sentence-transformers)
  - [x] Include embedding metadata (model_id, inference_mode, dimension, timestamp)
  - _Requirements: 1.1, 1.2_
  - _Status: Implemented in `src/ml/paecter_client.py`_

- [x] 1.2 Implement text preprocessing utilities
  - [x] Create text builders for patents (title + abstract) and awards (solicitation_title + abstract)
  - [x] Add field concatenation with space separator, whitespace trimming
  - [x] Static methods `prepare_patent_text()` and `prepare_award_text()`
  - _Requirements: 1.1, 1.2_
  - _Status: Implemented in `PaECTERClient` class_

- [x] 1.3 Create core Dagster assets for basic PaECTER functionality
  - [x] `paecter_embeddings_awards` → generates embeddings for SBIR awards
  - [x] `paecter_embeddings_patents` → generates embeddings for USPTO patents
  - [x] Include columns: award_id/patent_id, embedding, model_version, inference_mode, dimension
  - [x] Add asset checks for embedding coverage thresholds
  - _Requirements: 1.1, 1.2_
  - _Status: Implemented in `src/assets/paecter/embeddings.py`_

- [x] 1.4 Implement basic similarity computation
  - [x] Create `paecter_award_patent_similarity` asset with cosine similarity computation
  - [x] Support brute-force similarity computation
  - [x] Output similarity pairs with scores above configurable threshold
  - [x] Top-k filtering (top 10 per award)
  - _Requirements: 2.1, 2.2_
  - _Status: Implemented in `src/assets/paecter/embeddings.py`_

- [ ] 1.5 Add `ml.paecter.*` configuration block to config/base.yaml
  - [ ] use_local: false (default to API mode)
  - [ ] model_name: "mpi-inno-comp/paecter"
  - [ ] batch_size: 32
  - [ ] similarity_threshold: 0.80
  - [ ] coverage_threshold_awards: 0.95
  - [ ] coverage_threshold_patents: 0.98
  - [ ] enable_cache: false
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

## Phase 2: Neo4j Integration and Quality Validation

- [ ] 2.1 Implement Neo4j similarity edge loading asset
  - [ ] Create `neo4j_paecter_similarity_edges` Dagster asset (optional, disabled by default)
  - [ ] Load similarity pairs as (Award)-[:SIMILAR_TO {score, method:"paecter", rank, computed_at}]->(Patent)
  - [ ] Use MERGE for idempotent relationship creation
  - [ ] Include configurable batch size and transaction management
  - [ ] Add dry-run mode for testing without committing changes
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 2.2 Add Neo4j configuration to config/base.yaml
  - [ ] ml.paecter.enable_neo4j_edges: false (disabled by default)
  - [ ] ml.paecter.neo4j.batch_size: 1000
  - [ ] ml.paecter.neo4j.dry_run: false
  - [ ] ml.paecter.neo4j.prune_previous: false (optional cleanup of old edges)
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 2.3 Implement quality metrics and performance baselines
  - [ ] Create `paecter_quality_metrics` asset for tracking embedding quality
  - [ ] Generate performance baselines for similarity computation
  - [ ] Add cohesion metrics to validate embeddings cluster within CET classifications
  - [ ] Implement quality gates for embedding coverage and similarity distributions
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 2.4 Add comprehensive asset checks
  - [ ] Implement similarity score distribution validation
  - [ ] Add checks for top-k similarity consistency
  - [ ] Create regression detection for similarity quality
  - [ ] Add performance monitoring for embedding generation time
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

## Phase 3: Testing and Documentation

- [ ] 3.1 Unit testing for PaECTER components
  - [ ] Test PaECTER client configuration and initialization
  - [ ] Test text preprocessing edge cases (missing fields, empty strings)
  - [ ] Test embedding caching behavior
  - [ ] Test similarity computation with various input sizes
  - _Requirements: All requirements_

- [ ] 3.2 Integration testing for Dagster assets
  - [ ] Test complete embedding generation pipeline (awards → patents → similarity)
  - [ ] Test asset dependency resolution and execution order
  - [ ] Test asset checks trigger correctly on quality threshold violations
  - [ ] Test Neo4j loading with mock data (if enabled)
  - _Requirements: All requirements_

- [ ] 3.3 Create comprehensive documentation
  - [ ] Document PaECTER configuration options in config/base.yaml
  - [ ] Document Dagster asset usage and dependencies
  - [ ] Document Neo4j schema for SIMILAR_TO relationships
  - [ ] Create usage examples for common workflows
  - _Requirements: All requirements_

- [ ] 3.4 Add monitoring and observability
  - [ ] Implement performance metrics collection for embedding generation
  - [ ] Add similarity computation performance tracking
  - [ ] Create dashboards for PaECTER pipeline health
  - [ ] Add alerting for quality threshold violations
  - _Requirements: All requirements_

## Future Enhancements (Optional - Not in Current Scope)

The following Bayesian MoE enhancements are documented in the design but marked as optional future work. They are NOT required for the core PaECTER functionality and should only be implemented if explicitly requested:

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
  - Domain-specific PaECTER LoRA adapters
  - Embedding routing asset with uncertainty propagation
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
