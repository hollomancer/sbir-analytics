# Implementation Tasks

**Note**: Unit tests for CET Pydantic models (CETArea, CETClassification, EvidenceStatement, CETAssessment, CompanyCETProfile) have been created in `tests/unit/ml/test_cet_models.py` with comprehensive validation coverage.

## Sprint Plan & Prioritization

The remaining work has been grouped into prioritized sprints to unblock downstream pieces (assets, classification, Neo4j integration) while keeping iterations small and testable. Each sprint includes estimated effort (hours), suggested owners, and the tasks (by number) from this file it intends to complete or unblock.

Sprint 0 — Setup & Infrastructure (COMPLETED)
- Goal: Ensure dependencies, project layout, and configuration plumbing are in place.
- Primary tasks: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
- Deliverables: `src/ml/` module scaffold, `config/cet/` directory, pytest fixtures.
- Estimate: 24 hours
- Owner: @conradhollomon (Platform/ML setup)
- Rationale: Small, high-impact setup that allows parallel development.
- Completed: All Sprint 0 tasks have been implemented and validated locally; corresponding checklist items in this document are checked.

Sprint 1 — Taxonomy, Config, and Dagster Asset Baseline (COMPLETED)
- Goal: Load and validate CET taxonomy, create Dagster asset skeletons, and persist taxonomy to processed storage.
- Primary tasks: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 7.1, 7.2, 7.3, 7.4, 7.5, 21.1
- Deliverables:
  - `src/ml/config/taxonomy_loader.py` (TaxonomyLoader with Pydantic validation and completeness checks)
  - `src/assets/cet_assets.py` with `cet_taxonomy` asset (import-safe; parquet → JSON fallback)
  - `data/processed/cet_taxonomy.parquet` (or NDJSON fallback) produced in CI/dev runs
  - Documentation in `config/cet/README.md`
  - CI step to run taxonomy completeness checks and upload the checks artifact
- Estimate: 80 hours
- Owner: Data Engineer (owner: @data-engineer), Co-owner: @conradhollomon
- Rationale: Taxonomy is a dependency for model metadata, Neo4j loaders, and assets; implement and test early.
- Completed: Sprint 1 taxonomy tasks and their automated checks have been implemented and validated locally (unit tests passed) and wired into CI to run on PRs/changes to taxonomy files.

Sprint 1 — Checklist (current run tasks)
- [x] 2.1 Port `config/taxonomy.yaml` from sbir-cet-classifier (21 CET categories) (owner: ml-engineer)
- [x] 2.2 Port `config/classification.yaml` from sbir-cet-classifier (ML hyperparameters) (owner: ml-engineer)
- [x] 2.3 Create configuration loader in `src/ml/config/taxonomy_loader.py` (owner: ml-engineer)
- [x] 2.4 Add CET configuration schema validation (Pydantic models) (owner: ml-engineer)
- [x] 2.5 Add taxonomy versioning support (NSTC-2025Q1, etc.) (owner: ml-engineer)
- [x] 2.6 Document CET taxonomy structure in `config/cet/README.md` (owner: ml-engineer)
- [x] 7.1 Create `cet_taxonomy` asset in `src/assets/cet_assets.py` (owner: data-engineer)
- [x] 7.2 Load taxonomy from `config/cet/taxonomy.yaml` (owner: data-engineer)
- [x] 7.3 Validate taxonomy schema (required fields, unique IDs) (owner: ml-engineer)
- [x] 7.4 Add asset checks for taxonomy completeness (owner: data-engineer)
- [x] 7.5 Output taxonomy to `data/processed/cet_taxonomy.parquet` (or NDJSON fallback) (owner: data-engineer)
- [x] 21.1 Document CET taxonomy structure in `config/cet/README.md` (owner: ml-engineer)
- [x] CI: Run taxonomy completeness checks and upload artifact (`.github/workflows/ci.yml` updated) (est: 1h, owner: infra)

