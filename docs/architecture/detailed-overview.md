# SBIR ETL Codebase Architecture Overview

## Executive Summary

**sbir-analytics** is an experimental ETL (Extract, Transform, Load) research pipeline for linking Small Business Innovation Research (SBIR) program data to commercialization signals in a Neo4j graph database. It orchestrates multi-source data ingestion, transformations, and exploratory analysis workflows through Dagster asset definitions. As described in the README, this is a personal side project rather than production software; the architecture below describes the current documented approach, including an optional cloud setup.

**Key Characteristics:**

- **Data Sources**: SBIR.gov awards, USAspending contracts, USPTO patents, transition detection
- **Processing**: DuckDB (extraction), Pandas/Python (transformation), Neo4j (graph storage)
- **Orchestration**: GitHub Actions and optional AWS Step Functions for documented repeatable runs
- **Compute**: GitHub Actions runners, with optional AWS Lambda functions for cloud experiments
- **Storage**: Local filesystem for development, with optional AWS S3 data lake paths
- **Database**: Neo4j via Docker for local development, with optional EC2-hosted Neo4j notes
- **Deployment**: Docker for local development, plus an experimental GitHub Actions + AWS + Neo4j EC2 deployment path
- **Tech Stack**: Python 3.11/3.12, Neo4j 5.x, AWS Lambda, S3, DuckDB, Pandas, Pydantic, scikit-learn

---

## 1. Project Structure & Components

### 1.1 Core Directory Structure

The repository now uses a hybrid layout: reusable ETL code lives in the
`sbir_etl/` library, while separately installable packages under `packages/`
cover Dagster orchestration, Neo4j graph loading, and ML/heuristic components.

```text
sbir-analytics/
├── sbir_etl/                      # Core ETL library modules
│   ├── extractors/                # Source-specific ingestion (SBIR, USAspending, USPTO, SEC, etc.)
│   ├── validators/                # Schema and data-quality validation
│   ├── enrichers/                 # External enrichment and entity-resolution helpers
│   ├── transformers/              # Business transformations and fiscal/analytic adapters
│   ├── models/                    # Shared Pydantic/domain models
│   ├── config/                    # Library configuration loading and schemas
│   ├── quality/                   # Data-quality checks and baselines
│   └── utils/                     # Shared DuckDB, monitoring, reporting, cache, and data utilities
│
├── packages/                      # Separately installable application packages
│   ├── sbir-analytics/            # Dagster orchestration package
│   │   └── sbir_analytics/
│   │       ├── assets/            # Dagster assets for ingestion, enrichment, CET, transition, fiscal, SEC, USPTO
│   │       ├── assets/jobs/       # Dagster job definitions
│   │       ├── assets/sensors/    # Dagster sensors
│   │       ├── clients/           # Orchestration-layer clients
│   │       ├── lambda/            # Lambda entry points/helpers
│   │       ├── tools/             # Analysis tool modules
│   │       └── definitions.py     # Dagster repository root
│   │
│   ├── sbir-graph/                # Neo4j graph loading and graph query utilities
│   │   └── sbir_graph/
│   │       ├── loaders/neo4j/     # Neo4j clients and loaders for awards, patents, CET, transitions, profiles
│   │       └── queries/           # Graph query helpers
│   │
│   └── sbir-ml/                   # CET and transition-related ML components
│       └── sbir_ml/
│           ├── ml/                # CET/patent classifiers, taxonomy loading, vectorizers, training helpers
│           └── transition/        # Transition detection, scoring, features, analytics, and evaluation
│
├── config/                        # YAML configuration: thresholds, paths, Neo4j, fiscal, CET, transition
├── docs/                          # Research notes, architecture, methodology, guides, schemas, deployment docs
├── specs/                         # Per-feature design notes and archived completed/superseded specs
├── examples/                      # Standalone demonstration scripts
├── notebooks/                     # Exploratory Jupyter notebooks
├── scripts/                       # One-off analysis, data, validation, CI, Docker, and operational scripts
├── infrastructure/                # AWS CDK deployment resources
├── tests/                         # Unit, integration, functional, e2e, slow, and validation tests
├── .github/workflows/             # CI/CD and scheduled workflow definitions
├── workspace.yaml                 # Dagster workspace entry point (loads sbir_analytics.definitions)
└── docker-compose.yml             # Local dev/test services
```

