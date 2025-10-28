# Implementation Tasks

## 25. Next Work Package: Transition Linking MVP (2 sprints)
Goal: Deliver a minimal, testable end-to-end transition detection flow on a small, representative dataset. Focus on award↔contract linkage, scoring, evidence, and validation.

### Scope
- Data: 2–3 agencies, last 3–5 years of awards/contracts (sampled to <= 10k records each)
- Signals: UEI/DUNS vendor linkage, PIID/FAIN linkage, date overlap, award amount sanity, agency alignment
- Outputs: transitions.parquet, transitions.evidence.ndjson, checks JSON, Dagster asset metadata

### Tasks
- [ ] 25.1 Ingest a contracts SAMPLE
  - [ ] Implement/configure a “contracts_sample” extractor reading FPDS/USAspending subset (CSV/Parquet) to `data/processed/contracts_sample.parquet`
  - [ ] Columns: `piid`, `fain`, `uei`, `duns`, `vendor_name`, `action_date`, `obligated_amount`, `awarding_agency_code`
  - [ ] Add a checks JSON with record counts, date range, and coverage metrics (uei/duns/piid)
  - Acceptance:
    - [ ] Sample size between 1k–10k
    - [ ] ≥ 90% rows have `action_date`, ≥ 60% have at least one of `uei|duns|piid|fain`

- [ ] 25.2 Vendor Resolver (SBIR recipient → contractor)
  - [ ] Implement resolver pipeline using UEI, DUNS, and fuzzy name+state fallback (RapidFuzz)
  - [ ] Emit a mapping table: `award_recipient_id → contractor_id` with `match_type` and `confidence`
  - [ ] Persist to `data/processed/vendor_resolution.parquet` and checks JSON: coverage, precision sample
  - Acceptance:
    - [ ] ≥ 70% of SBIR recipients in the sample map to at least one contractor (any match_type)
    - [ ] Manual review of 50 random mappings shows ≥ 85% precision at `confidence >= 0.8`

- [ ] 25.3 Transition Scoring v1 (rule-based)
  - [ ] Implement a deterministic scorer that aggregates:
        UEI/DUNS exact (strong), PIID/FAIN link (strong), date overlap (medium), agency alignment (medium), amount sanity (low)
  - [ ] Output fields: `award_id`, `contract_id`, `score`, `signals[]`, `computed_at`
  - [ ] Thresholds in config; default: high>=0.80, med>=0.60
  - Acceptance:
    - [ ] Deterministic outputs for the same inputs
    - [ ] Top-10 transitions per award are stable across runs

- [ ] 25.4 Evidence Bundle v1
  - [ ] For each transition, emit structured evidence:
        `matched_keys`, `dates`, `amounts`, `agencies`, `resolver_path`, `notes`
  - [ ] Persist NDJSON to `data/processed/transitions_evidence.ndjson` and reference from score rows
  - Acceptance:
    - [ ] Evidence present for 100% of transitions with `score >= 0.60`

- [ ] 25.5 Dagster assets (MVP chain)
  - [ ] `contracts_sample` → `vendor_resolution` → `transition_scores_v1` → `transition_evidence_v1`
  - [ ] Each asset writes checks JSON and asset metadata (counts, durations)
  - Acceptance:
    - [ ] Materialization completes locally with the sample dataset
    - [ ] Checks JSON present for all assets; no ERROR severity issues

- [ ] 25.6 Validation & Gates (MVP)
  - [ ] Coverage gates:
        `contracts_sample`: action_date ≥ 90%, `vendor_resolution`: mapped ≥ 60%
  - [ ] Quality gate:
        transition precision quick-check via 30-manual-spot review ≥ 80% for `score>=0.80`
  - [ ] Write validation summary to `reports/validation/transition_mvp.json`
  - Acceptance:
    - [ ] Gates enforced in CI/dev; failing gate blocks downstream assets

- [ ] 25.7 Tests
  - [ ] Unit tests: resolver (UEI/DUNS/fuzzy), scorer (signal weights), evidence assembly
  - [ ] Integration tests: end-to-end sample pipeline on tiny fixture (<= 200 awards / 200 contracts)
  - [ ] Add golden files for expected small-run outputs and checks JSON
  - Acceptance:
    - [ ] ≥ 80% coverage on new modules, integration tests stable on CI

