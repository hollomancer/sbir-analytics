# Implementation Tasks

## 1. Project Setup & Dependencies

- [ ] 1.1 Promote rapidfuzz to main dependencies (needed for vendor name matching)
- [x] 1.2 Create src/transition/ module structure (detection/, features/, config/)
  - Notes: Implemented `src/transition/` package with scaffolds:
    - `src/transition/detection/` (detection pipeline stubs)
    - `src/transition/features/` (vendor resolver and feature extractors)
    - `src/transition/config/` (configuration placeholders)
    - Added `src/transition/__init__.py` and initial `VendorResolver` implementation in `src/transition/features/vendor_resolver.py`.
    - Basic unit test and fixtures scaffold added to accelerate verification (see tests/unit/test_vendor_resolver.py).
- [x] 1.3 Add pytest fixtures for transition detection tests
  - Notes: Added pytest fixture `sample_vendors` and an initial unit test suite for `VendorResolver` at `tests/unit/test_vendor_resolver.py`. These provide the initial fixtures and tests for vendor name/identifier matching and will be extended for broader transition detection fixtures.
- [ ] 1.4 Verify DuckDB availability for large contract dataset analytics

## 2. Configuration Files

- [ ] 2.1 Create config/transition/detection.yaml (scoring weights, thresholds)
- [ ] 2.2 Create config/transition/presets.yaml (high-precision, broad-discovery, balanced)
- [ ] 2.3 Add timing window configuration (default: 0-24 months)
- [ ] 2.4 Add vendor matching configuration (fuzzy threshold, identifier priority)
- [ ] 2.5 Document transition configuration in config/transition/README.md

## 3. Pydantic Data Models

- [ ] 3.1 Create Transition model in src/models/transition_models.py
- [ ] 3.2 Create EvidenceBundle model (comprehensive audit trail)
- [ ] 3.3 Create TransitionSignals models (Agency, Timing, Competition, Patent, CET)
- [ ] 3.4 Create FederalContract model in src/models/contract_models.py
- [ ] 3.5 Create VendorMatch model (cross-walk tracking)
- [ ] 3.6 Create TransitionProfile model (company-level aggregation)
- [ ] 3.7 Add validation rules for transition models

## 4. Vendor Resolution Module

- [ ] 4.1 Create VendorResolver in src/transition/features/vendor_resolver.py
- [ ] 4.2 Implement UEI exact matching (primary method, confidence: 0.99)
- [ ] 4.3 Implement CAGE code matching (defense-specific, confidence: 0.95)
- [ ] 4.4 Implement DUNS number matching (legacy, confidence: 0.90)
- [ ] 4.5 Implement fuzzy name matching with rapidfuzz (threshold ≥0.90)
- [ ] 4.6 Create vendor cross-walk table (mapping all identifiers)
- [ ] 4.7 Handle company acquisitions and name changes
- [ ] 4.8 Add vendor match confidence tracking

## 5. Federal Contracts Ingestion

- [ ] 5.1 Create ContractExtractor in src/extractors/contract_extractor.py
- [ ] 5.2 Integrate with USAspending.gov CSV data
- [ ] 5.3 Implement chunked processing (100K contracts/batch) for 14GB+ dataset
- [ ] 5.4 Parse competition type (sole source, limited, full and open)
- [ ] 5.5 Extract vendor identifiers (UEI, CAGE, DUNS)
- [ ] 5.6 Handle parent-child contract relationships (IDV, IDIQ, BPA)
- [ ] 5.7 Create contracts_ingestion asset (depends on USAspending data)

## 6. Transition Scoring Algorithm