Older documentation may refer to top-level `assets`, `extractors`, or
`validators` directories under `packages/`. Those locations have been
consolidated: Dagster assets now live under
`packages/sbir-analytics/sbir_analytics/assets/`, and reusable ETL extractors
and validators are under `sbir_etl/extractors/` and `sbir_etl/validators/`.

### 1.2 Key Files

| File | Purpose |
|------|---------|
| `packages/sbir-analytics/sbir_analytics/definitions.py` | Dagster repository root; loads all assets and job definitions |
| `pyproject.toml` | Python dependencies (uv) + Dagster entry point |
| `config/base.yaml` | Default configuration (paths, thresholds, credentials) |
| `Dockerfile` | Multi-stage Docker build |
| `docker-compose.yml` | Local dev/test services (Dagster, Neo4j) |
| `Makefile` | Development commands (docker-build, docker-up-dev, etc.) |

---

## 2. Data Flow Through the ETL Pipeline

### 2.1 High-Level ETL Architecture

```
┌─────────────┐
│   EXTRACT   │  Raw data from multiple sources
├─────────────┤
│ • SBIR.gov CSV (DuckDB)
│ • USAspending DB dump (PostgreSQL)
│ • USPTO patents (CSV/DTA)
│ • Federal contracts (API/dumps)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  VALIDATE   │  Schema & quality checks
├─────────────┤
│ • Pydantic schema validation
│ • Data quality gates
│ • Completeness, uniqueness, validity checks
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   ENRICH    │  External API/enrichment lookups
├─────────────┤
│ • SAM.gov company enrichment
│ • USAspending match rate tracking
│ • NAICS code assignment (fiscal analysis)
│ • Geographic/state mapping
│ • Patent matching
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ TRANSFORM   │  Business logic & derived data
├─────────────┤
│ • CET classification (ML)
│ • Transition detection (6-signal scoring)
│ • Fiscal impact modeling (BEA I-O)
│ • Company-level aggregation
│ • Patent chain reconstruction
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    LOAD     │  Persist to Neo4j graph
├─────────────┤
│ • Upsert Award/Company/Patent nodes
│ • Create relationships (RECEIVED, OWNS, etc.)
│ • CET enrichment properties
│ • Transition evidence chains
└──────┴──────┘
```

### 2.2 Dagster Asset Dependency Graph

Assets are organized by **group_name** (extraction, validation, enrichment, transformation, loading):

```
1. EXTRACTION LAYER
   ├─ raw_sbir_awards (SBIR CSV via DuckDB)
   ├─ raw_usaspending_recipients (USAspending dump)
   ├─ raw_usaspending_contracts (Federal contracts)
   └─ raw_uspto_patents (Patent assignments)

2. VALIDATION LAYER
   ├─ validated_sbir_awards (Pydantic schema checks)
   ├─ validated_usaspending_contracts
   └─ patent_validations

3. ENRICHMENT LAYER
   ├─ enriched_sbir_awards (SAM.gov, USAspending)
   ├─ enriched_sbir_naics (NAICS codes)
   ├─ enriched_sbir_inflation_adjusted (Fiscal year normalization)
   └─ patent_chain_enrichment

4. TRANSFORMATION LAYER
   ├─ cet_award_classifications (ML classifier)
   ├─ cet_company_profiles (Company-level aggregation)
   ├─ transition_detections (6-signal scoring)
   ├─ transition_analytics (KPI aggregation)
   ├─ patent_sbir_links (SBIR-patent mapping)
   ├─ fiscal_economic_impacts (BEA I-O modeling)
   └─ fiscal_tax_estimates (ROI calculations)

5. NEO4J LOADING LAYER
   ├─ loaded_awards (Upsert Award nodes)
   ├─ loaded_companies (Company nodes + enrichment)
   ├─ loaded_cet_areas (CETArea nodes)
   ├─ loaded_award_cet_enrichment (CET properties)
   ├─ loaded_award_cet_relationships (APPLICABLE_TO edges)
   ├─ loaded_patents (Patent nodes)
   ├─ loaded_patent_assignments (Chain relationships)
   └─ loaded_transitions (Transition nodes + evidence)
```

### 2.3 Key Data Transformations

#### SBIR Award Data Model (Award class)