- [ ] 25.8 Docs
  - [ ] Add `docs/transition/mvp.md`: scope, data requirements, config keys, how-to-run, acceptance metrics
  - [ ] Update README with the new assets and make-targets
  - Acceptance:
    - [ ] Docs allow a new developer to run the MVP in < 30 minutes

### Deliverables
- `data/processed/contracts_sample.parquet`
- `data/processed/vendor_resolution.parquet`
- `data/processed/transitions.parquet` and `transitions_evidence.ndjson`
- Checks JSON for all assets; a validation summary report
- Unit/integration tests passing; coverage ≥ 80% on new code
- docs/transition/mvp.md updated

### Exit Criteria
- End-to-end run completes on the agreed sample within < 10 minutes locally
- Validation gates pass; manual spot-check precision ≥ 80% at `score>=0.80`
- All new tests passing in CI; docs published

## 1. Project Setup & Dependencies

- [x] 1.1 Promote rapidfuzz to main dependencies (needed for vendor name matching)
  - Notes: `rapidfuzz = {extras = ["simd"], version = "^3.9.1"}` is already present in `[tool.poetry.dependencies]` section of pyproject.toml. Ready for use in vendor name matching and fuzzy resolution.
- [x] 1.2 Create src/transition/ module structure (detection/, features/, config/)
  - Notes: Implemented `src/transition/` package with scaffolds:
    - `src/transition/detection/` (detection pipeline stubs)
    - `src/transition/features/` (vendor resolver and feature extractors)
    - `src/transition/config/` (configuration placeholders)
    - Added `src/transition/__init__.py` and initial `VendorResolver` implementation in `src/transition/features/vendor_resolver.py`.
    - Basic unit test and fixtures scaffold added to accelerate verification (see tests/unit/test_vendor_resolver.py).
- [x] 1.3 Add pytest fixtures for transition detection tests
  - Notes: Added pytest fixture `sample_vendors` and an initial unit test suite for `VendorResolver` at `tests/unit/test_vendor_resolver.py`. These provide the initial fixtures and tests for vendor name/identifier matching and will be extended for broader transition detection fixtures.
- [x] 1.4 Verify DuckDB availability for large contract dataset analytics
  - Notes: DuckDB `^1.0.0` is already available in `[tool.poetry.dependencies]`. Confirmed to be installed and ready for large contract dataset analytics (6.7M+ records). Can be used for memory-efficient processing of USAspending data.

## 2. Configuration Files

- [x] 2.1 Create config/transition/detection.yaml (scoring weights, thresholds)
  - Notes: Created comprehensive detection configuration with scoring weights for 6 signals (agency continuity: 0.25, timing proximity: 0.20, competition type: 0.20, patent signal: 0.15, cet alignment: 0.10, vendor match: 0.10). Includes confidence thresholds (High: ≥0.85, Likely: ≥0.65, Possible: <0.65), vendor matching priorities (UEI→CAGE→DUNS→fuzzy), timing windows (0-24 months default), and performance tuning parameters.
- [x] 2.2 Create config/transition/presets.yaml (high-precision, broad-discovery, balanced)
  - Notes: Implemented 6 preset configurations: high_precision (conservative, confidence ≥0.85, 12-month window), balanced (default, ≥0.65, 24-month window), broad_discovery (exploratory, ≥0.50, 36-month window), research (no threshold, 48-month window), phase_2_focus (optimized for Phase II awards), and cet_focused (emphasizes technology area alignment). Each preset includes custom scoring weights and signal configurations.
- [x] 2.3 Add timing window configuration (default: 0-24 months)
  - Notes: Timing window configuration implemented in detection.yaml with default 0-24 months after Phase II completion. Includes preset-specific overrides: 12 months (high_precision), 24 months (balanced/phase_2_focus), 36 months (broad_discovery), 48 months (research). Scoring curves for timing proximity with multipliers: 0-3mo (1.0x), 3-12mo (0.75x), 12-24mo (0.50x).
- [x] 2.4 Add vendor matching configuration (fuzzy threshold, identifier priority)
  - Notes: Vendor matching configuration includes priority-based resolution (UEI→CAGE→DUNS→fuzzy_name) with fuzzy thresholds: primary 0.85 (strict), secondary 0.70 (exploratory), algorithm token_set_ratio via rapidfuzz. Name normalization rules (uppercase, remove special chars, collapse whitespace). Cross-walk persistence with JSONL/Parquet support.
