# Implementation Plan

## Phase 1: Core PaECTER Infrastructure

- [ ] 1.1 Add `paecter.*` configuration block to config/base.yaml with core settings
  - [ ] provider: `huggingface` (default), `local` (fallback)
  - [ ] endpoint.type: `inference_api` (default), `endpoint` (later option)
  - [ ] auth.token_env: `HF_API_TOKEN`
  - [ ] remote.batch.size: 64, max_qps: 10, timeout_seconds: 60
  - [ ] cache.enable: false, max_length: 512
  - [ ] text.award_fields: ["solicitation_title", "abstract"]
  - [ ] text.patent_fields: ["title", "abstract"]
  - [ ] validation.coverage.patents: 0.98, validation.coverage.awards: 0.95
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 1.2 Implement PaECTER client wrapper for Hugging Face API
  - [ ] Create `PaECTERClient` class with batch processing, rate limiting, and retry logic
  - [ ] Implement authentication via Bearer token from environment variable
  - [ ] Add exponential backoff for 429/5xx errors with jittered delays
  - [ ] Include embedding metadata (model_id, revision, provider, timestamp)
  - _Requirements: 1.1, 1.2_

- [ ] 1.3 Implement text preprocessing utilities
  - [ ] Create text builders for patents (title + abstract) and awards (solicitation_title + abstract)
  - [ ] Add field concatenation with " — " separator, whitespace trimming
  - [ ] Implement token truncation to max_length with safe fallback behavior
  - _Requirements: 1.1, 1.2_

- [ ] 1.4 Create core Dagster assets for basic PaECTER functionality
  - [ ] `paecter_embeddings_patents` → data/processed/paecter_embeddings_patents.parquet
  - [ ] `paecter_embeddings_awards` → data/processed/paecter_embeddings_awards.parquet
  - [ ] Include columns: document_id, text_source, embedding, model_name, computed_at
  - [ ] Add asset checks for embedding coverage thresholds
  - _Requirements: 1.1, 1.2_

- [ ] 1.5 Implement basic similarity computation
  - [ ] Create `paecter_award_patent_similarity` asset with cosine similarity computation
  - [ ] Support brute-force and optional FAISS backends for similarity search
  - [ ] Output similarity pairs with scores, ranks, and threshold filtering
  - [ ] Add quality checks for similarity score distributions
  - _Requirements: 2.1, 2.2_

## Phase 2: Bayesian MoE Framework Foundation

- [ ]* 2.1 Add Bayesian MoE configuration to config/base.yaml
  - [ ] bayesian_moe.enable: false (disabled by default)
  - [ ] bayesian_moe.uncertainty.ece_threshold: 0.1
  - [ ] bayesian_moe.uncertainty.confidence_threshold: 0.8
  - [ ] bayesian_moe.uncertainty.review_threshold: 0.3
  - [ ] bayesian_moe.calibration.method: "platt_scaling"
  - [ ] bayesian_moe.routing.inference_method: "variational"
  - _Requirements: 5.1, 6.1, 7.1_

- [ ]* 2.2 Implement core Bayesian router framework
  - [ ] Create abstract `BayesianRouter` base class with routing interface
  - [ ] Implement `RoutingDecision` dataclass with probabilities and uncertainty metrics
  - [ ] Add `UncertaintyMetrics` dataclass with entropy, ECE, and confidence intervals
  - [ ] Create routing decision logic with variational inference support
  - _Requirements: 5.1, 6.1, 7.1_

- [ ]* 2.3 Implement uncertainty quantification components
  - [ ] Create `UncertaintyHead` class with ECE computation and calibration
  - [ ] Implement epistemic and aleatoric uncertainty calculation methods
  - [ ] Add confidence score calibration using Platt scaling or temperature scaling
  - [ ] Create uncertainty-based flagging logic for human review cases
  - _Requirements: 5.1, 6.1, 7.1_