```python
class Award(BaseModel):
    # Core identifiers
    award_id: str               # Unique award ID
    company_name: str
    company_uei: str | None     # Unique Entity Identifier
    company_duns: str | None
    company_cage: str | None

    # Award details
    award_amount: float
    award_date: date
    phase: str | None           # Phase I, II, III
    agency: str | None          # Federal agency
    program: str                # SBIR or STTR

    # Contact/personnel
    principal_investigator: str | None
    contact_name: str | None

    # Enrichment fields
    usaspending_id: str | None
    fiscal_year: int | None

    # Validators: awards must have positive amount, valid dates, etc.
```


---

## 3. Data Transformation & Enrichment Mechanisms

### 3.1 Enrichment Pipeline (Stage 3)

**Multi-stage enrichment with quality gates:**

```python
# 1. SBIR Awards → USAspending Matching
enriched_sbir_awards = enrich_with_usaspending(
    raw_awards,
    match_strategy='fuzzy_name_matching',  # RapidFuzz
    confidence_threshold=0.65
)

# 2. Company Enrichment (SAM.gov)
enriched_sbir_awards = enrich_company_data(
    enriched_sbir_awards,
    api_endpoint='https://api.sam.gov/entity-information/v3',
    rate_limit=60,  # requests/minute
    retry_attempts=3
)

# 3. NAICS Codes (for Fiscal Analysis)
enriched_sbir_awards = enrich_with_naics(
    enriched_sbir_awards,
    fallback_chain=[
        'original_sbir_data',      # confidence: 0.95
        'usaspending_match',       # confidence: 0.85-0.90
        'fresh_api_lookup',        # confidence: 0.85-0.90
        'agency_defaults',         # confidence: 0.50
        'sector_fallback'          # confidence: 0.30
    ]
)

# 4. Iterative Refresh (Phase 1 - USAspending)
enriched_sbir_awards = refresh_stale_enrichment(
    enriched_sbir_awards,
    sources=['usaspending'],
    staleness_threshold_days=1,
    enable_delta_detection=True  # Skip if payload unchanged
)
```

**Quality Gates (from config/base.yaml):**

```yaml
enrichment:
  performance:
    match_rate_threshold: 0.70      # Min 70% enrichment success
    memory_threshold_mb: 2048       # Spill to disk if exceeded
    chunk_size: 25000               # Records to process in memory
    timeout_seconds: 300            # Per-chunk processing timeout
```

### 3.2 CET Classification (Machine Learning)

Awards are classified against 21 NSTC technology areas using TF-IDF + Logistic Regression with keyword boosting. See [ml/cet-integration.md](../ml/cet-integration.md) for the full data flow, model architecture, hyperparameters, and Neo4j loading details.

### 3.3 Transition Detection (6-Signal Scoring)

Six independent signals (agency continuity, timing proximity, competition type, patent signal, CET alignment, vendor match) combine into a likelihood score (0.0–1.0) with HIGH/LIKELY/POSSIBLE confidence bands. See [transition/detection-algorithm.md](../transition/detection-algorithm.md) for the full algorithm.

**Vendor Resolution (4-step cascade):**

1. UEI exact match (confidence: 0.99)
2. CAGE code exact match (confidence: 0.95)
3. DUNS exact match (confidence: 0.90)
4. RapidFuzz fuzzy name matching (confidence: 0.65–0.85)

### 3.4 Fiscal Returns Analysis

**Economic Modeling Pipeline:**

1. Prepare SBIR Awards (NAICS codes + state geography + inflation adjustment to base year 2023)
2. Map NAICS codes → BEA sectors
3. Aggregate into economic shocks (direct industry output by sector/region)
4. Apply BEA I-O multipliers (Leontief gross output, state-level)
5. Extract tax components (wage income, proprietor income, corporate profits)
6. Estimate federal tax receipts and compute ROI metrics (NPV, payback period, sensitivity analysis)

---

## 4. Data Models & Schemas

### 4.1 Core Entities

#### Award (Unified Model)

```python
# Single model supports both general and SBIR.gov CSV formats
# Field aliases enable flexibility (company vs company_name, etc.)

Award:
  - award_id (required)
  - company_name (required)
  - award_amount (required, positive float)
  - award_date (required, date)
  - program (required, "SBIR" or "STTR")
  - phase (optional: "Phase I", "Phase II", "Phase III")
  - agency (federal agency: NSF, DOD, etc.)
  - abstract, keywords, title
  - company_uei, company_duns, company_cage (identifiers)
  - principal_investigator, contact_name, contact_email
  - contract_start_date, contract_end_date
  - research_institution, ri_poc_name
  - is_hubzone, is_woman_owned, is_socially_disadvantaged
  - number_of_employees, company_website
  - usaspending_id, fiscal_year
```