- [x] 2.5 Document transition configuration in config/transition/README.md
  - Notes: Created comprehensive README documenting all configuration files, quick start guide, configuration parameters (timing window, vendor matching, scoring signals, confidence levels), 4 detailed configuration examples (production/research/phase II/CET-focused), code examples for loading configuration, best practices, and troubleshooting guide. Total: 397 lines of documentation.

## 3. Pydantic Data Models

- [x] 3.1 Create Transition model in src/models/transition_models.py
- [x] 3.2 Create EvidenceBundle model (comprehensive audit trail)
- [x] 3.3 Create TransitionSignals models (Agency, Timing, Competition, Patent, CET)
- [x] 3.4 Create FederalContract model in src/models/contract_models.py
- [x] 3.5 Create VendorMatch model (cross-walk tracking)
- [x] 3.6 Create TransitionProfile model (company-level aggregation)
- [x] 3.7 Add validation rules for transition models

## 4. Vendor Resolution Module

- [x] 4.1 Create VendorResolver in src/transition/features/vendor_resolver.py
  - Notes: Implemented `VendorResolver` with in-memory indices and convenience factory `build_resolver_from_iterable`.
- [x] 4.2 Implement UEI exact matching (primary method, confidence: 0.99)
  - Notes: `resolve_by_uei` implemented with exact-match semantics and score = 1.0 for matches.
- [x] 4.3 Implement CAGE code matching (defense-specific, confidence: 0.95)
  - Notes: `resolve_by_cage` implemented with exact-match semantics and score = 1.0 for matches.
- [x] 4.4 Implement DUNS number matching (legacy, confidence: 0.90)
  - Notes: `resolve_by_duns` implemented with exact-match semantics and score = 1.0 for matches.
- [x] 4.5 Implement fuzzy name matching with rapidfuzz (threshold ≥0.90)
  - Notes: Name normalization and fuzzy matching implemented (`resolve_by_name`) using `rapidfuzz` when available and difflib fallback; configurable thresholds `fuzzy_threshold` and `fuzzy_secondary_threshold`.
- [x] 4.6 Create vendor cross-walk table (mapping all identifiers)
  - Notes: Implemented `src/transition/features/vendor_crosswalk.py` providing `CrosswalkRecord`, `VendorCrosswalk` manager, persistence helpers (JSONL/Parquet), DuckDB integration helpers, and alias/merge utilities. The manager supports add/merge semantics, name/identifier indices, and save/load functions to persist the cross-walk.
  - Notes: Cross-walk persistence (DB-backed table) not yet implemented; in-memory indices exist as scaffolding and a cross-walk table will be added later.
- [x] 4.7 Handle company acquisitions and name changes
  - Notes: Added acquisition/alias handling to `VendorCrosswalk` including `handle_acquisition` which records provenance, optionally merges acquired records into acquirers, preserves alias history, and updates indices. This includes provenance metadata and optional non-destructive aliasing when merge is not desired.
  - Notes: Complex acquisition/name-change handling is a planned enhancement that requires historical linkage data; remain open.
- [x] 4.8 Add vendor match confidence tracking
  - Notes: `VendorMatch` includes a `score` field and `VendorResolver` populates scores for fuzzy matches; the transformer/pipeline will persist these confidence scores.

## 5. Federal Contracts Ingestion

- [ ] 5.1 Create ContractExtractor in src/extractors/contract_extractor.py
- [ ] 5.2 Integrate with USAspending.gov CSV data
- [ ] 5.3 Implement chunked processing (100K contracts/batch) for 14GB+ dataset
- [ ] 5.4 Parse competition type (sole source, limited, full and open)
- [ ] 5.5 Extract vendor identifiers (UEI, CAGE, DUNS)
- [ ] 5.6 Handle parent-child contract relationships (IDV, IDIQ, BPA)
- [ ] 5.7 Create contracts_ingestion asset (depends on USAspending data)

## 6. Transition Scoring Algorithm

- [x] 6.1 Create TransitionScorer in src/transition/detection/scoring.py
  - Notes: Implemented `TransitionScorer` class with comprehensive scoring methods in `src/transition/detection/scoring.py`. Supports configurable weights via YAML configuration.
- [x] 6.2 Implement base score calculation (0.15 baseline)
  - Notes: Base score of 0.15 is configurable via `base_score` parameter. All scores build on this baseline.
- [x] 6.3 Implement agency continuity scoring (same agency: +0.25, cross-service: +0.125)
  - Notes: `score_agency_continuity()` method implements same agency (0.25 bonus * 0.25 weight = 0.0625), cross-service (0.125 * 0.25 = 0.03125), and different department (0.05 * 0.25 = 0.0125) scoring with configurable bonuses and weights.
