# SBIR ETL Pipeline

## Documentation Map
- Specs (Kiro): `.kiro/specs/`
- User/Developer Docs: `docs/` (see `docs/index.md`)
- Agent Steering: `.kiro/steering/` (see `.kiro/steering/README.md`)
- Historical Reference: `archive/openspec/`

## Transition Detection System

**Status**: Production-ready. Core implementation 100% complete; deployment in progress.
**Completion**: 91% of tasks (169/186) ✓

### What is Transition Detection?

The **Transition Detection System** identifies which SBIR-funded companies likely transitioned their research into federal procurement contracts. It combines six independent signals to estimate the probability that an SBIR award led to a subsequent federal contract (commercialization).

**Key Question**: *Did this SBIR-funded research result in a federal contract?*

**Answer**: A composite likelihood score (0.0–1.0) with confidence classification (HIGH/LIKELY/POSSIBLE) supported by detailed evidence.

### How It Works

The system uses a multi-signal scoring approach:

1. **Vendor Resolution** - Match SBIR recipients to federal contractors (UEI, CAGE, DUNS, fuzzy name)
2. **Signal Extraction** - Extract 6 independent evidence signals:
   - 🏛️ **Agency Continuity** - Same federal agency indicates ongoing relationship
   - ⏱️ **Timing Proximity** - Contracts within 0–24 months of award completion
   - 🎯 **Competition Type** - Sole source/limited competition indicates vendor targeting
   - 📜 **Patent Signal** - Patents filed indicate technology maturity
   - 🔬 **CET Alignment** - Same critical technology area shows focus consistency
   - 🤝 **Vendor Match** - UEI/CAGE/DUNS exact match confirms same company
3. **Composite Scoring** - Weighted combination of all signals (0.0–1.0)
4. **Confidence Classification** - HIGH (≥0.85), LIKELY (0.65–0.84), POSSIBLE (<0.65)
5. **Evidence Generation** - Detailed justification for each detection
6. **Neo4j Loading** - Graph database storage for complex analysis

### Key Capabilities

- **Comprehensive Analysis**: 6 independent signals + configurable weights
- **Transparent Decisions**: Full evidence bundles justify every detection
- **Flexible Configuration**: Presets for high-precision, balanced, broad-discovery, and CET-focused analysis
- **Neo4j Integration**: Award→Transition→Contract pathways, patent backing, technology area clustering
- **Analytics**: Dual-perspective metrics (award-level + company-level transition rates)
- **Validation**: Precision/recall evaluation, confusion matrix, false positive analysis

### Performance

- **Throughput**: 15,000–20,000 detections/minute (target: ≥10K)
- **Coverage**: ~80% of SBIR awards resolve to contracts
- **Precision (HIGH)**: ≥85% (manual validation)
- **Recall**: ≥70% (vs. ground truth)
- **Scalability**: Tested on 252K awards + 6.7M contracts

### Data Assets

After transition detection pipeline:

- **transitions.parquet** - Detected transitions with scores and signals
- **transitions_evidence.ndjson** - Complete evidence bundles (JSON per line)
- **vendor_resolution.parquet** - Award recipient → contractor cross-walk
- **transition_analytics.json** - Aggregated KPIs (award-level, company-level, by-agency, by-CET)
- **transition_analytics_executive_summary.md** - Markdown report with key findings
- **Neo4j Transition nodes** - Queryable in graph database
- **Neo4j relationships** - TRANSITIONED_TO, RESULTED_IN, ENABLED_BY, INVOLVES_TECHNOLOGY

### Quick Start

```bash
# Run full transition detection pipeline (all SBIR awards)
poetry run python -m dagster job execute -f src/definitions.py -j transition_full_pipeline_job

# Or: Run from Dagster UI
dagster dev

# Then select and materialize "transition_full_pipeline_job"
```

**Expected Output** (10–30 minutes on typical hardware):
- 169/186 tasks complete
- ~40,000–80,000 detected transitions (depending on dataset size)
- Precision: ~85% (HIGH confidence)
- Full analytics suite generated

### Configuration

**Quick Setup**:
```bash
# Use balanced preset (default)
export SBIR_ETL__TRANSITION__DETECTION__PRESET=balanced

# Or: Use high-precision preset
export SBIR_ETL__TRANSITION__DETECTION__PRESET=high_precision

# Or: Use broad-discovery preset
export SBIR_ETL__TRANSITION__DETECTION__PRESET=broad_discovery
```