#### Company

```python
Company:
  - name (required, unique)
  - duns (9 digits)
  - cage (5 characters)
  - address, city, state, zip, country
  - business_type, naics_code, naics_description
  - phone, email
  - sam_registration_status, sam_exclusion_status
  - last_updated (from SAM.gov)
```

#### CET Area (Critical & Emerging Technology)

```python
CETArea:
  - cet_id (unique, lowercase with underscores)
  - name (human-readable)
  - definition (official NSTC definition)
  - keywords (list of associated terms)
  - parent_cet_id (for hierarchical relationships)
  - taxonomy_version (e.g., "NSTC-2025Q1")
```

#### Patent

```python
Patent:
  - patent_id / grant_doc_num (primary identifier)
  - appno_doc_num (application number)
  - title, abstract
  - appno_date, pgpub_date (timeline)
  - num_inventors, num_assignees
  - sbir_funded (boolean, enriched from Award links)
  - sbir_award_phase (if SBIR-funded)
```

#### Transition Detection Result

```python
TransitionDetection:
  - transition_id (unique)
  - award_id (foreign key)
  - contract_id (federal contract)
  - likelihood_score (0.0-1.0)
  - confidence (HIGH / LIKELY / POSSIBLE)
  - detected_at (timestamp)
  - evidence (json: signals, supporting facts, metadata)
```

### 4.2 Configuration Schemas (Pydantic)

```python
# Hierarchical configuration with environment variable overrides

PipelineConfig (root):
  - pipeline: PipelineMetadata
  - paths: PathConfiguration
  - data_quality: DataQualityConfig
  - extraction: ExtractionConfig
  - enrichment: EnrichmentConfig
  - validation: ValidationConfig
  - neo4j: Neo4jConfig
  - fiscal_analysis: FiscalAnalysisConfig
  - cet: CETConfig
  - transition: TransitionConfig
  - core: CoreConfig

# Environment overrides: SBIR_ETL__<SECTION>__<KEY>=value
# Example: SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
```

---

## 5. Classification & Tagging Mechanisms

### 5.1 CET Classification System

Classifies awards and patents against 21 NSTC technology areas (TF-IDF + Logistic Regression). Outputs `APPLICABLE_TO` (Award→CETArea) and `SPECIALIZES_IN` (Company→CETArea) relationships in Neo4j.

See [ml/cet-integration.md](../ml/cet-integration.md) for the full pipeline: taxonomy loading, award/patent classification, company profiling, and Neo4j loading details.

### 5.2 Transition Detection Tags

Each detected transition carries a likelihood score (0.0–1.0), confidence band (HIGH/LIKELY/POSSIBLE), signal breakdown, and evidence bundle. See [transition/detection-algorithm.md](../transition/detection-algorithm.md) for scoring details.

**Neo4j Relationships:**

- `Award -[:TRANSITIONED_TO]-> Transition`
- `Transition -[:RESULTED_IN]-> Contract`
- `Transition -[:ENABLED_BY]-> Patent`
- `Award -[:INVOLVES_TECHNOLOGY]-> CETArea`

### 5.3 Quality Tags

**Data Quality Flags:**

- Validation status (pass/fail)
- Completeness score
- Enrichment coverage
- Confidence scores for enrichment sources
- Freshness tracking (last update timestamp)

---

## 6. Technology Stack & Integration Points

### 6.1 Core Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Orchestration** | GitHub Actions Solo Plan | Managed workflow DAG, asset dependencies, cloud observability |
| **Compute** | AWS Lambda | Serverless compute for scheduled data refresh workflows |
| **Storage** | AWS S3 | Optional cloud data lake for CSV files, intermediate results, artifacts |
| **Secrets Management** | AWS Secrets Manager | Secure storage for Neo4j credentials, API keys |
| **Database (Optional Cloud Setup)** | Neo4j (EC2) | Self-hosted graph database for cloud experiments |
| **Database (Development)** | Neo4j 5.x (Docker) | Local graph database for development and testing |
| **Data Processing** | DuckDB + Pandas | Efficient CSV/SQL processing + transformation |
| **Configuration** | Pydantic 2.x | Type-safe YAML loading with validation |
| **ML Classification** | scikit-learn | TF-IDF + Logistic Regression for CET |
| **Fuzzy Matching** | RapidFuzz 3.x | Company name matching (vendor resolution) |
| **Economic Modeling** | BEA API | Input-output impact modeling (Leontief) |
| **Logging** | Loguru | Structured logging |
| **CLI** | Typer + Rich | Interactive dashboard commands |
| **Testing** | Pytest + Pytest-Cov | Unit/integration/E2E tests |
| **Local Development** | Docker + Docker Compose | Local dev/test environment |