- [ ]* 2.4 Create LoRA expert pool management system
  - [ ] Implement `LoRAExpertPool` class for managing adapter loading/unloading
  - [ ] Add dynamic adapter switching based on routing decisions
  - [ ] Create adapter weight computation and output merging logic
  - [ ] Implement memory-efficient adapter storage and caching
  - _Requirements: 5.1, 6.1, 7.1_

## Phase 3: Stage 1 - Bayesian Classification Routing

- [ ]* 3.1 Implement Bayesian classification router
  - [ ] Create `BayesianClassificationRouter` class extending `BayesianRouter`
  - [ ] Implement document feature extraction for routing decisions
  - [ ] Add variational inference for expert selection probability distributions
  - [ ] Create technology domain expert definitions (biotech, AI, defense, energy)
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ]* 3.2 Create LoRA adapters for classification experts
  - [ ] Design LoRA adapter configurations for CET and CPC classification tasks
  - [ ] Implement adapter loading logic for domain-specific classification experts
  - [ ] Add base model integration with adapter switching capabilities
  - [ ] Create adapter training pipeline for domain specialization
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ]* 3.3 Implement classification routing Dagster asset
  - [ ] Create `bayesian_classification_routing` asset
  - [ ] Output classifications with uncertainty metrics to data/processed/bayesian_classifications.parquet
  - [ ] Include routing probabilities, confidence scores, and review flags
  - [ ] Add asset checks for classification quality and uncertainty calibration
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ]* 3.4 Add classification uncertainty validation
  - [ ] Implement ECE computation for classification confidence calibration
  - [ ] Add uncertainty-based quality gates that block downstream processing
  - [ ] Create classification performance monitoring and drift detection
  - [ ] Generate classification uncertainty baselines and alerts
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

## Phase 4: Stage 2 - Bayesian Similarity Routing

- [ ]* 4.1 Implement Bayesian similarity router
  - [ ] Create `BayesianSimilarityRouter` class with category-conditioned routing
  - [ ] Implement similarity expert selection based on document categories
  - [ ] Add probabilistic routing to intra-category, cross-category, and temporal experts
  - [ ] Create Bayesian model averaging for similarity score aggregation
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ]* 4.2 Create LoRA adapters for similarity experts
  - [ ] Design similarity computation LoRA adapters for different expert types
  - [ ] Implement intra-category similarity experts for domain-specific matching
  - [ ] Add cross-category similarity experts for technology transfer detection
  - [ ] Create temporal similarity experts for time-aware relationship modeling
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ]* 4.3 Implement similarity routing Dagster asset
  - [ ] Create `bayesian_similarity_routing` asset building on classification results
  - [ ] Output similarity scores with uncertainty to data/processed/bayesian_similarities.parquet
  - [ ] Include confidence intervals, routing decisions, and expert contributions
  - [ ] Add asset checks for similarity quality and uncertainty validation
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ]* 4.4 Add similarity uncertainty quantification
  - [ ] Implement confidence interval computation for similarity scores
  - [ ] Add uncertainty propagation from classification to similarity stages
  - [ ] Create similarity uncertainty validation and quality gates
  - [ ] Generate similarity performance baselines and regression detection
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

## Phase 5: Stage 3 - Bayesian Embedding Routing

- [ ]* 5.1 Implement Bayesian embedding router
  - [ ] Create `BayesianEmbeddingRouter` class with multi-stage informed routing
  - [ ] Implement routing based on classification and similarity analysis results
  - [ ] Add domain-specialized PaECTER expert selection logic
  - [ ] Create embedding generation uncertainty quantification
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ]* 5.2 Create LoRA adapters for embedding experts
  - [ ] Design domain-specific PaECTER LoRA adapters (biotech, AI, defense, energy)
  - [ ] Implement document type LoRA adapters (patents vs SBIR awards)
  - [ ] Add temporal LoRA adapters for different time periods
  - [ ] Create adapter fine-tuning pipeline for embedding specialization
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ]* 5.3 Implement embedding routing Dagster asset
  - [ ] Create `bayesian_embedding_routing` asset using classification and similarity inputs
  - [ ] Output specialized embeddings to data/processed/bayesian_embeddings.parquet
  - [ ] Include domain specialization metadata and quality scores
  - [ ] Add asset checks for embedding quality and uncertainty validation
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ]* 5.4 Add embedding uncertainty integration
  - [ ] Implement embedding quality confidence score computation
  - [ ] Add uncertainty propagation through the complete pipeline
  - [ ] Create end-to-end uncertainty validation and calibration checks
  - [ ] Generate embedding performance baselines and monitoring
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