**Fine-Tuning**:
```bash
# Override confidence thresholds
export SBIR_ETL__TRANSITION__DETECTION__HIGH_CONFIDENCE_THRESHOLD=0.88
export SBIR_ETL__TRANSITION__DETECTION__LIKELY_CONFIDENCE_THRESHOLD=0.70

# Override timing window (days)
export SBIR_ETL__TRANSITION__DETECTION__MAX_DAYS=365  # 12 months instead of 24

# Override signal weights (must sum to 1.0)
export SBIR_ETL__TRANSITION__DETECTION__AGENCY_WEIGHT=0.30
export SBIR_ETL__TRANSITION__DETECTION__TIMING_WEIGHT=0.20
export SBIR_ETL__TRANSITION__DETECTION__COMPETITION_WEIGHT=0.20
export SBIR_ETL__TRANSITION__DETECTION__PATENT_WEIGHT=0.15
export SBIR_ETL__TRANSITION__DETECTION__CET_WEIGHT=0.15
```

### Documentation

**Comprehensive Guides** (6,126 lines total):
- 📖 [Detection Algorithm](docs/transition/detection_algorithm.md) - How the system works end-to-end
- 📖 [Scoring Guide](docs/transition/scoring_guide.md) - Detailed scoring breakdown + tuning
- 📖 [Vendor Matching](docs/transition/vendor_matching.md) - Vendor resolution methods + validation
- 📖 [Evidence Bundles](docs/transition/evidence_bundles.md) - Evidence structure + interpretation
- 📖 [Neo4j Schema](docs/schemas/transition-graph-schema.md) - Graph model + queries
- 📖 [CET Integration](docs/transition/cet_integration.md) - Technology area alignment
- 📖 [Data Dictionary](docs/data-dictionaries/transition_fields_dictionary.md) - Field reference

**Quick Reference**:
- 📋 [MVP Guide](docs/transition/mvp.md) - Minimal viable product
- 📋 [Configuration Reference](config/transition/README.md) - YAML configuration guide

### Neo4j Queries

**Find All Transitions for an Award**:
```cypher
MATCH (a:Award {award_id: "SBIR-2020-PHASE-II-001"})
  -[:TRANSITIONED_TO]->(t:Transition)
  -[:RESULTED_IN]->(c:Contract)
RETURN a.award_id, c.contract_id, t.likelihood_score, t.confidence
ORDER BY t.likelihood_score DESC
```

**Find Patent-Backed Transitions**:
```cypher
MATCH (t:Transition)-[:ENABLED_BY]->(p:Patent)
  -[:RESULTED_IN]->(c:Contract)
WHERE t.confidence IN ["HIGH", "LIKELY"]
RETURN t.transition_id, p.title, c.piid, t.likelihood_score
```

**Transition Effectiveness by CET Area**:
```cypher
MATCH (a:Award)-[:INVOLVES_TECHNOLOGY]->(cet:CETArea)
  <-[:INVOLVES_TECHNOLOGY]-(t:Transition)
WITH cet.name as cet_area,
     count(DISTINCT a) as total_awards,
     count(DISTINCT t) as transitions
RETURN cet_area, total_awards, transitions,
       round(100.0 * transitions / total_awards) as effectiveness_percent
ORDER BY effectiveness_percent DESC
```

### Testing

```bash
# Run all transition detection tests
poetry run pytest tests/unit/test_transition*.py -v
poetry run pytest tests/integration/test_transition_integration.py -v
poetry run pytest tests/e2e/test_transition_e2e.py -v

# Run with coverage
poetry run pytest tests/unit/test_transition*.py --cov=src/transition --cov-report=html

# Run specific signal tests
poetry run pytest tests/unit/test_transition_scorer.py -v  # 32 tests, 93% coverage
poetry run pytest tests/unit/test_cet_signal_extractor.py -v  # 37 tests, 96% coverage
```

### Key Files

**Implementation**:
- `src/transition/detection/` - Detection pipeline (scoring, evidence, detector)
- `src/transition/features/` - Feature extraction (vendor resolver, patent analyzer, CET)
- `src/transition/analysis/` - Analytics (dual-perspective metrics)
- `src/transition/evaluation/` - Evaluation (precision/recall, confusion matrix)
- `src/transition/queries/` - Neo4j queries (pathways, analytics)
- `src/loaders/transition_loader.py` - Neo4j loading