- [ ] 6.1 Create TransitionScorer in src/transition/detection/scoring.py
- [ ] 6.2 Implement base score calculation (0.15 baseline)
- [ ] 6.3 Implement agency continuity scoring (same agency: +0.25, cross-service: +0.125)
- [ ] 6.4 Implement timing proximity scoring (0-3mo: 1.0, 3-12mo: 0.75, 12-24mo: 0.5)
- [ ] 6.5 Implement competition type scoring (sole source: +0.20, limited: +0.10)
- [ ] 6.6 Implement patent signal scoring (has patent: +0.05, pre-contract: +0.03, topic match: +0.02)
- [ ] 6.7 Implement CET area alignment scoring (same CET: +0.05)
- [ ] 6.8 Implement text similarity scoring (optional, configurable weight)
- [ ] 6.9 Add configurable weights via YAML
- [ ] 6.10 Add confidence classification (High: ≥0.85, Likely: ≥0.65, Possible: <0.65)

## 7. Evidence Bundle Generation

- [ ] 7.1 Create EvidenceGenerator in src/transition/detection/evidence.py
- [ ] 7.2 Generate agency signals evidence (same agency, department, score contribution)
- [ ] 7.3 Generate timing signals evidence (days after completion, within window)
- [ ] 7.4 Generate competition signals evidence (type, score contribution)
- [ ] 7.5 Generate patent signals evidence (count, filing dates, topic similarity)
- [ ] 7.6 Generate CET signals evidence (technology area alignment)
- [ ] 7.7 Generate vendor match evidence (method, confidence, matched identifier)
- [ ] 7.8 Generate contract details evidence (PIID, agency, amount, start date)
- [ ] 7.9 Serialize evidence bundle to JSON (store on Neo4j relationships)
- [ ] 7.10 Add evidence bundle validation (completeness, consistency)

## 8. Transition Detection Pipeline

- [ ] 8.1 Create TransitionDetector in src/transition/detection/detector.py
- [ ] 8.2 Implement candidate selection (all contracts for vendors with SBIR awards)
- [ ] 8.3 Implement vendor matching (cross-walk resolution)
- [ ] 8.4 Implement timing window filtering (0-24 months after award completion)
- [ ] 8.5 Implement signal extraction (agency, competition, timing, patent, CET)
- [ ] 8.6 Implement likelihood scoring (composite score from all signals)
- [ ] 8.7 Implement confidence classification (threshold-based)
- [ ] 8.8 Implement evidence bundle generation
- [ ] 8.9 Add batch processing for efficiency (1000 awards/batch)
- [ ] 8.10 Add progress logging and metrics

## 9. Patent Signal Extraction

- [ ] 9.1 Create PatentSignalExtractor in src/transition/features/patent_analyzer.py
- [ ] 9.2 Find patents filed between SBIR completion and contract start
- [ ] 9.3 Calculate patent-contract timing (filed before contract: true/false)
- [ ] 9.4 Calculate patent topic similarity using TF-IDF (threshold ≥0.7)
- [ ] 9.5 Calculate average patent filing lag (days after SBIR completion)
- [ ] 9.6 Identify patent assignees (detect technology transfer if different from SBIR recipient)
- [ ] 9.7 Generate patent signal scores
- [ ] 9.8 Handle awards with no patents gracefully

## 10. CET Integration

- [ ] 10.1 Create CETSignalExtractor in src/transition/features/cet_analyzer.py
- [ ] 10.2 Extract award CET classification (from CET classification module)
- [ ] 10.3 Infer contract CET area from description (keyword matching or ML)
- [ ] 10.4 Calculate CET area alignment (award CET == contract CET)
- [ ] 10.5 Generate CET signal scores
- [ ] 10.6 Handle awards without CET classification (optional signal)

## 11. Dagster Assets - Transition Detection

- [ ] 11.1 Create transition_detections asset (depends on awards, contracts, patents)
- [ ] 11.2 Run transition detection pipeline for all awards
- [ ] 11.3 Generate transition detections with scores and evidence
- [ ] 11.4 Add asset checks for detection success rate (≥99%)
- [ ] 11.5 Add asset checks for vendor match rate (target: ≥90%)
- [ ] 11.6 Output detections to data/processed/transition_detections.parquet
- [ ] 11.7 Log detection metrics (total detections, high-confidence count, avg score)