### 6.2 Data Flow Connections (Optional Cloud Architecture)

```
┌─────────────────────────────────────────┐
│   Data Sources                           │
├─────────────────────────────────────────┤
│ • SBIR.gov CSV (weekly downloads)        │
│ • USAspending PostgreSQL dumps          │
│ • USPTO patent files                    │
└─────────────────────┬───────────────────┘
                      ↓
┌─────────────────────────────────────────┐
│   AWS Lambda / Dagster Assets           │
│   (Download & Upload to S3)             │
└─────────────────────┬───────────────────┘
                      ↓
┌─────────────────────────────────────────┐
│   AWS S3 Data Lake                      │
├─────────────────────────────────────────┤
│ • Raw CSVs                               │
│ • Intermediate Parquet files            │
│ • Processed datasets                    │
└─────────────────────┬───────────────────┘
                      ↓
┌─────────────────────────────────────────┐
│   GitHub Actions / Lambda Processing     │
├─────────────────────────────────────────┤
│ • DuckDB extraction (S3 → DataFrame)    │
│ • Pydantic validation                   │
│ • Multi-stage enrichment                │
│   - SAM.gov API lookups                 │
│   - USAspending fuzzy matching          │
│   - NAICS code assignment               │
└─────────────────────┬───────────────────┘
                      ↓
┌─────────────────────────────────────────┐
│   S3 Enriched Data Storage              │
│   (enriched_sbir_awards.parquet)        │
└─────────────────────┬───────────────────┘
                      ↓
┌─────────────────────────────────────────┐
│   Parallel Transformations              │
├─────────────────────────────────────────┤
│ ├─ CET Classification (scikit-learn ML) │
│ ├─ Transition Detection (6-signal)      │
│ ├─ Fiscal Analysis (BEA I-O tables)     │
│ ├─ Patent Chain Analysis                │
│ └─ Company Aggregation                  │
└─────────────────────┬───────────────────┘
                      ↓
┌─────────────────────────────────────────┐
│   Neo4j Loading (Batch Upsert)         │
├─────────────────────────────────────────┤
│ CREATE CONSTRAINT ... UNIQUE            │
│ CREATE INDEX ...                        │
│ MERGE (node {id}) ON CREATE/MATCH ...   │
│ CREATE (n)-[rel]->(m) ...               │
└─────────────────────┬───────────────────┘
                      ↓
┌─────────────────────────────────────────┐
│   Neo4j Database                        │
│   (Queryable Knowledge Graph)           │
└─────────────────────────────────────────┘

Local Development Alternative:
- S3 → Local filesystem fallback (data/ directory)
- Neo4j EC2 → Docker Neo4j (docker-compose.yml)
- GitHub Actions → Local Dagster (dagster dev)
```

### 6.3 Neo4j Integration

Neo4j is loaded via batch MERGE operations from `packages/sbir-graph/sbir_graph/loaders/`. For node labels, relationship types, constraints, indexes, and example queries, see [schemas/neo4j.md](../schemas/neo4j.md).

---

## 7. How Data Flows to Key Integration Points

### 7.1 CET Classification Integration Points

Key files for CET classification:

- `packages/sbir-analytics/sbir_analytics/assets/cet/classifications.py` — award classification asset
- `packages/sbir-ml/sbir_ml/ml/models/cet_classifier.py` — `ApplicabilityModel` (TF-IDF + LR)
- `packages/sbir-analytics/sbir_analytics/assets/cet/training.py` — training data generation
- `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py` — IAA evaluation and drift detection
- `packages/sbir-analytics/sbir_analytics/assets/cet/loading.py` — Neo4j relationship loading

### 7.2 Transition Detection Integration Points

**Where transitions flow through the system:**

1. **Evidence collection**
   - `packages/sbir-analytics/sbir_analytics/assets/transition/evidence.py` → Assemble evidence bundles
   - Contains: signal scores, timestamps, relationships

2. **Analytics computation**
   - `packages/sbir-analytics/sbir_analytics/assets/transition/analytics.py` → Aggregate metrics
   - Award-level vs company-level effectiveness
   - By-agency breakdown
   - CET-focused analysis