## Phase 6: Neo4j Integration and System Compatibility

- [ ] 6.1 Implement Neo4j integration with uncertainty metadata
  - [ ] Create `neo4j_bayesian_similarity_edges` asset (optional, disabled by default)
  - [ ] Add SIMILAR_TO relationships with uncertainty scores and routing metadata
  - [ ] Include confidence intervals and expert routing information in edge properties
  - [ ] Implement uncertainty-based edge filtering and quality validation
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 6.2 Ensure system compatibility and additive implementation
  - [ ] Verify all Bayesian MoE assets are strictly additive to existing functionality
  - [ ] Implement feature flags to enable/disable Bayesian components independently
  - [ ] Add backward compatibility checks for existing data schemas and APIs
  - [ ] Create migration path documentation for enabling Bayesian features
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 6.3 Implement comprehensive quality gates and validation
  - [ ] Add uncertainty calibration quality gates across all pipeline stages
  - [ ] Implement ECE validation thresholds that block poor calibration
  - [ ] Create uncertainty-error correlation validation for system reliability
  - [ ] Add performance regression detection for Bayesian components
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

## Phase 7: Testing and Validation

- [ ] 7.1 Unit testing for Bayesian components
  - [ ] Test Bayesian router uncertainty computation and calibration methods
  - [ ] Test LoRA expert pool management and adapter switching logic
  - [ ] Test uncertainty head ECE computation and confidence calibration
  - [ ] Test routing decision logic and expert selection algorithms
  - _Requirements: All requirements_

- [ ] 7.2 Integration testing for end-to-end pipeline
  - [ ] Test complete Classification → Similarity → Embedding pipeline flow
  - [ ] Test uncertainty propagation across all three routing stages
  - [ ] Test quality gate enforcement and error handling with uncertainty
  - [ ] Test Neo4j integration with Bayesian uncertainty metadata
  - _Requirements: All requirements_

- [ ] 7.3 Uncertainty calibration validation testing
  - [ ] Test ECE computation on validation datasets across all stages
  - [ ] Test confidence interval coverage and uncertainty-error correlation
  - [ ] Test calibration drift detection and recalibration triggers
  - [ ] Test human review flagging accuracy and effectiveness
  - _Requirements: 5.1, 6.1, 7.1, 3.1_

- [ ] 7.4 Performance and scalability testing
  - [ ] Test LoRA adapter switching overhead and memory efficiency
  - [ ] Test Bayesian routing computational overhead vs accuracy gains
  - [ ] Test system scalability with large patent and award datasets
  - [ ] Test uncertainty computation performance and optimization
  - _Requirements: All requirements_

## Phase 8: Documentation and Deployment

- [ ] 8.1 Create comprehensive documentation
  - [ ] Document Bayesian MoE architecture and uncertainty quantification approach
  - [ ] Document LoRA adapter management and expert pool configuration
  - [ ] Document uncertainty calibration methods and quality validation
  - [ ] Document deployment and configuration for Bayesian features
  - _Requirements: All requirements_

- [ ] 8.2 Implement monitoring and observability
  - [ ] Add uncertainty quality monitoring and alerting systems
  - [ ] Create Bayesian routing performance dashboards and metrics
  - [ ] Implement calibration drift detection and automated recalibration
  - [ ] Add expert pool performance monitoring and adapter health checks
  - _Requirements: All requirements_

- [ ] 8.3 Deploy and validate in production
  - [ ] Deploy core PaECTER functionality with Bayesian features disabled
  - [ ] Gradually enable Bayesian classification routing with monitoring
  - [ ] Enable similarity and embedding routing with uncertainty validation
  - [ ] Monitor system performance and uncertainty calibration quality
  - _Requirements: All requirements_