## 12. Dual-Perspective Analytics

- [ ] 12.1 Create TransitionAnalytics in src/transition/analysis/analytics.py
- [ ] 12.2 Calculate award-level transition rate (transitioned awards / total awards)
- [ ] 12.3 Calculate company-level transition rate (companies with transitions / total companies)
- [ ] 12.4 Calculate Phase I vs Phase II effectiveness
- [ ] 12.5 Calculate transition rates by agency
- [ ] 12.6 Calculate transition rates by CET area (NEW)
- [ ] 12.7 Calculate avg time to transition by CET area (NEW)
- [ ] 12.8 Calculate patent-backed transition rates by CET area (NEW)
- [ ] 12.9 Create transition_analytics asset
- [ ] 12.10 Generate executive summary reports

## 13. Neo4j Graph Model - Transition Nodes

- [ ] 13.1 Create TransitionLoader in src/loaders/transition_loader.py
- [ ] 13.2 Create Transition node schema (transition_id, detection_date, likelihood_score, confidence)
- [ ] 13.3 Load transition detections as Transition nodes
- [ ] 13.4 Create index on Transition.transition_id
- [ ] 13.5 Create neo4j_transitions asset
- [ ] 13.6 Add asset checks for transition node count

## 14. Neo4j Graph Model - Transition Relationships

- [ ] 14.1 Create TRANSITIONED_TO relationships (Award → Transition)
- [ ] 14.2 Store evidence bundle as JSON on TRANSITIONED_TO relationship
- [ ] 14.3 Store likelihood_score, confidence, detection_date on relationship
- [ ] 14.4 Create RESULTED_IN relationships (Transition → Contract)
- [ ] 14.5 Create ENABLED_BY relationships (Transition → Patent) for patent-backed transitions
- [ ] 14.6 Create INVOLVES_TECHNOLOGY relationships (Transition → CETArea)
- [ ] 14.7 Batch write relationships (1000/transaction)
- [ ] 14.8 Create neo4j_transition_relationships asset

## 15. Neo4j Graph Model - Company Transition Profiles

- [ ] 15.1 Create TransitionProfile nodes (company-level aggregation)
- [ ] 15.2 Calculate total_awards, total_transitions, success_rate per company
- [ ] 15.3 Calculate avg_likelihood_score, avg_time_to_transition
- [ ] 15.4 Create ACHIEVED relationships (Company → TransitionProfile)
- [ ] 15.5 Create neo4j_transition_profiles asset

## 16. Transition Pathway Queries

- [ ] 16.1 Implement query: Award → Transition → Contract
- [ ] 16.2 Implement query: Award → Patent → Transition → Contract
- [ ] 16.3 Implement query: Award → CET → Transition (technology-specific)
- [ ] 16.4 Implement query: Company → TransitionProfile (company success)
- [ ] 16.5 Implement query: Transition rate by CET area
- [ ] 16.6 Implement query: Patent-backed transition rate by CET area
- [ ] 16.7 Document queries in docs/queries/transition_queries.md

## 17. Performance Optimization

- [ ] 17.1 Use DuckDB for large contract dataset analytics (6.7M+ contracts)
- [ ] 17.2 Implement vendor-based contract filtering (only load contracts for SBIR vendors)
- [ ] 17.3 Optimize vendor cross-walk with indexed lookups
- [ ] 17.4 Parallelize detection across Dagster workers (if needed)
- [ ] 17.5 Cache vendor resolutions to avoid redundant matching
- [ ] 17.6 Profile detection performance (target: ≥10K detections/minute)

## 18. Evaluation & Validation