3. **Neo4j loading**
   - `packages/sbir-graph/sbir_graph/loaders/neo4j/transitions.py` → Load Transition nodes
   - Relationships: TRANSITIONED_TO, RESULTED_IN, ENABLED_BY

### 7.3 Fiscal Analysis Integration Points

**Economic model flow:**

```
enriched_sbir_awards (with NAICS)
    ↓
    └─→ BEA API (I-O tables via REST)
        ↓
        └─→ Input-output multipliers
            ↓
            └─→ Economic shocks → impacts → tax estimates
```

---

## 8. Architecture Decisions & Patterns

### 8.1 Design Patterns

| Pattern | Implementation | Example |
|---------|---|---|
| **Asset-Based DAG** | Dagster assets with dependencies | `enriched_sbir_awards` depends on `raw_sbir_awards` |
| **Configuration as Code** | Pydantic + YAML merging | Environment variables override YAML |
| **Batch Processing** | Chunked enrichment with memory limits | `chunk_size=25000`, `memory_threshold_mb=2048` |
| **Idempotent Upserts** | Neo4j MERGE with ON CREATE/MATCH | Safe re-runs without duplicates |
| **Quality Gates** | Asset checks (Dagster asset_check) | Fail pipeline if enrichment <70% |
| **Performance Monitoring** | Context managers + metrics aggregation | Track duration, memory, record counts |
| **Iterative Enrichment** | Delta detection (payload hash comparison) | Skip API calls if data unchanged |
| **Error Handling** | Custom exception hierarchy | SBIRETLError → specific types |

### 8.2 Key Architectural Decisions (ADRs)

Located in `docs/decisions/`:

- **Configuration Management**: Unified Pydantic model with env overrides
- **Extraction Strategy**: DuckDB for SBIR CSV (10x faster than pandas)
- **Neo4j Schema**: MERGE semantics for idempotent loading
- **CET Classification**: TF-IDF + scikit-learn (not LLM-based for cost/reproducibility)
- **Transition Detection**: 6-signal composite scoring (transparency via evidence)
- **Fiscal Analysis**: BEA I-O tables via REST API (economic rigor)

---

## 9. Performance Characteristics

### 9.1 Processing Throughput

| Stage | Dataset | Throughput | Duration |
|-------|---------|-----------|----------|
| SBIR Extraction | 250K awards | 50-100K/min | 3-5 min |
| SBIR Validation | 250K awards | 100K+/min | 2-3 min |
| Enrichment (SAM.gov) | 50K unique cos. | 600-1000/min | 50-80 min |
| CET Classification | 250K awards | 10-15K/min | 20-30 min |
| Transition Detection | 250K awards | 15-20K/min | 15-20 min |
| Fiscal Analysis | 250K awards | 5-10K/min | 30-50 min |
| Neo4j Loading | ~500K nodes + rels | 5-10K/min | 60-100 min |

### 9.2 Resource Requirements

- **Memory**: 2-6 GB (depending on chunk size)
- **Disk**: 50 GB (raw data + processed artifacts)
- **Time**: 4-6 hours for full pipeline (parallel job execution)

### 9.3 Quality Gates

- **SBIR Validation**: ≥95% pass rate
- **Enrichment Success**: ≥70% match rate (SAM.gov)
- **CET Classification**: ≥60% high-confidence (score ≥70)
- **Transition Detection**: Evidence completeness ≥80%
- **Neo4j Loading**: ≥99% successful node/relationship creation

---

## Summary

The **sbir-analytics** codebase is an experimental research ETL system that currently:

1. **Ingests** multi-source government data (SBIR awards, USAspending, USPTO patents)
2. **Validates & Enriches** with external APIs and ML classification
3. **Transforms** into domain-specific insights (CET classification, transition detection, fiscal analysis)
4. **Loads** into Neo4j for complex relationship analysis
5. **Orchestrates** via Dagster with observable asset dependencies and quality gates

**CET classification** is fully integrated as an ML-based asset with:

- Taxonomy loading from YAML configs
- TF-IDF feature extraction with keyword boosting
- Logistic regression classification (21 categories)
- Evidence extraction (supporting excerpts)
- Quality validation (high-confidence rate, coverage thresholds)
- Neo4j loading (APPLICABLE_TO, SPECIALIZES_IN relationships)

The system is designed for extensibility, allowing new classifiers, enrichment strategies, and analysis methods to be integrated through well-defined asset interfaces and configuration schemas.