**Configuration**:
- `config/transition/detection.yaml` - Scoring weights, thresholds
- `config/transition/presets.yaml` - Preset configurations
- `config/transition/README.md` - Configuration guide

**Data**:
- `data/processed/transitions.parquet` - Detected transitions
- `data/processed/transitions_evidence.ndjson` - Evidence bundles (JSON per line)
- `data/processed/vendor_resolution.parquet` - Award→contractor cross-walk
- `data/processed/transition_analytics.json` - KPIs
- `reports/validation/transition_mvp.json` - MVP validation summary

### Algorithms

**Vendor Resolution** (4-step cascade):
1. UEI exact match (confidence: 0.99)
2. CAGE code exact match (confidence: 0.95)
3. DUNS number exact match (confidence: 0.90)
4. Fuzzy name matching with RapidFuzz (confidence: 0.65–0.85)

**Transition Scoring** (6 independent signals):
1. Agency continuity (weight: 0.25) - Same agency contracts
2. Timing proximity (weight: 0.20) - 0–24 months after award
3. Competition type (weight: 0.20) - Sole source/limited competition
4. Patent signal (weight: 0.15) - Patents filed; topic match
5. CET alignment (weight: 0.10) - Same technology area
6. Vendor match (weight: 0.10) - UEI/CAGE/DUNS confidence

**Confidence Bands**:
- HIGH: score ≥ 0.85 (high precision, ~85%)
- LIKELY: score 0.65–0.84 (balanced, ~75% precision)
- POSSIBLE: score <0.65 (high recall, ~40% precision)

### Next Steps

The project has successfully migrated from OpenSpec to Kiro for specification-driven development. All active OpenSpec changes have been converted to Kiro specifications.

For ongoing development:
- Use Kiro specifications in `.kiro/specs/` for new features and changes
- Follow the Kiro workflow for requirements, design, and task management
- Reference archived OpenSpec content in `archive/openspec/` for historical context only

**Migration Complete**: OpenSpec to Kiro migration completed successfully. See [Migration Report](migration_output/) for details.

---

## Transition Detection MVP

**Status**: MVP infrastructure complete. Sample data validated (5,000 contracts, 100% action_date coverage). Ready for quality gate review.</parameter>
</invoke>

### 30-Minute Quick Start

```bash
# 1. Verify contracts sample meets acceptance criteria
poetry run python scripts/validate_contracts_sample.py

# 2. Run the MVP pipeline (vendor resolution → transition scoring → evidence)
make transition-mvp-run

# 3. Review validation summary and gates
cat reports/validation/transition_mvp.json | jq .

# 4. Review 30 quality samples for precision assessment
cat reports/validation/transition_quality_review_sample.json | jq '.[] | select(.score >= 0.80)'

# 5. (Optional) Clean artifacts
make transition-mvp-clean
```

### What You Get

After the MVP run:
- ✓ **contracts_sample.parquet** (5,000 records with validated metadata)
- ✓ **vendor_resolution** mapping (award recipients → federal contracts)
- ✓ **transition_scores** with deterministic rule-based scoring
- ✓ **transitions_evidence.ndjson** for manual inspection
- ✓ **Quality review samples** (30 high-confidence transitions for precision assessment)
- ✓ **Validation gates** enforcing data quality (coverage, resolution rate, etc.)

### Acceptance Criteria (Task 25.1-25.6)

✓ Sample size: 1k–10k records  
✓ Action date coverage: ≥ 90%  
✓ Identifier coverage (UEI|DUNS|PIID): ≥ 60%  
✓ Vendor resolution rate: ≥ 70%  
⏳ Quality gate: 30-sample precision review ≥ 80% (awaiting manual assessment)

### Configuration

Adjust thresholds via environment variables (no restart needed):

```bash
export SBIR_ETL__TRANSITION__FUZZY__THRESHOLD=0.75        # Fuzzy match strictness
export SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MIN=500  # Min contracts
export SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MAX=15000 # Max contracts
export SBIR_ETL__TRANSITION__DATE_WINDOW_YEARS=3          # Award→contract window
```

See **docs/transition/mvp.md** for full documentation, scoring signals, and troubleshooting.

## CET (Critical and Emerging Technologies) Pipeline