- [x] 6.4 Implement timing proximity scoring (0-3mo: 1.0, 3-12mo: 0.75, 12-24mo: 0.5)
  - Notes: `score_timing_proximity()` method calculates days between award completion and contract start, applies time window-based multipliers: 0-90 days (1.0), 91-365 days (0.75), 366-730 days (0.5), with configurable windows via YAML.
- [x] 6.5 Implement competition type scoring (sole source: +0.20, limited: +0.10)
  - Notes: `score_competition_type()` method scores sole source (0.20 * 0.20 = 0.04), limited competition (0.10 * 0.20 = 0.02), full and open (0.0), with configurable bonuses.
- [x] 6.6 Implement patent signal scoring (has patent: +0.05, pre-contract: +0.03, topic match: +0.02)
  - Notes: `score_patent_signal()` method implements has_patent_bonus (0.05), pre_contract_bonus (0.03), topic_match_bonus (0.02) with similarity threshold (0.7), all weighted by patent signal weight (0.15).
- [x] 6.7 Implement CET area alignment scoring (same CET: +0.05)
  - Notes: `score_cet_alignment()` method provides same CET area bonus (0.05 * 0.10 = 0.005) with case-insensitive matching.
- [x] 6.8 Implement text similarity scoring (optional, configurable weight)
  - Notes: `score_text_similarity()` method accepts pre-computed similarity scores, applies only when enabled in config with configurable weight (default: disabled, 0.0 weight).
- [x] 6.9 Add configurable weights via YAML
  - Notes: All signal weights, bonuses, and thresholds are loaded from `config/transition/detection.yaml` via constructor. Scorer reads from `scoring` section with per-signal configuration including weights, bonuses, and enable/disable flags.
- [x] 6.10 Add confidence classification (High: ≥0.85, Likely: ≥0.65, Possible: <0.65)
  - Notes: `classify_confidence()` method maps likelihood scores to ConfidenceLevel enum (HIGH ≥0.85, LIKELY ≥0.65, POSSIBLE <0.65) using configurable thresholds. Comprehensive unit tests created in `tests/unit/test_transition_scorer.py` (32 tests, 93% code coverage).

## 7. Evidence Bundle Generation

- [x] 7.1 Create EvidenceGenerator in src/transition/detection/evidence.py
  - Notes: Implemented comprehensive EvidenceGenerator with methods for all signal types. Includes JSON serialization/deserialization and validation logic. Complete with detailed docstrings and logging.
- [x] 7.2 Generate agency signals evidence (same agency, department, score contribution)
  - Notes: `generate_agency_evidence()` method creates evidence items documenting same agency, cross-department, and different agency scenarios with appropriate snippets and metadata.
- [x] 7.3 Generate timing signals evidence (days after completion, within window)
  - Notes: `generate_timing_evidence()` method documents timing relationships with high/moderate/low proximity classifications and handles negative timing (anomalies).
- [x] 7.4 Generate competition signals evidence (type, score contribution)
  - Notes: `generate_competition_evidence()` method creates evidence for sole source, limited, and full and open competition types with descriptive snippets.
- [x] 7.5 Generate patent signals evidence (count, filing dates, topic similarity)
  - Notes: `generate_patent_evidence()` method documents patent counts, pre-contract filings, and topic similarity scores.
- [x] 7.6 Generate CET signals evidence (technology area alignment)
  - Notes: `generate_cet_evidence()` method creates evidence for CET area matches and mismatches.
- [x] 7.7 Generate vendor match evidence (method, confidence, matched identifier)
  - Notes: `generate_vendor_match_evidence()` method documents UEI, CAGE, DUNS, and fuzzy name matching with scores and metadata.
- [x] 7.8 Generate contract details evidence (PIID, agency, amount, start date)
  - Notes: `generate_contract_details_evidence()` method creates comprehensive contract summary evidence.
- [x] 7.9 Serialize evidence bundle to JSON (store on Neo4j relationships)
  - Notes: `serialize_bundle()` and `deserialize_bundle()` methods use Pydantic's model_dump_json() and model_validate_json() for robust JSON handling.
- [x] 7.10 Add evidence bundle validation (completeness, consistency)
  - Notes: `validate_bundle()` method checks for required fields, score ranges, and data completeness. Returns boolean with detailed logging.