Notes:
- Sprint 0 items are marked completed above and their original checklist entries remain checked in the main task list.
- Sprint 1 taxonomy work has been completed for the loader, Dagster asset creation, README, and automated completeness checks. Unit tests for the taxonomy asset were executed locally and passed (2 tests). Implementation details completed in this run:
  - `src/ml/config/taxonomy_loader.py`: added `TaxonomyLoader` with Pydantic validation, `validate_taxonomy_completeness()` returning structured metrics, and helpers for checks JSON output.
  - `src/assets/cet_assets.py`: implemented the `cet_taxonomy` asset that:
    - Loads taxonomy via `TaxonomyLoader`
    - Produces a parquet artifact when parquet engine available or NDJSON fallback when not
    - Writes a companion checks JSON for CI / asset verification
    - Emits structured asset metadata and is import-safe when `dagster` is missing (small stubs used)
  - `src/ml/config/taxonomy_checks.py`: CLI wrapper to run taxonomy checks and optionally fail on issues (used by CI).
  - `tests/unit/ml/test_taxonomy_asset.py`: unit tests validating loader, artifact output, and checks JSON.
  - `src/models/__init__.py` and `src/assets/__init__.py`: switched to lazy import patterns to avoid import-time failures when optional heavy dependencies (dagster, neo4j, duckdb, pyarrow) are not present during test collection.
  - CI updated: `.github/workflows/ci.yml` updated to run taxonomy checks, upload artifact, and evaluate checks on PRs (comment + fail behavior when issues detected).