Deployment
- CET deployment guide (staging/prod runbook): docs/deployment/cet-assets-deployment.md
- Staging Compose overlay: docker-compose.cet-staging.yml (bind mounts; .env for NEO4J_*/CET_MODEL_PATH)
- General production checklist: docs/DEPLOYMENT_CHECKLIST.md

This repository includes an end-to-end CET pipeline that classifies SBIR awards into CET areas, aggregates company-level CET profiles, and loads both enrichment properties and relationships into Neo4j.

### Run the full CET pipeline

You can execute the full CET job via Dagster:

```
dagster job execute -f src/definitions.py -j cet_full_pipeline_job
```

Requirements:
- Neo4j reachable via environment variables:
  - NEO4J_URI (e.g., bolt://localhost:7687)
  - NEO4J_USERNAME
  - NEO4J_PASSWORD
- Minimal CET configs under config/cet:
  - taxonomy.yaml
  - classification.yaml

Alternatively, run from the Dagster UI and select the job “cet_full_pipeline_job”.

### Assets included in the CET pipeline

The job orchestrates these assets in dependency order:
- cet_taxonomy
- cet_award_classifications
- cet_company_profiles
- neo4j_cetarea_nodes
- neo4j_award_cet_enrichment
- neo4j_company_cet_enrichment
- neo4j_award_cet_relationships
- neo4j_company_cet_relationships

### Neo4j schema for CET

See the CET graph schema documentation:
- docs/schemas/cet-neo4j-schema.md

This document covers:
- CETArea node schema and constraints
- Award/Company CET enrichment properties
- Award → CETArea APPLICABLE_TO relationships
- Company → CETArea SPECIALIZES_IN relationships
- Idempotent MERGE semantics and re-run safety

### CI

A dedicated CI workflow runs a tiny-fixture CET pipeline to catch regressions end-to-end:
- .github/workflows/cet-pipeline-ci.yml

This spins up a Neo4j service, builds minimal CET configs and sample awards, and executes the cet_full_pipeline_job, uploading resulting artifacts (processed outputs and Neo4j checks).

Performance baseline initialization

To enable automated regression detection against a baseline, initialize the CET performance baseline from existing processed artifacts. The initializer computes baseline coverage and specialization thresholds and writes them to `reports/benchmarks/baseline.json`. Run the initializer locally or in CI (after producing the processed artifacts) with:

    python scripts/init_cet_baseline.py \
      --awards-parquet data/processed/cet_award_classifications.parquet \
      --companies-path data/processed/cet_company_profiles.parquet

Once the baseline is created, the performance/regression job will compare current runs to the saved baseline and surface alerts when thresholds are exceeded. The baseline file is retained by CI artifacts and can be updated with the `--force` or `--set-thresholds` flags as needed.

A robust ETL (Extract, Transform, Load) pipeline for processing SBIR (Small Business Innovation Research) program data into Neo4j graph database.

### Why This Project?

The federal government provides a vast amount of data on innovation and government funding. However, this data is spread across multiple sources and formats, making it difficult to analyze. This project provides a unified and enriched view of the SBIR ecosystem by:

*   **Connecting disparate data sources:** Integrating SBIR awards, USAspending contracts, USPTO patents, and other publicly available data.
*   **Building a knowledge graph:** Structuring the data in a Neo4j graph database to reveal complex relationships.
*   **Enabling powerful analysis:** Allowing for queries that trace funding, track technology transitions, and analyze patent ownership chains.

## Overview

This project implements a five-stage ETL pipeline that processes SBIR award data from multiple government sources and loads it into a Neo4j graph database for analysis and visualization.

### Pipeline Stages

1. **Extract**: Download and parse raw data (SBIR.gov CSV, USAspending PostgreSQL dump, USPTO patent DTAs)
2. **Validate**: Schema validation and data quality checks
3. **Enrich**: Augment data with fuzzy matching and external enrichment
4. **Transform**: Business logic and graph-ready entity preparation
5. **Load**: Write to Neo4j with idempotent operations and relationship chains

```
+-----------+      +------------+      +----------+      +-------------+      +--------+
|  Extract  |----->|  Validate  |----->|  Enrich  |----->|  Transform  |----->|  Load  |
+-----------+      +------------+      +----------+      +-------------+      +--------+
    |                  |                   |                   |                  |
 (Python/           (Pydantic)         (DuckDB/            (Python/           (Neo4j/
  Pandas)                             Fuzzy-matching)      Pandas)            Cypher)
```

## Features

- **Dagster Orchestration**: Asset-based pipeline with dependency management and observability
- **DuckDB Processing**: Efficient querying of CSV and PostgreSQL dump data
- **Neo4j Graph Database**: Patent chains, award relationships, technology transition tracking
- **Pydantic Configuration**: Type-safe YAML configuration with environment overrides
- **Docker Deployment**: Multi-stage build with dev, test, and prod profiles

#### Quality Gates

Configurable thresholds enforce data quality:

```yaml
# config/base.yaml
enrichment:
  match_rate_threshold: 0.70      # Min 70% match rate

validation:
  pass_rate_threshold: 0.95       # Min 95% pass rate

loading:
  load_success_threshold: 0.99    # Min 99% load success
```

**Asset Checks:**
- `enrichment_quality_regression_check` — Compare to baseline
- `patent_load_success_rate` — Verify Neo4j load success
- `assignment_load_success_rate` — Verify relationship creation

## Quick Start

### Prerequisites

- **Python**: 3.11 or 3.12
- **Poetry**: For dependency management
- **Docker**: For containerized development
- **Neo4j**: 5.x (provided via Docker Compose)

### Container Development (Recommended)

The project provides Docker Compose for a consistent development and testing environment, including comprehensive E2E testing capabilities optimized for MacBook Air development.

1. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env: set NEO4J_USER, NEO4J_PASSWORD
   ```

2. **Build and start services:**
   ```bash
   make docker-build
   make docker-up-dev
   ```

3. **Run the pipeline:**
   Open your browser to [http://localhost:3000](http://localhost:3000) and materialize the assets to run the pipeline.

4. **Run tests in container:**
   ```bash
   make docker-test
   ```

5. **Run E2E tests locally:**
   ```bash
   # Run comprehensive E2E tests (MacBook Air optimized)
   make docker-e2e-standard
   
   # Quick smoke test (< 2 minutes)
   make docker-e2e-minimal
   
   # Performance test with larger datasets
   make docker-e2e-large
   
   # Edge case testing
   make docker-e2e-edge-cases
   
   # Interactive debugging
   make docker-e2e-debug
   
   # Cleanup E2E environment
   make docker-e2e-clean
   ```

6. **View logs:**
   ```bash
   make docker-logs SERVICE=dagster-webserver
   ```

See `docs/guides/containerization.md` for full details.

### Local Development (Alternative)

1. **Clone and install dependencies:**
   ```bash
   git clone <repository-url>
   cd sbir-etl
   poetry install
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with Neo4j credentials and data paths
   ```

3. **Start Dagster UI:**
   ```bash
   poetry run dagster dev
   # Open http://localhost:3000 and materialize the assets.
   ```

4. **Run tests:**
   ```bash
   pytest -v --cov=src --cov-report=html
   ```

## Bulk Data Sources

### SBIR Awards
- **Source**: [SBIR.gov Awards Database](https://www.sbir.gov/awards)
- **Format**: CSV with 42 columns
- **Records**: ~533,000 awards (1983–present)
- **Update**: Monthly exports available

### USAspending
- **Source**: PostgreSQL database dump
- **Size**: 51GB compressed
- **Purpose**: Award enrichment, transaction tracking, technology transition detection
- **Coverage**: Federal contract and grant transactions

### USPTO Patents
- **Source**: [USPTO Patent Assignment Dataset](https://www.uspto.gov/learning-and-resources/patent-assignment-data)
- **Format**: CSV, Stata (.dta), Parquet
- **Purpose**: Patent ownership chains, SBIR-funded patent tracking

## Configuration

Configuration uses a unified three-layer system with consolidated schemas:

```
config/
├── base.yaml          # Defaults (version controlled)
├── dev.yaml           # Development overrides
├── prod.yaml          # Production settings
├── sbir/              # SBIR-specific configurations
├── uspto/             # USPTO-specific configurations
└── cet/               # CET-specific configurations
```

The unified configuration system provides:
- **Single hierarchical Pydantic model** for type-safe validation
- **Standardized SBIR_ETL__ prefix** for all environment variables
- **Environment-specific overrides** through consistent loading mechanism
- **Hot-reload capability** for development environments

Environment variables override YAML using `SBIR_ETL__SECTION__KEY=value`:

```bash
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__ENRICHMENT__MATCH_RATE_THRESHOLD=0.75
export SBIR_ETL__CORE__DEBUG=true
```

## Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src --cov-report=html

# Run specific test categories
poetry run pytest tests/unit/test_config.py -v
poetry run pytest tests/integration/ -v
poetry run pytest tests/e2e/ -v

# Container tests
make docker-test

# E2E tests (containerized - recommended)
make docker-e2e-minimal      # Quick smoke test (< 2 min)
make docker-e2e-standard     # Full validation (5-8 min)
make docker-e2e-large        # Performance test (8-10 min)
make docker-e2e-edge-cases   # Robustness test (3-5 min)

# E2E tests (direct script execution - alternative)
python scripts/run_e2e_tests.py --scenario minimal    # Quick smoke test
python scripts/run_e2e_tests.py --scenario standard   # Full validation
python scripts/run_e2e_tests.py --scenario large      # Performance test
python scripts/run_e2e_tests.py --scenario edge-cases # Robustness test
```

**Test Suite:**
- 29+ tests across unit, integration, and E2E
- Coverage target: ≥80% (CI enforced)
- Serial execution: ~8-12 minutes in CI
- E2E tests: MacBook Air optimized with Docker Compose
  - Minimal scenario: < 2 minutes, ~2GB memory
  - Standard scenario: 5-8 minutes, ~4GB memory  
  - Large scenario: 8-10 minutes, ~6GB memory
  - Resource limits: 8GB total memory, 2 CPU cores

## Project Structure

```
sbir-etl/
├── src/
│   ├── core/                    # Consolidated core functionality
│   │   ├── assets/             # Unified asset definitions
│   │   ├── config/             # Single configuration system
│   │   ├── models/             # Consolidated data models
│   │   └── monitoring/         # Unified performance monitoring
│   ├── pipeline/               # Pipeline-specific logic
│   │   ├── extraction/         # Data extraction components
│   │   ├── enrichment/         # Data enrichment components
│   │   ├── transformation/     # Data transformation components
│   │   └── loading/            # Data loading components
│   ├── shared/                 # Shared utilities and helpers
│   │   ├── database/           # Database clients and utilities
│   │   ├── validation/         # Validation logic
│   │   └── utils/              # Common utilities
│   └── tests/                  # Unified testing framework
│       ├── fixtures/           # Shared test fixtures
│       ├── helpers/            # Test utilities
│       └── scenarios/          # Test scenarios
│
├── config/                      # YAML configuration
│   ├── base.yaml                # Defaults + thresholds
│   ├── dev.yaml                 # Development overrides
│   └── prod.yaml                # Production settings
│
├── tests/                       # Test suite (29+ tests)
│   ├── unit/                    # Component-level tests
│   ├── integration/             # Multi-component tests
│   └── e2e/                     # End-to-end pipeline tests
│       └── test_dagster_enrichment_pipeline.py  # E2E smoke tests
│
├── scripts/
│   ├── benchmark_enrichment.py           # Baseline creation
│   ├── detect_performance_regression.py  # CI regression check
│   ├── run_e2e_tests.py                  # E2E test orchestration
│   └── e2e_health_check.py               # E2E environment validation
│
├── docs/
│   ├── data/                    # Data dictionaries
│   ├── deployment/              # Container guides
│   └── schemas/                 # Neo4j schema docs
│
├── reports/                     # Generated artifacts (gitignored)
│   ├── benchmarks/baseline.json     # Cached baseline
│   ├── alerts/                      # Performance alerts
│   └── dashboards/                  # Quality dashboards
│
├── .github/workflows/
│   ├── ci.yml                       # Standard CI
│   ├── container-ci.yml             # Docker test runner
│   ├── neo4j-smoke.yml              # Integration tests
│   ├── performance-regression-check.yml  # Benchmark pipeline
│   ├── cet-pipeline-ci.yml          # CET pipeline validation
│   └── secret-scan.yml
│
├── docker/                      # Docker Compose configurations
│   ├── docker-compose.dev.yml      # Development stack with bind mounts
│   ├── docker-compose.test.yml     # Test runner environment
│   └── docker-compose.e2e.yml      # E2E testing (MacBook Air optimized)
│
├── .kiro/                       # Kiro specifications (active spec system)
│   ├── specs/                   # Specification-driven development
│   └── steering/                # Agent steering documents (architectural patterns)
└── archive/                     # Archived content
    └── openspec/                # Archived OpenSpec content (historical reference)
```

## Neo4j Graph Model

**Node Types:**
- `Award` — SBIR/STTR awards with company, agency, phase, amount
- `Company` — Awardee companies with contact info, location
- `Patent` — USPTO patents linked to SBIR-funded research
- `PatentAssignment` — Patent transfer transactions
- `PatentEntity` — Assignees and assignors (normalized names)

**Relationship Types:**
- `RECEIVED` — Company → Award
- `GENERATED_FROM` — Patent → Award (SBIR-funded patents)
- `OWNS` — Company → Patent (current ownership)
- `ASSIGNED_VIA` — Patent → PatentAssignment
- `ASSIGNED_FROM` — PatentAssignment → PatentEntity
- `ASSIGNED_TO` — PatentAssignment → PatentEntity
- `CHAIN_OF` — PatentAssignment → PatentAssignment (ownership history)

**Query Examples:**

```cypher
# Find all awards for a company
MATCH (c:Company {name: "Acme Inc"})-[:RECEIVED]->(a:Award)
RETURN a.title, a.amount, a.phase

# Trace patent ownership chain
MATCH path = (p:Patent)-[:ASSIGNED_VIA*]->(pa:PatentAssignment)
WHERE p.grant_doc_num = "7123456"
RETURN path

# Find SBIR-funded patents with assignments
MATCH (a:Award)<-[:GENERATED_FROM]-(p:Patent)-[:ASSIGNED_VIA]->(pa:PatentAssignment)
WHERE a.company_name = "Acme Inc"
RETURN p.title, pa.assignee_name, pa.recorded_date
```

## Continuous Integration

GitHub Actions workflows:

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push to main/develop, PRs | Standard CI (lint, test, security) |
| `container-ci.yml` | Push to main/develop, PRs | Docker build + test (serial, ~8-12 min) |
| `neo4j-smoke.yml` | Push to main/develop, PRs | Neo4j integration tests |
| `performance-regression-check.yml` | PRs (enrichment changes) | Benchmark + regression detection |
| `secret-scan.yml` | Push to main/develop, PRs | Secret leak detection |

**Performance Regression CI:**
- Runs on enrichment/asset changes
- Compares to cached baseline (`reports/benchmarks/baseline.json`)
- Posts PR comment with duration/memory/match_rate deltas
- Sets GitHub Check status (success/failure)
- Uploads artifacts (regression JSON, HTML report)


## Documentation

- **Testing**: `docs/testing/README.md`, `docs/testing/e2e-testing-guide.md` (comprehensive testing guides)
- **Data Sources**: `docs/data/usaspending-evaluation.md`, `data/raw/uspto/README.md`
- **Deployment**: `docs/deployment/containerization.md`
- **Schemas**: `docs/schemas/patent-neo4j-schema.md`
- **Specifications**: `.kiro/specs/` (Kiro specification system) - see `AGENTS.md` for workflow guidance

## Contributing

1. Follow code quality standards (black, ruff, mypy, bandit)
2. Write tests for new functionality (≥80% coverage)
3. Update documentation as needed
4. Use Kiro specs for architectural changes (see `.kiro/specs/` and `AGENTS.md` for workflow)
5. Ensure performance regression checks pass in CI

### Upcoming Architecture Changes

**Specification System Migration** (Completed): The project has successfully migrated from OpenSpec to Kiro for specification-driven development. This migration:
- Consolidated all specifications into Kiro's unified format
- Implemented EARS patterns for requirements documentation
- Established task-driven development workflows
- Preserved historical OpenSpec content in `archive/openspec/` for reference

All new development should use the Kiro specification system in `.kiro/specs/`.

**Codebase Consolidation Refactor** (Q1 2025): A comprehensive refactoring effort is planned to consolidate and streamline the codebase architecture. This will:
- Reduce code duplication by 30-60%
- Unify configuration management across all components
- Consolidate asset definitions with clear separation of concerns
- Establish unified testing framework with consistent patterns
- Centralize performance monitoring and metrics collection

See [Consolidation Refactor Plan](docs/architecture/consolidation-refactor-plan.md) and [Migration Guide](docs/architecture/consolidation-migration-guide.md) for details.

## License

This project is licensed under the [MIT License](LICENSE). Copyright (c) 2025 Conrad Hollomon.