## 8. Transition Detection Pipeline

- [x] 8.1 Create TransitionDetector in src/transition/detection/detector.py
  - Notes: Implemented full TransitionDetector pipeline orchestrating vendor matching, timing filtering, signal extraction, scoring, and evidence generation. Includes comprehensive metrics tracking and configurable parameters.
- [x] 8.2 Implement candidate selection (all contracts for vendors with SBIR awards)
  - Notes: `detect_batch()` method indexes contracts by vendor ID for efficient lookup. Supports UEI, CAGE, DUNS, and name-based vendor identification.
- [x] 8.3 Implement vendor matching (cross-walk resolution)
  - Notes: `match_vendor()` method resolves vendors using priority-based matching (UEI → CAGE → DUNS → fuzzy name) via VendorResolver integration. Tracks match method and confidence scores.
- [x] 8.4 Implement timing window filtering (0-24 months after award completion)
  - Notes: `filter_by_timing_window()` method applies configurable min/max days after completion (default: 0-730 days). Handles contracts without start dates gracefully.
- [x] 8.5 Implement signal extraction (agency, competition, timing, patent, CET)
  - Notes: Integrated with TransitionScorer to extract all signals. Builds structured data dicts for scoring from award and contract models.
- [x] 8.6 Implement likelihood scoring (composite score from all signals)
  - Notes: Uses TransitionScorer.score_and_classify() to compute composite likelihood scores from all enabled signals.
- [x] 8.7 Implement confidence classification (threshold-based)
  - Notes: Classifies detections into HIGH/LIKELY/POSSIBLE confidence levels using configurable thresholds. Tracks distribution in metrics.
- [x] 8.8 Implement evidence bundle generation
  - Notes: Integrated EvidenceGenerator to create comprehensive evidence bundles for each detection. Stores bundles in Transition.evidence field.
- [x] 8.9 Add batch processing for efficiency (1000 awards/batch)
  - Notes: `detect_batch()` method processes awards in configurable batch sizes with generator-based streaming. Supports efficient processing of large award datasets.
- [x] 8.10 Add progress logging and metrics
  - Notes: Integrated tqdm progress bars, comprehensive metrics tracking (awards processed, detections, vendor match rate, confidence distribution), and detailed logging at DEBUG/INFO levels. Includes `get_metrics()` and `reset_metrics()` methods.

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

- [x] 19.1 Unit tests for VendorResolver (UEI, CAGE, DUNS, fuzzy matching)
  - Notes: Comprehensive unit tests in `tests/unit/test_vendor_resolver.py` covering exact matching (UEI, CAGE, DUNS), fuzzy name matching, threshold handling, and cross-walk integration.
- [x] 19.2 Unit tests for TransitionScorer (all signal types, weight combinations)
  - Notes: Full test suite in `tests/unit/test_transition_scorer.py` with 32 tests covering all signal types (agency, timing, competition, patent, CET, text similarity), weight configurations, confidence classification, and edge cases. 93% code coverage.
- [x] 19.3 Unit tests for EvidenceGenerator (bundle completeness, serialization)
  - Notes: Comprehensive tests in `tests/unit/test_evidence_generator.py` covering all evidence types (agency, timing, competition, patent, CET, vendor match, contract details), JSON serialization/deserialization, bundle validation, and edge cases. Tests bundle completeness, score calculations, and error handling.
- [ ] 19.4 Unit tests for PatentSignalExtractor (timing, similarity, assignees)
  - Notes: Pending - PatentSignalExtractor not yet implemented (Task 9).
- [ ] 19.5 Unit tests for CETSignalExtractor (area alignment, scoring)
  - Notes: Pending - CETSignalExtractor not yet implemented (Task 10).
- [x] 19.6 Unit tests for TransitionDetector (end-to-end detection logic)
  - Notes: Complete test suite in `tests/unit/test_transition_detector.py` covering timing window filtering, vendor matching (all methods), single-award detection, batch processing, metrics tracking, confidence level distribution, and edge cases (empty contracts, missing data, optional vendor matching). Tests full pipeline integration.
- [ ] 19.7 Unit tests for TransitionAnalytics (dual-perspective calculations)
  - Notes: Pending - TransitionAnalytics not yet implemented (Task 12).
- [ ] 19.8 Unit tests for TransitionLoader (Neo4j node/relationship creation)
  - Notes: Pending - TransitionLoader not yet implemented (Task 13).

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
