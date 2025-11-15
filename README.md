# SBIR ETL Pipeline

A robust, consolidated ETL pipeline for processing SBIR program data into a Neo4j graph database for analysis and visualization.

## Quick Start

### Prerequisites

- **Python**: 3.11 or 3.12
- **uv**: For dependency management ([install uv](https://github.com/astral-sh/uv))
- **Neo4j Aura**: Neo4j cloud instance (Free tier available)
- **R** (optional): For fiscal returns analysis with StateIO/USEEIOR models

### Local Development

1. **Clone and install dependencies:**
   ```bash
   git clone <repository-url>
   cd sbir-etl
   uv sync
   ```

2. **Set up Neo4j Aura:**
   - Create a Neo4j Aura instance at [neo4j.com/cloud/aura](https://neo4j.com/cloud/aura)
   - Copy your connection URI and credentials

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env: set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
   ```

4. **Run the pipeline:**
   ```bash
   uv run dagster dev
   # Open http://localhost:3000 and materialize the assets
   ```

5. **Run tests:**
   ```bash
   uv run pytest -v --cov=src
   ```

### Container Development (Alternative)

For containerized development with Docker Compose:

```bash
cp .env.example .env
# Edit .env: set NEO4J_USER, NEO4J_PASSWORD (for local Neo4j if not using Aura)
make docker-build
make docker-up-dev
# Open http://localhost:3000 and materialize the assets
```

See `docs/deployment/containerization.md` for full details.

## Overview

This project implements a five-stage ETL pipeline that processes SBIR award data from multiple government sources and loads it into a Neo4j graph database for analysis and visualization.

### Pipeline Stages

1. **Extract**: Download and parse raw data (SBIR.gov CSV, USAspending PostgreSQL dump, USPTO patent DTAs)
2. **Validate**: Schema validation and data quality checks
3. **Enrich**: Augment data with fuzzy matching and external enrichment
4. **Transform**: Business logic and graph-ready entity preparation
5. **Load**: Write to Neo4j with idempotent operations and relationship chains

### Key Features

- **Dagster Orchestration**: Asset-based pipeline with dependency management and observability
- **DuckDB Processing**: Efficient querying of CSV and PostgreSQL dump data
- **Neo4j Graph Database**: Patent chains, award relationships, technology transition tracking
- **Pydantic Configuration**: Type-safe YAML configuration with environment overrides
- **Docker Deployment**: Multi-stage build with dev, test, and prod profiles
- **Iterative Enrichment Refresh**: Automatic freshness tracking and refresh for enrichment data

## Documentation Map

- Specs (Kiro): `.kiro/specs/` (Active) | `.kiro/specs/archive/` (Completed)
- User/Developer Docs: `docs/` (see `docs/index.md`)
- Agent Steering: `.kiro/steering/` (see `.kiro/steering/README.md`)

## Transition Detection System

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

### Usage

```bash
# Run full transition detection pipeline
uv run python -m dagster job execute -f src/definitions.py -j transition_full_job

# Or: Run from Dagster UI
uv run dagster dev
# Then select and materialize "transition_full_job"
```

**Expected Output**: ~40,000–80,000 detected transitions with ≥85% precision (HIGH confidence)

### Configuration

### Quick Setup

```bash

## Use balanced preset (default)

export SBIR_ETL__TRANSITION__DETECTION__PRESET=balanced

## Or: Use high-precision preset

export SBIR_ETL__TRANSITION__DETECTION__PRESET=high_precision

## Or: Use broad-discovery preset

export SBIR_ETL__TRANSITION__DETECTION__PRESET=broad_discovery
```

### Fine-Tuning

```bash

## Override confidence thresholds

export SBIR_ETL__TRANSITION__DETECTION__HIGH_CONFIDENCE_THRESHOLD=0.88
export SBIR_ETL__TRANSITION__DETECTION__LIKELY_CONFIDENCE_THRESHOLD=0.70

## Override timing window (days)

export SBIR_ETL__TRANSITION__DETECTION__MAX_DAYS=365  # 12 months instead of 24

## Override signal weights (must sum to 1.0)

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

### Quick Reference
- 📋 [MVP Guide](docs/transition/mvp.md) - Minimal viable product
- 📋 [Configuration Reference](config/transition/README.md) - YAML configuration guide

### Neo4j Queries

### Find All Transitions for an Award

```cypher
MATCH (a:Award {award_id: "SBIR-2020-PHASE-II-001"})

  -[:TRANSITIONED_TO]->(t:Transition)
  -[:RESULTED_IN]->(c:Contract)

RETURN a.award_id, c.contract_id, t.likelihood_score, t.confidence
ORDER BY t.likelihood_score DESC
```

### Find Patent-Backed Transitions

```cypher
MATCH (t:Transition)-[:ENABLED_BY]->(p:Patent)

  -[:RESULTED_IN]->(c:Contract)

WHERE t.confidence IN ["HIGH", "LIKELY"]
RETURN t.transition_id, p.title, c.piid, t.likelihood_score
```

### Transition Effectiveness by CET Area

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

## Run all transition detection tests

uv run pytest tests/unit/test_transition*.py -v
uv run pytest tests/integration/test_transition_integration.py -v
uv run pytest tests/e2e/test_transition_e2e.py -v

## Run with coverage

uv run pytest tests/unit/test_transition*.py --cov=src/transition --cov-report=html

## Run specific signal tests

uv run pytest tests/unit/test_transition_scorer.py -v  # 32 tests, 93% coverage
uv run pytest tests/unit/test_cet_signal_extractor.py -v  # 37 tests, 96% coverage
```

### Key Files

### Implementation
- `src/transition/detection/` - Detection pipeline (scoring, evidence, detector)
- `src/transition/features/` - Feature extraction (vendor resolver, patent analyzer, CET)
- `src/transition/analysis/` - Analytics (dual-perspective metrics)
- `src/transition/evaluation/` - Evaluation (precision/recall, confusion matrix)
- `src/transition/queries/` - Neo4j queries (pathways, analytics)
- `src/loaders/transition_loader.py` - Neo4j loading

### Configuration
- `config/transition/detection.yaml` - Scoring weights, thresholds
- `config/transition/presets.yaml` - Preset configurations
- `config/transition/README.md` - Configuration guide

### Data
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

### Confidence Bands
- HIGH: score ≥ 0.85 (high precision, ~85%)
- LIKELY: score 0.65–0.84 (balanced, ~75% precision)
- POSSIBLE: score <0.65 (high recall, ~40% precision)

### Implementation Status

**Transition Detection**: ✅ **FULLY COMPLETED** (October 30, 2025)
- All 169 specification tasks implemented and validated
- Performance metrics achieved: ≥10K detections/min, ≥85% precision, ≥70% recall
- Complete documentation suite delivered (8 guides, 6,126 lines)
- Neo4j graph schema implemented with full relationship modeling
- Archived in `.kiro/specs/archive/completed-features/transition_detection/`

## Fiscal Returns Analysis System

### What is Fiscal Returns Analysis?

The **Fiscal Returns Analysis System** calculates the return on investment (ROI) of SBIR program funding by estimating federal tax receipts generated from economic impacts. It uses economic input-output modeling to trace how SBIR investments flow through the economy and generate taxable economic activity.

**Key Question**: *What is the fiscal return to the federal government from SBIR investments?*

**Answer**: Quantitative ROI metrics with confidence intervals, showing dollars of federal tax receipts per dollar of SBIR investment.

### How It Works

The system uses a multi-stage economic modeling approach:

1. **Data Preparation** - Enrich SBIR awards with NAICS codes, geographic data, and inflation adjustments
2. **Economic Modeling** - Map NAICS to BEA sectors, aggregate economic shocks, compute impacts via StateIO/USEEIO
3. **Tax Calculation** - Extract wage/income components, estimate federal tax receipts using tax rates
4. **ROI Analysis** - Calculate net present value, ROI ratios, and payback periods
5. **Sensitivity Analysis** - Parameter sweeps and uncertainty quantification with confidence intervals
6. **Audit Trail** - Complete lineage tracking from source awards to final estimates

### Key Capabilities

- **Economic Impact Modeling**: Integration with StateIO/USEEIO models via R interface
- **Comprehensive Tax Estimation**: Federal income, payroll, and corporate tax calculations
- **Sensitivity Analysis**: Monte Carlo parameter sweeps with uncertainty quantification
- **Geographic Resolution**: State-level economic impact modeling
- **Quality Gates**: Configurable thresholds for NAICS coverage, confidence scores, and mapping rates
- **Audit Trails**: Complete parameter and transformation tracking for reproducibility

### Performance

- **Pipeline Assets**: 13 Dagster assets with 7 quality checks
- **Processing Speed**: Optimized for large-scale SBIR datasets
- **Quality Thresholds**: ≥85% NAICS coverage, ≥90% BEA sector mapping
- **Confidence Scoring**: Hierarchical fallback with evidence tracking

### Data Assets

After fiscal returns analysis pipeline:

- **fiscal_return_summary.parquet** - ROI metrics and tax estimates by award
- **sensitivity_scenarios.parquet** - Parameter sweep results with confidence intervals
- **uncertainty_analysis.json** - Statistical uncertainty quantification
- **comprehensive_fiscal_report.json** - Complete analysis with all metrics
- **audit_trail.json** - Parameter lineage and transformation history

### Usage

```bash
# Run MVP fiscal analysis (core functionality)
uv run python -m dagster job execute -f src/definitions.py -j fiscal_returns_mvp_job

# Run full analysis with sensitivity analysis
uv run python -m dagster job execute -f src/definitions.py -j fiscal_returns_full_job

# Or: Run from Dagster UI
uv run dagster dev
# Then select and materialize "fiscal_returns_full_job"
```

**Expected Output** (15–45 minutes depending on dataset size):
- All fiscal analysis assets materialized ✅
- ROI calculations with confidence intervals
- Sensitivity analysis with parameter sweeps
- Complete audit trail and quality metrics

### Configuration

### Key Settings

```bash

## Base analysis year

export SBIR_ETL__FISCAL_ANALYSIS__BASE_YEAR=2023

## Quality thresholds

export SBIR_ETL__FISCAL_ANALYSIS__QUALITY_THRESHOLDS__NAICS_COVERAGE_RATE=0.85
export SBIR_ETL__FISCAL_ANALYSIS__QUALITY_THRESHOLDS__BEA_SECTOR_MAPPING_RATE=0.90

## Economic modeling parameters

export SBIR_ETL__FISCAL_ANALYSIS__ECONOMIC_MODELING__DISCOUNT_RATE=0.03
export SBIR_ETL__FISCAL_ANALYSIS__ECONOMIC_MODELING__ANALYSIS_PERIOD_YEARS=10

## StateIO model version

export SBIR_ETL__FISCAL_ANALYSIS__STATEIO_MODEL_VERSION=v2.1
```

### R Package Installation

For fiscal returns analysis with StateIO/USEEIOR economic models:

### R Package Repositories:
- **StateIO**: https://github.com/USEPA/stateior
- **USEEIOR**: https://github.com/USEPA/useeior

1. **Install R**:

   ```bash
   # macOS
   brew install r

   # Linux
   sudo apt-get update && sudo apt-get install r-base

   # Windows: Download from https://cran.r-project.org/bin/windows/base/
   ```

2. **Install Python rpy2**:

   ```bash
   uv sync --extra r
   ```

3. **Install R packages** (in R console):

   ```r
   install.packages("remotes")
   remotes::install_github("USEPA/stateior")
   remotes::install_github("USEPA/useeior")
   ```

4. **Validate installation**:

   ```bash
   python scripts/validate_r_adapter.py check-installation
   python scripts/validate_r_adapter.py test-adapter
   ```

See `docs/fiscal/r-package-reference.md` for detailed documentation and troubleshooting.

### Implementation Status

**Fiscal Returns Analysis**: ✅ **FULLY COMPLETED** (November 2025)

- Complete economic modeling pipeline with StateIO/USEEIO integration
- Federal tax estimation with comprehensive rate structures
- Sensitivity analysis and uncertainty quantification
- 13 Dagster assets with full quality gate coverage
- Comprehensive test suite (10 test files covering unit, integration, validation)
- Archived in `.kiro/specs/archive/sbir-fiscal-returns-analysis/`

### Statistical Reporting System

**Status**: 🚧 **IN DEVELOPMENT** - Core infrastructure implemented, module analyzers in progress

The Statistical Reporting System provides comprehensive, multi-format reports for pipeline runs, enabling data-driven decisions and quality tracking across all pipeline stages.

### Implementation Status
- ✅ Core infrastructure: `StatisticalReporter`, data models, configuration schema
- ✅ Multi-format report generation: HTML, JSON, Markdown, Executive dashboards
- ✅ CI/CD integration: GitHub Actions artifacts, PR comments
- 🚧 Module-specific analyzers: SBIR enrichment, patent analysis, CET classification, transition detection
- 🚧 Automated insights: Anomaly detection, quality recommendations, success story identification

#### Key Features

- **Comprehensive Reports**: Data quality, performance metrics, and pipeline insights
- **Multiple Formats**: HTML (interactive), JSON (machine-readable), Markdown (PR-friendly), Executive dashboards
- **Module-Specific Analysis**: SBIR enrichment, patent analysis, CET classification, transition detection
- **Executive Reporting**: High-level impact metrics, success stories, program effectiveness analysis
- **Automated Insights**: Quality recommendations, anomaly detection, threshold violations
- **CI/CD Integration**: GitHub Actions artifacts, PR comments, historical comparison

#### Quick Start

```python

## Generate reports for a pipeline run

from src.utils.statistical_reporter import StatisticalReporter

reporter = StatisticalReporter()

## Generate comprehensive reports

run_context = {
    "run_id": "run_20251030_143022",
    "pipeline_name": "sbir-etl",
    "modules": {"sbir_enrichment": {"stage": "enrich", "records_processed": 50000}}
}

report_collection = reporter.generate_reports(run_context)

## Returns ReportCollection with artifacts for all formats

```

###Report Types

### Data Hygiene Metrics
- Clean vs dirty data ratios
- Validation pass/fail rates
- Quality score distributions
- Field-level completeness

### Module Reports
- **SBIR Enrichment**: Match rates, source breakdown, coverage metrics
- **Patent Analysis**: Validation results, loading statistics, quality scores
- **CET Classification**: Technology distribution, detection rates, coverage
- **Transition Detection**: Classification distribution, confidence scores

### Executive Reports
- **Impact Metrics**: Total funding analyzed, companies tracked, patents linked
- **Success Stories**: High-impact technology transitions, commercialization examples
- **Program Effectiveness**: Funding ROI, commercialization rates, sector performance
- **Comparative Analysis**: Performance against program goals and benchmarks

### Automated Insights
- Quality threshold violations with severity levels
- Performance anomaly detection and analysis
- Actionable recommendations for identified issues
- Trend analysis and regression detection

#### Configuration

```yaml

## config/base.yaml

statistical_reporting:
  output_formats: ["html", "json", "markdown", "executive"]
  output_directory: "reports/statistical"
  retention_days: 30

  insights:
    quality_threshold: 0.95
    performance_threshold: 0.80
    anomaly_detection: true
    success_stories:
      enabled: true
      min_impact_threshold: 0.8
```

###CI/CD Integration

Reports are automatically generated in GitHub Actions:

- **Artifacts**: 30-day retention for HTML, JSON, Markdown, and Executive reports
- **PR Comments**: Markdown summaries with key metrics and changes
- **Executive Dashboards**: High-level impact metrics and success stories for stakeholders
- **Historical Comparison**: Trend analysis against previous runs

See `.kiro/specs/statistical_reporting/` for complete specification and implementation status.

### Next Steps

The project has successfully migrated from OpenSpec to Kiro for specification-driven development. All active OpenSpec changes have been converted to Kiro specifications.

For ongoing development:

- Use Kiro specifications in `.kiro/specs/` for new features and changes
- Follow the Kiro workflow for requirements, design, and task management
- Reference archived OpenSpec content in `archive/openspec/` for historical context only

**Migration Complete**: OpenSpec to Kiro migration completed successfully. See [Migration Report](migration_output/) for details.

---

## Configuration

### Path Configuration

The pipeline uses a flexible, configuration-driven approach for file system paths. All paths can be configured via YAML files or environment variables.

**Default paths** (relative to project root):
```
data/
├── usaspending/              # USAspending database dumps
├── transition/               # Transition detection outputs
├── raw/                      # Raw input data
└── scripts_output/          # Script outputs
```

**Configuration file** (`config/base.yaml`):
```yaml
paths:
  data_root: "data"
  usaspending_dump_file: "data/usaspending/usaspending-db_20251006.zip"
  transition_contracts_output: "data/transition/contracts_ingestion.parquet"
  scripts_output: "data/scripts_output"
```

**Key benefits:**
- ✅ **Portable**: No hardcoded paths - works across different environments
- ✅ **Flexible**: Override via environment variables for different deployments
- ✅ **Validated**: Automatic path validation on startup with helpful error messages

See [Path Configuration Guide](docs/configuration/paths.md) for complete documentation.

## CLI Interface

The SBIR CLI provides a rich command-line interface for monitoring and operating the pipeline:

```bash
# Install and verify
uv sync
uv run sbir-cli --help

# Check pipeline status
uv run sbir-cli status summary

# View metrics
uv run sbir-cli metrics latest

# Start interactive dashboard
uv run sbir-cli dashboard start
```

See [CLI Reference Guide](docs/cli/README.md) for complete documentation.

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

- Containerization guide: docs/deployment/containerization.md
- Development: `docker compose --profile dev up` (bind mounts, live reload)
- CI Testing: `docker compose --profile ci up` (ephemeral, test execution)
- Neo4j server guide: docs/neo4j/server.md

This repository includes an end-to-end CET pipeline that classifies SBIR awards into CET areas, aggregates company-level CET profiles, and loads both enrichment properties and relationships into Neo4j.

### Run the full CET pipeline

You can execute the full CET job via Dagster:

```text
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

See the Neo4j schema documentation:

- docs/references/schemas/neo4j.md

CET-specific schema details:

- CETArea node schema and constraints (defined in `src/loaders/cet_loader.py`)
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

### Research & References

### Classifier-Related Research:
- **Bayesian Mixture-of-Experts**: [Bayesian Mixture-of-Experts: Towards Making LLMs Know What They Don't Know](https://www.arxiv.org/abs/2509.23830) - Research on improving calibration and uncertainty estimation in classifier routing mechanisms
- **PaECTER**: [PaECTER - Patent Embeddings using Citation-informed TransformERs](https://huggingface.co/mpi-inno-comp/paecter) - Patent similarity model for semantic search and patent analysis tasks

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

```text
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
- **Iterative Enrichment Refresh**: Automatic freshness tracking and refresh for enrichment data (see [Iterative Enrichment](#iterative-enrichment-refresh))

###Quality Gates

Configurable thresholds enforce data quality:

```yaml

## config/base.yaml

enrichment:
  match_rate_threshold: 0.70      # Min 70% match rate

validation:
  pass_rate_threshold: 0.95       # Min 95% pass rate

loading:
  load_success_threshold: 0.99    # Min 99% load success
```

### Asset Checks:
- `enrichment_quality_regression_check` — Compare to baseline
- `patent_load_success_rate` — Verify Neo4j load success
- `assignment_load_success_rate` — Verify relationship creation

### Iterative Enrichment Refresh

**Status**: ✅ **IMPLEMENTED** - USAspending API refresh operational (Phase 1)

The iterative enrichment refresh system automatically keeps enrichment data current by periodically refreshing stale records from external APIs. This ensures data freshness without requiring full pipeline re-runs.

### Key Features
- **Automatic Refresh**: Sensor-driven refresh after bulk enrichment completes
- **Delta Detection**: Skips API calls when data is unchanged (payload hash comparison)
- **Freshness Tracking**: Tracks last attempt, last success, payload hash, and status per award/source
- **Checkpoint/Resume**: Interrupted runs can resume from last checkpoint
- **Metrics**: Coverage, success rate, staleness rate, and error rate tracking
- **CLI Tools**: Manual refresh via `scripts/refresh_enrichment.py`

**Phase 1**: USAspending API only. Other APIs (SAM.gov, NIH RePORTER, PatentsView) will be evaluated in Phase 2+.

**Documentation**: See [`docs/enrichment/usaspending-iterative-refresh.md`](docs/enrichment/usaspending-iterative-refresh.md) for detailed workflow, configuration, and troubleshooting.

## PatentsView API Integration

**Status**: ✅ **IMPLEMENTED** - PatentsView API client operational

The PatentsView API integration enables enrichment of SBIR companies with patent filing information and reassignment tracking. This helps identify which companies have filed patents and whether those patents were later reassigned to other entities.

### Key Features

- **Patent Query**: Query patents by assignee organization name
- **Reassignment Tracking**: Identify patents that were reassigned to different companies
- **Caching**: File-based caching to avoid redundant API calls
- **Rate Limiting**: Automatic rate limiting to respect API policies
- **Fuzzy Matching**: Support for company name variations

### Setup

1. **Obtain API Key**: Request a PatentsView API key from the [PatentsView Support Portal](https://patentsview-support.atlassian.net/servicedesk/customer/portals)

2. **Set Environment Variable**:
   ```bash
   export PATENTSVIEW_API_KEY=your_api_key_here
   ```

3. **Configuration**: PatentsView API settings are in `config/base.yaml`:
   ```yaml
   enrichment:
     patentsview_api:
       base_url: "https://search.patentsview.org/api"
       api_key_env_var: "PATENTSVIEW_API_KEY"
       rate_limit_per_minute: 60
       cache:
         enabled: true
         cache_dir: "data/cache/patentsview"
         ttl_hours: 24
   ```

### Usage

**Test Script**: Process companies from CSV and generate reports:

```bash
# Test first 10 companies (quick)
uv run python test_patentsview_enrichment.py --limit 10

# Test all companies
uv run python test_patentsview_enrichment.py

# Test with a different CSV file
uv run python test_patentsview_enrichment.py --dataset path/to/companies.csv

# Test specific company by UEI
uv run python test_patentsview_enrichment.py --uei ABC123DEF456

# Export results to CSV
uv run python test_patentsview_enrichment.py --output results.csv

# Generate detailed markdown report
uv run python test_patentsview_enrichment.py --markdown-report report.md
```

**Programmatic Usage**:

```python
from src.enrichers.patentsview import PatentsViewClient, retrieve_company_patents

# Initialize client
client = PatentsViewClient()

# Retrieve patents for a company
patents_df = retrieve_company_patents("Company Name", uei="UEI123", duns="123456789")

# Check for reassignments
from src.enrichers.patentsview import check_patent_reassignments
reassignments_df = check_patent_reassignments(
    patent_numbers=["12345678", "87654321"],
    original_company_name="Company Name",
    client=client
)

client.close()
```

### Output

The test script generates:
- **Summary Statistics**: Total companies, companies with patents, reassigned patents count
- **CSV Export**: Company name, UEI, DUNS, patent count, patent numbers, reassignment details
- **Markdown Report**: Detailed breakdown with patent filing timeline and reassignment analysis

### API Rate Limits

PatentsView API has a rate limit of 45 requests per minute. The client automatically handles rate limiting with exponential backoff retry logic.

### Caching

API responses are cached by default (24-hour TTL) to avoid redundant queries. Cache can be disabled or configured in `config/base.yaml`.

### Usage

```bash
# List stale awards
python scripts/refresh_enrichment.py list-stale --source usaspending

# Refresh stale awards
python scripts/refresh_enrichment.py refresh-usaspending --stale-only

# View freshness statistics
python scripts/refresh_enrichment.py stats --source usaspending
```

**Configuration**: `config/base.yaml` → `enrichment_refresh.usaspending` | **Metrics**: `reports/metrics/enrichment_freshness.json`

## Company Categorization

**Status**: ✅ **IMPLEMENTED** - Company categorization system operational

The company categorization system analyzes federal contract portfolios to classify companies as **Product-leaning**, **Service-leaning**, or **Mixed** based on their non-SBIR/STTR federal revenue. This helps identify companies that have successfully commercialized SBIR research into product sales.

### Key Features

- **Product/Service Classification**: Analyzes Product Service Codes (PSC) and contract types to classify revenue
- **SBIR Exclusion**: Excludes SBIR/STTR awards from analysis to focus on commercial revenue
- **Agency Breakdown**: Reports revenue proportions by awarding agency
- **Commercialization Detection**: Identifies companies with successful commercialization (non-R&D revenue > R&D revenue in final two years)
- **Product Commercialization**: Identifies companies with product revenue > R&D revenue in final two years
- **DuckDB Integration**: Prioritizes DuckDB bulk data, falls back to USAspending API
- **Caching**: File-based caching for API responses to avoid redundant queries

### Usage

**Test Script**: Validate categorization against high-volume SBIR companies:

```bash
# Test first 10 companies (quick)
uv run python test_categorization_validation.py --limit 10

# Test all companies
uv run python test_categorization_validation.py

# Test specific company by UEI
uv run python test_categorization_validation.py --uei ABC123DEF456

# Export results to CSV
uv run python test_categorization_validation.py --output results.csv

# Generate detailed markdown report
uv run python test_categorization_validation.py --markdown-report report.md

# Load categorized companies to Neo4j
uv run python test_categorization_validation.py --load-neo4j
```

**Programmatic Usage**:

```python
from src.enrichers.company_categorization import categorize_companies
from src.transformers.company_categorization import aggregate_company_classification

# Categorize companies from DataFrame
results = categorize_companies(companies_df)
```

### Classification Logic

Companies are classified based on:
1. **Product Service Codes (PSC)**: PSC codes indicate product vs service contracts
2. **Contract Types**: Fixed-price contracts favor products, cost-reimbursement favors services
3. **Dollar-weighted Analysis**: Classification weighted by contract dollar amounts
4. **Commercialization Signals**: Final two years of data analyzed for commercialization patterns

### Output

The test script generates:
- **Classification Results**: Product-leaning, Service-leaning, or Mixed for each company
- **Agency Breakdown**: Percentage of revenue from each awarding agency
- **Commercialization Flags**: Successful commercialization and product commercialization indicators
- **CSV Export**: Company name, UEI, classification, percentages, agency breakdown
- **Markdown Report**: Detailed analysis with justifications and evidence

**Configuration**: `config/base.yaml` → `enrichment_refresh.usaspending`

## Neo4j Schema Migration

**Status**: ✅ **AVAILABLE** - Unified schema migration scripts operational

The migration system consolidates Neo4j schema from legacy node types to a unified schema:
- **Organization**: Unified node for Company, PatentEntity, ResearchInstitution, Agency
- **Individual**: Unified node for Researcher and PatentEntity individuals
- **FinancialTransaction**: Unified node for Award and Contract
- **Relationships**: Consolidated relationship types (PARTICIPATED_IN, RECIPIENT_OF, etc.)

### Migration Scripts

**Main Migration Script**: `scripts/migration/unified_schema_migration.py`

This script orchestrates all migrations in the correct order:
1. Organization Migration (Company, PatentEntity, ResearchInstitution → Organization)
2. Individual Migration (Researcher, PatentEntity individuals → Individual)
3. FinancialTransaction Migration (Award, Contract → FinancialTransaction)
4. Participated_in Unification (RESEARCHED_BY, WORKED_ON → PARTICIPATED_IN)
5. TransitionProfile Consolidation (TransitionProfile → Organization properties)
6. Relationship Consolidation (AWARDED_TO → RECIPIENT_OF, etc.)

### Usage

```bash
# Dry run to see what would happen
uv run python scripts/migration/unified_schema_migration.py --dry-run

# Run all migrations (requires confirmation)
uv run python scripts/migration/unified_schema_migration.py

# Run all migrations (skip confirmation)
uv run python scripts/migration/unified_schema_migration.py --yes

# Skip specific steps
uv run python scripts/migration/unified_schema_migration.py --yes --skip-steps 1,2

# Optimize for speed (larger batches, more connections)
uv run python scripts/migration/unified_schema_migration.py --yes --batch-size 2000 --connection-pool-size 30
```

### Features

- **Idempotent**: All migrations use MERGE operations, safe to re-run
- **Batch Processing**: Processes large datasets in batches to prevent timeouts
- **Progress Logging**: Detailed progress logging for long-running migrations
- **Resume Support**: Can skip completed steps and resume from interruptions
- **Dry Run Mode**: Preview changes without executing

### Environment Variables

```bash
export NEO4J_URI=bolt://neo4j:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your_password
```

### Documentation

- **Migration Guides**: `docs/migration/` - Detailed guides for each migration step
- **Schema Documentation**: `docs/schemas/` - Neo4j schema documentation


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

```text
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

### CI Test Execution Strategy

The CI system optimizes test runtime with prioritized job tiers:

#### Job Priority Tiers

1. **Tier 1 (Speed)**: Fast tests run first
   - Fast unit tests (`pytest -m fast`) - completes in < 5 minutes
   - Provides immediate feedback to developers
   - All subsequent tiers depend on this passing

2. **Tier 2 (User Stories)**: Core functionality tests
   - Containerized deployment validation
   - CET pipeline E2E tests
   - Transition detection pipeline tests
   - Runs in parallel after Tier 1 passes

3. **Tier 3 (Performance)**: Performance checks (non-blocking)
   - Performance regression detection
   - Runs after user story tests
   - Does not block merges but provides valuable metrics

#### Workflow Behavior

- **PR/Commit Workflows**: Run Tier 1 immediately, Tier 2 conditionally, Tier 3 last
- **Nightly Builds**: Run comprehensive test suite in parallel (all tiers)
- **Test Markers**:
  - `@pytest.mark.fast` - Fast unit tests (< 1 second each)
  - `@pytest.mark.slow` - Slow unit tests (ML training, heavy computation)
  - `@pytest.mark.integration` - Integration tests
  - `@pytest.mark.e2e` - End-to-end tests

### Running Tests Locally

```bash

## Run all tests

uv run pytest

## Run fast tests only (matches PR/commit CI)

uv run pytest -m fast

## Run slow tests only

uv run pytest -m slow

## Run integration tests

uv run pytest -m integration

## Run E2E tests

uv run pytest -m e2e

## Run with coverage

uv run pytest --cov=src --cov-report=html

## Run specific test categories

uv run pytest tests/unit/test_config.py -v
uv run pytest tests/integration/ -v
uv run pytest tests/e2e/ -v

## Container tests

make docker-test

## E2E tests (containerized - recommended, uses ci profile)

make docker-e2e-minimal      # Quick smoke test (< 2 min)
make docker-e2e-standard     # Full validation (5-8 min)
make docker-e2e-large        # Performance test (8-10 min)
make docker-e2e-edge-cases   # Robustness test (3-5 min)

## E2E tests (direct script execution - alternative)

python scripts/run_e2e_tests.py --scenario minimal    # Quick smoke test
python scripts/run_e2e_tests.py --scenario standard   # Full validation
python scripts/run_e2e_tests.py --scenario large      # Performance test
python scripts/run_e2e_tests.py --scenario edge-cases # Robustness test
```

### Test Suite:
- 29+ tests across unit, integration, and E2E
- Coverage target: ≥80% (CI enforced)
- Serial execution: ~8-12 minutes in CI
- E2E tests: MacBook Air optimized, runs via ci profile
  - Minimal scenario: < 2 minutes, ~2GB memory
  - Standard scenario: 5-8 minutes, ~4GB memory
  - Large scenario: 8-10 minutes, ~6GB memory
  - Resource limits: 8GB total memory, 2 CPU cores

## Project Structure

```text
sbir-etl/
├── src/
│   ├── assets/                 # Dagster asset definitions (pipeline orchestration)
│   ├── config/                 # Configuration management and schemas
│   ├── extractors/             # Stage 1: Data extraction from various sources
│   ├── validators/             # Stage 2: Schema validation and data quality checks
│   ├── enrichers/              # Stage 3: External enrichment and fuzzy matching
│   ├── transformers/           # Stage 4: Business logic and graph preparation
│   ├── loaders/                # Stage 5: Neo4j loading and relationship creation
│   ├── models/                 # Pydantic data models and type definitions
│   ├── utils/                  # Shared utilities (logging, metrics, performance)
│   ├── quality/                # Data quality validation modules
│   ├── ml/                     # Machine learning models (CET classification)
│   ├── transition/             # Technology transition detection logic
│   ├── migration/              # Migration utilities
│   └── definitions.py          # Dagster repository definitions
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
│   ├── e2e_health_check.py               # E2E environment validation
│   └── migration/                        # Neo4j schema migration scripts
│       ├── unified_schema_migration.py   # Main migration orchestrator
│       ├── unified_organization_migration.py
│       ├── unified_individual_migration.py
│       ├── unified_financial_transaction_migration.py
│       └── ...
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
├── docker/                      # Docker utilities and configurations
│   ├── entrypoint.sh              # Container entrypoint script
│   ├── healthcheck.sh             # Health check script
│   └── ...                        # Additional Docker utilities
│
├── .kiro/                       # Kiro specifications (active spec system)
│   ├── specs/                   # Specification-driven development
│   └── steering/                # Agent steering documents (architectural patterns)
└── archive/                     # Archived content
    └── openspec/                # Archived OpenSpec content (historical reference)
```

## Neo4j Graph Model

### Node Types:
- `Award` — SBIR/STTR awards with company, agency, phase, amount
- `Company` — Awardee companies with contact info, location
- `Patent` — USPTO patents linked to SBIR-funded research
- `PatentAssignment` — Patent transfer transactions
- `PatentEntity` — Assignees and assignors (normalized names)

### Relationship Types:
- `RECEIVED` — Company → Award
- `GENERATED_FROM` — Patent → Award (SBIR-funded patents)
- `OWNS` — Company → Patent (current ownership)
- `ASSIGNED_VIA` — Patent → PatentAssignment
- `ASSIGNED_FROM` — PatentAssignment → PatentEntity
- `ASSIGNED_TO` — PatentAssignment → PatentEntity
- `CHAIN_OF` — PatentAssignment → PatentAssignment (ownership history)

### Query Examples:

```cypher

## Find all awards for a company

MATCH (c:Company {name: "Acme Inc"})-[:RECEIVED]->(a:Award)
RETURN a.title, a.amount, a.phase

## Trace patent ownership chain

MATCH path = (p:Patent)-[:ASSIGNED_VIA*]->(pa:PatentAssignment)
WHERE p.grant_doc_num = "7123456"
RETURN path

## Find SBIR-funded patents with assignments

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

### Performance Regression CI:
- Runs on enrichment/asset changes
- Compares to cached baseline (`reports/benchmarks/baseline.json`)
- Posts PR comment with duration/memory/match_rate deltas
- Sets GitHub Check status (success/failure)
- Uploads artifacts (regression JSON, HTML report)


## Documentation

- **Testing**: `docs/testing/e2e-testing-guide.md`
- **Data Sources**: `docs/data/index.md`, `data/raw/uspto/README.md`
- **Deployment**: `docs/deployment/containerization.md`
- **Schemas**: `docs/schemas/patent-neo4j-schema.md`
- **Specifications**: `.kiro/specs/` (Kiro specification system) - see `AGENTS.md` for workflow guidance

## Error Handling

The SBIR ETL pipeline uses a comprehensive exception hierarchy for structured error handling and debugging. All custom exceptions provide rich context including component, operation, details, and retry guidance.

### Exception Hierarchy

```
SBIRETLError (base)
├── ExtractionError              # Data extraction failures
├── ValidationError              # Schema/quality validation
│   └── DataQualityError         # Quality thresholds not met
├── EnrichmentError              # Enrichment stage failures
│   └── APIError                 # External API failures
│       └── RateLimitError       # Rate limits exceeded
├── TransformationError          # Transformation failures
│   ├── TransitionDetectionError
│   ├── FiscalAnalysisError
│   ├── CETClassificationError
│   └── PatentProcessingError
├── LoadError                    # Loading stage failures
│   └── Neo4jError               # Neo4j operations
├── ConfigurationError           # Config issues
├── FileSystemError              # File I/O operations
└── DependencyError              # Missing dependencies
    └── RFunctionError           # R function failures
```

### Usage Example

```python
from src.exceptions import ValidationError, APIError, wrap_exception

# Raise with structured context
raise ValidationError(
    "Award amount must be positive",
    component="validators.sbir",
    operation="validate_award",
    details={"award_id": "A001", "amount": -1000}
)

# Wrap external exceptions
try:
    response = httpx.get(url)
    response.raise_for_status()
except httpx.HTTPError as e:
    raise wrap_exception(
        e, APIError,
        api_name="usaspending",
        endpoint=url,
        http_status=e.response.status_code
    )
```

### Key Features

- **Structured Context**: Every exception includes component, operation, and contextual details
- **Retry Guidance**: `retryable` flag indicates whether operations should be retried
- **Error Codes**: Numeric categorization (1xxx-5xxx) for programmatic handling
- **Cause Chains**: Preserves original exception context via `cause` parameter
- **Logging Integration**: Exceptions serialize to JSON for structured logging

For detailed guidelines, see [Exception Handling Guide](docs/development/exception-handling.md) and [CONTRIBUTING.md](CONTRIBUTING.md#exception-handling).

## Contributing

1. Follow code quality standards (black, ruff, mypy, bandit)
2. Write tests for new functionality (≥80% coverage)
3. Update documentation as needed
4. Use Kiro specs for architectural changes (see `.kiro/specs/` and `AGENTS.md` for workflow)
5. Ensure performance regression checks pass in CI

## Acknowledgments

This project makes use of and is grateful for the following open-source tools and research:

### Economic Modeling

- **[StateIO](https://github.com/USEPA/stateior)** - State-level economic input-output modeling framework by USEPA
- **[USEEIOR](https://github.com/USEPA/useeior)** - Environmentally-extended input-output model builder by USEPA

### Classifier Research & Tools

- **[Bayesian Mixture-of-Experts](https://www.arxiv.org/abs/2509.23830)** - Research on calibration and uncertainty estimation in classifier routing by Albus Yizhuo Li
- **[PaECTER](https://huggingface.co/mpi-inno-comp/paecter)** - Patent similarity model by Max Planck Institute for Innovation and Competition

## License

This project is licensed under the [MIT License](LICENSE). Copyright (c) 2025 Conrad Hollomon.