- [ ] 18.1 Create TransitionEvaluator in src/transition/evaluation/evaluator.py
- [ ] 18.2 Collect known Phase III awards as ground truth
- [ ] 18.3 Calculate precision (correct detections / total detections)
- [ ] 18.4 Calculate recall (detected Phase III / total Phase III)
- [ ] 18.5 Calculate F1 score
- [ ] 18.6 Evaluate by confidence band (High vs Likely vs Possible)
- [ ] 18.7 Generate confusion matrix
- [ ] 18.8 Identify false positives for algorithm tuning
- [ ] 18.9 Generate evaluation report with recommendations

## 19. Unit Testing

- [ ] 19.1 Unit tests for VendorResolver (UEI, CAGE, DUNS, fuzzy matching)
- [ ] 19.2 Unit tests for TransitionScorer (all signal types, weight combinations)
- [ ] 19.3 Unit tests for EvidenceGenerator (bundle completeness, serialization)
- [ ] 19.4 Unit tests for PatentSignalExtractor (timing, similarity, assignees)
- [ ] 19.5 Unit tests for CETSignalExtractor (area alignment, scoring)
- [ ] 19.6 Unit tests for TransitionDetector (end-to-end detection logic)
- [ ] 19.7 Unit tests for TransitionAnalytics (dual-perspective calculations)
- [ ] 19.8 Unit tests for TransitionLoader (Neo4j node/relationship creation)

## 20. Integration Testing

- [ ] 20.1 Integration test: Full detection pipeline (awards + contracts → detections)
- [ ] 20.2 Integration test: Vendor resolution with cross-walk
- [ ] 20.3 Integration test: Patent-backed transition detection
- [ ] 20.4 Integration test: CET area transition analytics
- [ ] 20.5 Integration test: Dual-perspective analytics (award + company levels)
- [ ] 20.6 Integration test: Neo4j graph creation and queries
- [ ] 20.7 Test with sample dataset (1000 awards, 5000 contracts, 500 patents)
- [ ] 20.8 Validate data quality metrics meet targets

## 21. End-to-End Testing

- [ ] 21.1 E2E test: Dagster pipeline materialization (all transition assets)
- [ ] 21.2 E2E test: Full FY2020-2024 detection (252K awards)
- [ ] 21.3 E2E test: Neo4j graph queries for transition pathways
- [ ] 21.4 E2E test: CET area effectiveness analysis
- [ ] 21.5 Validate performance metrics (throughput ≥10K detections/min)
- [ ] 21.6 Validate quality metrics (precision ≥85%, recall ≥70%)

## 22. Documentation

- [ ] 22.1 Document transition detection algorithm in docs/transition/detection_algorithm.md
- [ ] 22.2 Document scoring weights and thresholds in docs/transition/scoring_guide.md
- [ ] 22.3 Document vendor resolution logic in docs/transition/vendor_matching.md
- [ ] 22.4 Document evidence bundle structure in docs/transition/evidence_bundles.md
- [ ] 22.5 Document Neo4j transition graph schema in docs/schemas/transition-graph-schema.md
- [ ] 22.6 Document CET integration in docs/transition/cet_integration.md
- [ ] 22.7 Create data dictionary for transition fields
- [ ] 22.8 Add transition detection section to main README.md

## 23. Configuration & Deployment

- [ ] 23.1 Add transition configuration to config/base.yaml (enable/disable features)
- [ ] 23.2 Add environment-specific configuration (dev/staging/prod)
- [ ] 23.3 Create deployment checklist for transition module
- [ ] 23.4 Test configuration override via environment variables
- [ ] 23.5 Document deployment procedure in docs/deployment/transition_deployment.md

## 24. Deployment & Validation

- [ ] 24.1 Run full pipeline on development environment
- [ ] 24.2 Validate all data quality metrics meet targets
- [ ] 24.3 Generate comprehensive evaluation report
- [ ] 24.4 Review with program stakeholders
- [ ] 24.5 Deploy to staging environment
- [ ] 24.6 Run regression tests on staging
- [ ] 24.7 Deploy to production
- [ ] 24.8 Monitor detection metrics post-deployment
- [ ] 24.9 Generate initial transition effectiveness report by CET area