- Remaining follow-ups:
  - Formal registration of Dagster assets in any central manifest (if required by the repo's Dagster configuration) — tracked as a follow-up.
  - Optional: add a path-filtered workflow that runs taxonomy-only checks when `config/cet/**` changes to reduce noise (recommended; not yet added).
  - Optional: add a regression unit test that asserts the checks CLI exits with non-zero for purposely invalid taxonomy (recommended).

Sprint 2 — Evidence Extraction + Models Core (3 weeks, ~120h)
- Goal: Implement the EvidenceExtractor and the core CET classifier pipeline (TF-IDF vectorizer, classifier, calibration) with batch scoring capability.
- Primary tasks: 4.1–4.8, 5.1–5.7, 6.2, 6.3, 6.5, 6.6, 18.1, 18.2
- Deliverables:
  - `src/ml/features/evidence_extractor.py` (spaCy sentence segmentation, keyword matching, excerpting)
  - `src/ml/models/cet_classifier.py` (TF-IDF pipeline, save/load, metadata)
  - Training workflow `src/ml/models/trainer.py` (skeleton for training / calibration)
  - Unit tests for classifier and extractor (basic coverage)
- Estimate: 120 hours
- Owner: ML Engineer (owner: @ml-engineer), Co-owner: @conradhollomon
- Rationale: Provides core functionality for classifying awards and extracting evidence; enables offline evaluation.

Sprint 3 — Batch Classification Assets & Persistence (2 weeks, ~80h)
- Goal: Create Dagster assets to run batch classification of awards, extract evidence, and persist results for downstream aggregation and Neo4j ingestion.
- Primary tasks: 8.1–8.10, 6.4, 6.7, 18.1 (tests)
- Deliverables:
  - `cet_award_classifications` asset in `src/assets/cet_assets.py`
  - Batch classification implementation (1000 awards/batch), evidence extraction per award
  - Output: `data/processed/cet_award_classifications.parquet`
  - Asset checks: classification success rate, high confidence rate, evidence coverage
- Estimate: 80 hours
- Owner: Data Engineer (owner: @data-engineer), ML co-owner for model loading

Sprint 4 — Company Aggregation & Neo4j Model (3 weeks, ~120h)
- Goal: Aggregate award-level CETs to company profiles and implement Neo4j loaders for CET nodes & relationships.
- Primary tasks: 9.1–9.7, 12.1–12.7, 13.1–13.6, 14.1–14.5, 18.7, 18.8
- Deliverables:
  - `src/transformers/company_cet_aggregator.py`
  - `src/loaders/cet_loader.py` for CETArea nodes and Neo4j assets for relationships
  - Neo4j assets: `neo4j_cet_areas`, `neo4j_award_cet_relationships`, `neo4j_company_cet_relationships`
  - Unit tests for aggregation and Neo4j loader logic (mocks for Neo4j)
- Estimate: 120 hours
- Owner: Data Engineer + Graph Engineer (owner: @graph-engineer), Co-owner: @conradhollomon
- Rationale: Critical for analytics and portfolio queries; needs careful batching and idempotent writes.

Sprint 5 — Patent Integration & USPTO (2 weeks, ~80h)
- Goal: Add patent classification, integrate USPTO AI dataset loader, and add validation hooks.
- Primary tasks: 10.1–10.6, 11.1–11.8, 15.1–15.5
- Deliverables:
  - `src/ml/models/patent_classifier.py`
  - `src/ml/data/uspto_ai_loader.py` with chunked streaming and SQLite cache
  - Assets for patent CET classifications and Neo4j patent relationships
- Estimate: 80 hours
- Owner: ML Engineer + Data Engineer (owner: @ml-engineer), Co-owner: @data-engineer

Sprint 6 — Evaluation, Validation, Tests, and Docs (2–3 weeks, ~120h)
- Goal: Implement evaluation tooling, human sampling integration, performance baselining, and finish unit/integration tests and documentation.
- Primary tasks: 17.1–17.7, 18.3–18.8, 19.1–19.7, 20.1–20.6, 21.2–21.7
- Deliverables:
  - `src/ml/evaluation/cet_evaluator.py` and evaluation reports (charts + metrics)
  - Integration tests for pipeline (sample dataset)
  - E2E pipeline validation on dev
  - Complete docs: ML architecture, evidence extraction, Neo4j schema, deployment checklist
- Estimate: 120 hours
- Owner: @conradhollomon (Lead), with cross-functional reviewers (Data, ML, QA)

Backlog / Ongoing Optimization & Deployment (as needed)
- Performance tuning, CI/CD integration, production rollout checklist, monitoring and alerts (22.*, 23.*, 24.*).
- These items will be scheduled after Sprint 6 based on evaluation results and stakeholder review.

## 1. Project Setup & Dependencies

- [x] 1.1 Add scikit-learn>=1.4.0 to pyproject.toml dependencies
- [x] 1.2 Add spacy>=3.7.0 to pyproject.toml dependencies
- [x] 1.3 Install spaCy English model: python -m spacy download en_core_web_sm
- [x] 1.4 Create src/ml/ module structure (models/, features/, evaluation/)
- [x] 1.5 Create config/cet/ directory for CET configuration files
- [x] 1.6 Add pytest fixtures for CET classification tests

## 2. Configuration Files

- [x] 2.1 Port config/taxonomy.yaml from sbir-cet-classifier (21 CET categories)
- [x] 2.2 Port config/classification.yaml from sbir-cet-classifier (ML hyperparameters)
- [x] 2.3 Create configuration loader in src/ml/config/taxonomy_loader.py
- [x] 2.4 Add CET configuration schema validation (Pydantic models)
- [x] 2.5 Add taxonomy versioning support (NSTC-2025Q1, etc.)
- [x] 2.6 Document CET taxonomy structure in config/cet/README.md

## 3. Pydantic Data Models

- [x] 3.1 Create CETArea model in src/models/cet_models.py
- [x] 3.2 Create CETClassification model (score, classification, primary/supporting)
- [x] 3.3 Create EvidenceStatement model (excerpt, source_location, rationale_tag)
- [x] 3.4 Create CETAssessment model (combines classification + evidence)
- [x] 3.5 Add CET-specific validation rules (score 0-100, classification in High/Medium/Low)
- [x] 3.6 Add type hints for all CET models

## 4. ML Classification Module - Core Model

- [x] 4.1 Port ApplicabilityModel from sbir-cet-classifier to src/ml/models/cet_classifier.py
- [x] 4.2 Port CETAwareTfidfVectorizer with keyword boosting
- [x] 4.3 Implement TF-IDF pipeline (vectorizer → feature selection → classifier → calibration)
- [x] 4.4 Add balanced class weights for handling imbalanced CET categories
- [x] 4.5 Implement multi-threshold scoring (High: ≥70, Medium: 40-69, Low: <40)
- [x] 4.6 Add batch classification method for efficient processing
- [x] 4.7 Save/load trained model (pickle or joblib)
- [x] 4.8 Add model metadata (version, training date, taxonomy version)

## 5. Evidence Extraction

- [x] 5.1 Create EvidenceExtractor in src/ml/features/evidence_extractor.py
- [x] 5.2 Implement spaCy-based sentence segmentation
- [x] 5.3 Add CET keyword matching within sentences
- [x] 5.4 Implement 50-word excerpt truncation
- [x] 5.5 Add source location tracking (abstract, keywords, solicitation)
- [x] 5.6 Generate rationale tags (e.g., "Contains: machine learning, neural networks")
- [x] 5.7 Add evidence ranking (select top 3 most relevant sentences)

## 6. Training Data & Model Training

- [x] 6.1 Port bootstrap training data from sbir-cet-classifier (1000+ annotated awards)
- [x] 6.2 Create TrainingExample model for labeled data
- [x] 6.3 Implement model training workflow in src/ml/models/trainer.py
- [x] 6.4 Add cross-validation for hyperparameter tuning
- [x] 6.5 Implement probability calibration (sigmoid, 3-fold CV)
- [x] 6.6 Save trained model to artifacts/models/cet_classifier_v1.pkl
- [x] 6.7 Generate training metrics report (accuracy, precision, recall, F1)

Notes (section 6 implementation):
- Implemented `AwardTrainingLoader` in `src/ml/data/award_training_loader.py` to load CSV/NDJSON into `TrainingDataset`/`TrainingExample` with label/keyword parsing and deterministic training text.
- Added Dagster asset `cet_award_training_dataset` in `src/assets/cet_assets.py` to persist the labeled training data to `data/processed/cet_award_training.parquet` (with NDJSON fallback) and write a checks JSON at `data/processed/cet_award_training.checks.json`.

## 7. Dagster Assets - CET Taxonomy

- [x] 7.1 Create cet_taxonomy asset in src/assets/cet_assets.py
- [x] 7.2 Load taxonomy from config/cet/taxonomy.yaml
- [x] 7.3 Validate taxonomy schema (required fields, unique IDs)
- [x] 7.4 Add asset checks for taxonomy completeness
- [x] 7.5 Output taxonomy to data/processed/cet_taxonomy.parquet (or NDJSON fallback)

## 8. Dagster Assets - Award Classification

- [x] 8.1 Create `cet_award_classifications` asset (depends on `enriched_sbir_awards`, `cet_taxonomy`)
- [x] 8.2 Load trained CET classifier model
- [x] 8.3 Batch classify awards (configurable batch size; default 1000)
- [x] 8.4 Extract evidence for each classification using `EvidenceExtractor`
- [x] 8.5 Calculate primary CET area + up to 3 supporting areas
- [x] 8.6 Add asset checks for classification success rate (computed and emitted; target: ≥95%)
- [x] 8.7 Add asset checks for high confidence rate (computed and emitted; target: ≥60%)
- [x] 8.8 Add asset checks for evidence coverage (computed and emitted; target: ≥80%)
- [x] 8.9 Output classifications to `data/processed/cet_award_classifications.parquet` (or NDJSON fallback)
- [x] 8.10 Log classification metrics (throughput, latency, confidence distribution)

Notes (section 8 implementation):
- Implemented `cet_award_classifications` asset in `src/assets/cet_assets.py`.
  - Loads taxonomy via `TaxonomyLoader` and classification config.
  - Attempts to load trained model from `artifacts/models/cet_classifier_v1.pkl`; when missing, writes a schema-compatible placeholder and checks JSON.
  - Performs batch classification via `ApplicabilityModel.classify_batch`.
  - Extracts evidence per CET using `EvidenceExtractor` and attaches up to configured number of evidence excerpts.
  - Persists results to `data/processed/cet_award_classifications.parquet` with the same parquet → NDJSON fallback pattern used by the taxonomy asset.
  - Writes companion checks JSON at `data/processed/cet_award_classifications.checks.json` summarizing:
    - num_awards, num_classified, high_conf_count, high_conf_rate, evidence_coverage_rate, model_path.
  - Emits asset metadata including output path, rows, taxonomy/model version, and checks path.
- Files added/modified (high-level):
  - `src/assets/cet_assets.py` — added `cet_award_classifications` asset implementation.
  - Reused components: `src/ml/models/cet_classifier.py` (ApplicabilityModel) and `src/ml/features/evidence_extractor.py` (EvidenceExtractor).
- Behavior notes:
  - The asset is import-safe when optional dependencies are missing: it uses local stubs and JSON fallbacks so CI can run in lightweight runners.
  - Where the trained model or enriched awards data are not present in the environment, the asset writes a predictable placeholder output and a checks JSON that CI can evaluate and surface to PR authors.

## 9. Company CET Aggregation

- [x] 9.1 Create CompanyCETAggregator in src/transformers/company_cet_aggregator.py
- [x] 9.2 Aggregate CET scores from all awards per company
- [x] 9.3 Calculate dominant CET area (highest average score)
- [x] 9.4 Calculate CET specialization score (concentration in top CET)
- [x] 9.5 Track CET evolution over time (Phase I → Phase II → Phase III)
- [x] 9.6 Create cet_company_profiles asset (depends on cet_award_classifications)
- [x] 9.7 Output company profiles to data/processed/cet_company_profiles.parquet

## 10. Patent CET Classification

- [x] 10.1 Create PatentCETClassifier in src/ml/models/patent_classifier.py
- [x] 10.2 Classify patents based on title + assignee entity type
- [x] 10.3 Add patent-specific feature engineering (patent title structure)
- [x] 10.4 Create cet_patent_classifications asset (depends on transformed_patents)

## 11. USPTO AI Dataset Integration

- [x] 11.1 Add loader for USPTO AI dataset (streaming + chunking) — Implemented via `src/extractors/uspto_ai_extractor.py` and asset `src/assets/uspto_ai_extraction_assets.py::uspto_ai_extract_to_duckdb`
- [x] 11.2 Add deduplication & incremental checkpointing — Implemented via extractor resume checkpoints (`data/cache/uspto_ai_checkpoints`) and asset `src/assets/uspto_ai_extraction_assets.py::uspto_ai_deduplicate`
- [x] 11.3 Add sampling pipeline for human evaluation — Implemented via asset `src/assets/uspto_ai_extraction_assets.py::uspto_ai_human_sample_extraction`
- [x] 11.4 Add patent-specific extractor logic — Implemented grant id normalization and score coercion in `src/extractors/uspto_ai_extractor.py` (canonical `grant_doc_num`, numeric score fields)

## 12. Neo4j CET Graph Model - Nodes

- [x] 12.1 Create CETArea node schema — Implemented via `src/loaders/cet_loader.py` (CETArea schema) and asset `src/assets/cet_neo4j_loading_assets.py::neo4j_cetarea_nodes`
- [x] 12.2 Add uniqueness constraints for CETArea — Implemented in `src/loaders/cet_loader.py::CETLoader.create_constraints` (unique on `CETArea.cet_id`)
- [x] 12.3 Add CETArea properties (id, name, keywords, taxonomy_version) — Implemented in `src/loaders/cet_loader.py::CETLoader.load_cet_areas` (properties set from taxonomy output)
- [x] 12.4 Create Company node CET enrichment properties — Implemented via asset `src/assets/cet_neo4j_loading_assets.py::neo4j_company_cet_enrichment` and `src/loaders/cet_loader.py::CETLoader.upsert_company_cet_enrichment`
- [x] 12.5 Create Award node CET enrichment properties — Implemented via asset `src/assets/cet_neo4j_loading_assets.py::neo4j_award_cet_enrichment` and `src/loaders/cet_loader.py::CETLoader.upsert_award_cet_enrichment`
- [x] 12.6 Add batching + idempotent merges — Implemented via `src/loaders/neo4j_client.py::Neo4jClient.batch_upsert_nodes` used by `CETLoader`
- [x] 12.7 Unit tests (mocked Neo4j)

## 13. Neo4j CET Graph Model - Award Relationships

- [x] 13.1 Create Award -> CETArea relationship schema
- [x] 13.2 Add relationship properties (score, primary/supporting, rationale)
- [x] 13.3 Ensure idempotent MERGE semantics
- [x] 13.4 Unit tests (mocked Neo4j)

## 14. Neo4j CET Graph Model - Company Relationships

- [ ] 14.1 Create Company -> CETArea relationship schema
- [ ] 14.2 Add aggregation methods
- [ ] 14.3 Unit tests (mocked Neo4j)

## 15. CET Portfolio Analytics

- [ ] 15.1 Implement CET coverage dashboards
- [ ] 15.2 Implement CET specialization metrics
- [ ] 15.3 Add alerts for coverage regressions

## 16. CET Portfolio Analytics - Continued

- [ ] 16.1 Scale aggregation for large datasets (sharding)
- [ ] 16.2 Performance baselining

## 17. Evaluation & Validation

- [ ] 17.1 Human sampling and annotation harness
- [ ] 17.2 Inter-annotator agreement tracking
- [ ] 17.3 Model drift detection

## 18. Unit Testing

- [x] 18.1 Unit tests for taxonomy asset and loader (`tests/unit/ml/test_taxonomy_asset.py`)
- [x] 18.2 Unit tests for EvidenceExtractor and CET models
- [x] 18.3 Unit tests for TaxonomyLoader (YAML parsing, validation)
- [ ] 18.4 Unit tests for CompanyCETAggregator (aggregation logic)
- [ ] 18.5 Integration tests for classifier & trainer (larger dataset)
- [ ] 18.6 Add pytest markers for slow/e2e tests
- [ ] 18.7 Add Neo4j smoke tests (CI job)

## 19. Integration Testing

- [ ] 19.1 CI job to run a sample pipeline end-to-end on a small dataset
- [ ] 19.2 Add artifact retention policy for CI sample datasets

## 20. End-to-End Testing

- [ ] 20.1 E2E pipeline on dev stack
- [ ] 20.2 Load testing for batch classification assets

## 21. Documentation

- [x] 21.1 Document CET taxonomy structure in config/cet/README.md
- [ ] 21.2 Document ML model architecture and hyperparameters in docs/ml/cet_classifier.md

## 22. Performance Optimization (if needed)

- [ ] 22.1 Baseline TF-IDF & inference throughput
- [ ] 22.2 Implement batching & mem-optimizations

## 23. Configuration & Deployment

- [ ] 23.1 Add production config examples
- [ ] 23.2 Add deployment checklist for Dagster assets

## 24. Deployment & Validation

- [ ] 24.1 Onboard to staging environment
- [ ] 24.2 Run validation & human sampling on staging

---
Change log (Sprint 1 taxonomy work)
- Completed: implemented taxonomy loader, Dagster-compatible taxonomy asset, completeness checks CLI, unit tests for taxonomy asset, CI wiring for taxonomy checks.
- Files added/modified (high-level):
  - `src/ml/config/taxonomy_loader.py` — completeness checks + metadata helpers
  - `src/assets/cet_assets.py` — `cet_taxonomy` asset, parquet/NDJSON fallback, checks JSON writer
  - `src/ml/config/taxonomy_checks.py` — CLI to run taxonomy completeness checks (used by CI)
  - `tests/unit/ml/test_taxonomy_asset.py` — unit tests for loader and asset behaviors
  - `src/models/__init__.py` and `src/assets/__init__.py` — lazy import patterns to avoid import-time failures
  - `.github/workflows/ci.yml` — updated to run taxonomy checks and upload checks artifact
  - `openspec/changes/add-cet-classification/tasks.md` — this file updated to mark Sprint 1 taxonomy items completed
- Notes:
  - The taxonomy asset writes a companion checks JSON (human-readable) that CI evaluates; PRs with taxonomy issues receive a comment and the job fails to provide immediate feedback.
  - The implementation is import-safe when optional dependencies (dagster, pyarrow, duckdb) are not present; unit tests use NDJSON fallback so CI can run in lightweight runners.
