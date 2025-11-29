# SBIR ETL Codebase Architecture Overview

## Executive Summary

The **sbir-analytics** is a robust, cloud-native ETL (Extract, Transform, Load) pipeline for processing Small Business Innovation Research (SBIR) program data into a Neo4j graph database. It orchestrates multi-source data ingestion, complex transformations, and sophisticated analysis workflows through Dagster asset definitions.

**Key Characteristics:**
- **Data Sources**: SBIR.gov awards, USAspending contracts, USPTO patents, transition detection
- **Processing**: DuckDB (extraction), Pandas/Python (transformation), Neo4j Aura (cloud graph storage)
- **Orchestration**: Dagster Cloud Solo Plan (primary), AWS Step Functions (scheduled workflows)
- **Compute**: AWS Lambda functions (serverless processing), Dagster Cloud agents
- **Storage**: AWS S3 (primary data lake), local filesystem (development fallback)
- **Database**: Neo4j Aura (cloud-hosted production), Docker Neo4j (local development)
- **Deployment**: Cloud-first (Dagster Cloud + AWS + Neo4j Aura), Docker (local development)
- **Tech Stack**: Python 3.11/3.12, Neo4j 5.x, AWS Lambda, S3, DuckDB, Pandas, Pydantic, scikit-learn

---

## 1. Project Structure & Components

### 1.1 Core Directory Structure

```
sbir-analytics/
├── src/                          # Main application code
│   ├── assets/                   # Dagster asset definitions (pipeline nodes)
│   │   ├── cet/                  # CET classification pipeline
│   │   ├── transition/           # Transition detection pipeline
│   │   ├── sbir_ingestion.py     # Extract & validate SBIR awards
│   │   ├── sbir_neo4j_loading.py # Load awards into Neo4j
│   │   ├── sbir_usaspending_enrichment.py
│   │   ├── usaspending_ingestion.py
│   │   ├── usaspending_iterative_enrichment.py
│   │   ├── uspto/                # Patent processing assets
│   │   ├── fiscal_assets.py      # Fiscal returns analysis
│   │   └── jobs/                 # Composite job definitions
│   │
│   ├── extractors/               # Stage 1: Data extraction
│   │   ├── sbir.py               # SBIR CSV via DuckDB
│   │   ├── usaspending.py        # USAspending database dumps
│   │   ├── contract_extractor.py # Federal contracts
│   │   └── uspto_*.py            # USPTO patent data
│   │
│   ├── validators/               # Stage 2: Schema & quality validation
│   │   ├── sbir_awards.py        # SBIR award validation
│   │   └── schemas.py            # Pydantic validation schemas
│   │
│   ├── enrichers/                # Stage 3: External enrichment
│   │   ├── company_enricher.py   # SAM.gov company enrichment
│   │   ├── geographic_resolver.py # NAICS/GICS mapping
│   │   ├── inflation_adjuster.py # Fiscal year adjustments
│   │   ├── chunked_enrichment.py # Memory-efficient batching
│   │   └── usaspending/          # USAspending API integration
│   │
│   ├── transformers/             # Stage 4: Business logic & modeling
│   │   ├── patent_transformer.py # Patent chain processing
│   │   ├── company_cet_aggregator.py # Company-level CET profiles
│   │   ├── r_stateio_adapter.py  # Economic model interface
│   │   └── fiscal/               # Fiscal impact calculations
│   │
│   ├── loaders/                  # Stage 5: Neo4j persistence
│   │   └── neo4j/
│   │       ├── client.py         # Neo4j client wrapper
│   │       ├── cet.py            # CET loader
│   │       ├── patents.py        # Patent loader
│   │       ├── transitions.py    # Transition detector loader
│   │       └── profiles.py       # Company profile loader
│   │
│   ├── models/                   # Pydantic data models
│   │   ├── award.py              # Unified Award model
│   │   ├── company.py            # Company model
│   │   ├── cet_models.py         # CET classes
│   │   ├── patent.py             # Patent models
│   │   ├── contract_models.py
│   │   ├── transition_models.py
│   │   └── fiscal_models.py
│   │
│   ├── ml/                       # Machine learning (CET classification)
│   │   ├── config/               # Taxonomy loader
│   │   ├── models/
│   │   │   ├── cet_classifier.py # TF-IDF + LogisticRegression
│   │   │   └── patent_classifier.py
│   │   ├── features/             # Feature extraction
│   │   ├── train/                # Training pipeline
│   │   └── evaluation/           # Model evaluation
│   │
│   ├── quality/                  # Data quality checks
│   │   ├── checks.py
│   │   ├── baseline.py
│   │   └── dashboard.py
│   │
│   ├── utils/                    # Shared utilities
│   │   ├── duckdb_client.py      # DuckDB wrapper
│   │   ├── monitoring/            # Metrics & monitoring utilities
│   │   ├── enrichment_metrics.py
│   │   ├── enrichment_freshness.py
│   │   ├── text_normalization.py
│   │   └── statistical_reporter.py # Report generation
│   │
│   ├── config/                   # Configuration management
│   │   ├── loader.py             # Config loading with env overrides
│   │   └── schemas.py            # Pydantic config schemas
│   │
│   ├── cli/                      # Command-line interface
│   │   ├── main.py               # CLI entry point (sbir-cli)
│   │   └── commands/             # Command implementations
│   │
│   └── definitions.py            # Dagster repository root
│
├── config/                       # YAML configuration files
│   ├── base.yaml                 # Defaults (version controlled)
│   ├── dev.yaml                  # Development overrides
│   ├── prod.yaml                 # Production overrides
│   ├── sbir/                     # SBIR-specific configs
│   ├── transition/               # Transition detection configs
│   └── cet/                      # CET taxonomy & classification configs
│
├── tests/                        # Test suite (29+ tests)
│   ├── unit/                     # Component tests
│   ├── integration/              # Multi-component tests
│   └── e2e/                      # End-to-end pipeline tests
│
├── docs/                         # User/developer documentation
│   ├── architecture/             # Architecture decisions
│   ├── configuration/            # Configuration guides
│   ├── data-dictionaries/        # Data reference docs
│   ├── ml/                       # CET classifier docs
│   ├── neo4j/                    # Neo4j schema & queries
│   ├── schemas/                  # Data model documentation
│   ├── transition/               # Transition detection docs
│   └── references/               # Data dictionaries
│
├── .kiro/                        # Specification-driven development
│   ├── specs/                    # Active specifications (Kiro format)
│   │   ├── statistical_reporting/
│   │   ├── weekly-award-data-refresh/
│   │   ├── merger_acquisition_detection/
│   │   └── archive/              # Completed specs
│   └── steering/                 # Agent guidance documents
│
├── .github/workflows/            # CI/CD pipelines
│   ├── ci.yml                    # Standard lint/test
│   ├── container-ci.yml          # Docker build & test
│   ├── neo4j-smoke.yml           # Integration tests
│   ├── performance-regression-check.yml
│   ├── cet-pipeline-ci.yml
│   └── secret-scan.yml
│
└── docker-compose.yml            # Local dev/test environment

```

### 1.2 Key Files

| File | Purpose |
|------|---------|
| `src/definitions.py` | Dagster repository root; loads all assets and job definitions |
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
│ • Fiscal impact modeling (StateIO)
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
   ├─ fiscal_economic_impacts (StateIO modeling)
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

#### CET Classification Result

```python
class CETClassification(BaseModel):
    cet_id: str                 # e.g., "artificial_intelligence"
    cet_name: str               # Human-readable name
    score: float                # 0-100 confidence
    classification: ClassificationLevel  # HIGH/MEDIUM/LOW
    primary: bool               # True if highest score for this award
    evidence: list[EvidenceStatement]  # Supporting excerpts
    classified_at: str          # ISO 8601 timestamp
```

#### Transition Detection Result

```python
# From transition_models.py
# 6-signal composite score:
# - Agency continuity (25%)
# - Timing proximity (20%)
# - Competition type (20%)
# - Patent signal (15%)
# - CET alignment (10%)
# - Vendor match confidence (10%)
# Result: likelihood_score (0.0-1.0) + confidence band (HIGH/LIKELY/POSSIBLE)
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

**Pipeline:**

```python
# 1. Load CET Taxonomy (21 NSTC technology areas)
cet_taxonomy = load_cet_taxonomy()  # From config/cet/taxonomy.yaml

# 2. TF-IDF Feature Extraction (with keyword boosting)
class CETAwareTfidfVectorizer(TfidfVectorizer):
    """TF-IDF with CET-keyword boosting (2x multiplier)"""

    def _apply_keyword_boost(self, X):
        X_boosted = X.copy()
        X_boosted[:, keyword_indices] *= self.keyword_boost_factor
        return X_boosted

# 3. Train Multi-Label Classifier
model = Pipeline([
    ('tfidf', CETAwareTfidfVectorizer(cet_keywords=taxonomy)),
    ('feature_selection', SelectKBest(chi2, k=1000)),
    ('classifier', CalibratedClassifierCV(LogisticRegression()))
])

# 4. Classify Awards (batch)
classifications = model.predict_proba(awards['abstract'])
# Output: score (0-100), classification (HIGH/MEDIUM/LOW), evidence statements

# 5. Validate & Report
quality_check = {
    'high_conf_rate': 0.65,           # Target: ≥60%
    'evidence_coverage_rate': 0.82,   # Target: ≥80%
    'classification_threshold': 0.70  # HIGH confidence
}
```

### 3.3 Transition Detection (6-Signal Scoring)

**Algorithm:**

```python
# Detect when SBIR-funded research resulted in federal contracts

def detect_transition(award: Award, contracts: List[Contract]) -> TransitionResult:
    signals = {
        'vendor_match': compute_vendor_match_signal(award, contracts),
        'agency_continuity': compute_agency_signal(award, contracts),
        'timing_proximity': compute_timing_signal(award, contracts),
        'competition_type': compute_competition_signal(award, contracts),
        'patent_signal': compute_patent_signal(award, contracts, patents),
        'cet_alignment': compute_cet_alignment_signal(award, contracts)
    }

    # Weighted composite score
    likelihood_score = (
        0.25 * signals['agency_continuity'] +
        0.20 * signals['timing_proximity'] +
        0.20 * signals['competition_type'] +
        0.15 * signals['patent_signal'] +
        0.10 * signals['cet_alignment'] +
        0.10 * signals['vendor_match']
    )

    # Confidence classification
    confidence = (
        'HIGH'     if likelihood_score >= 0.85 else
        'LIKELY'   if likelihood_score >= 0.65 else
        'POSSIBLE'
    )

    return TransitionResult(
        award_id=award.award_id,
        contract_id=matched_contract.id,
        likelihood_score=likelihood_score,
        confidence=confidence,
        evidence={
            'signals': signals,
            'supporting_facts': [...]
        }
    )
```

**Vendor Resolution (4-step cascade):**

1. UEI exact match (confidence: 0.99)
2. CAGE code exact match (confidence: 0.95)
3. DUNS exact match (confidence: 0.90)
4. RapidFuzz fuzzy name matching (confidence: 0.65-0.85)

### 3.4 Fiscal Returns Analysis

**Economic Modeling Pipeline:**

```python
# 1. Prepare SBIR Awards (NAICS + Geography + Inflation)
fiscal_prepared_awards = prepare_awards(
    awards,
    naics_enrichment=True,
    geographic_resolution='state',
    inflation_adjustment=True,
    base_year=2023
)

# 2. Map NAICS → BEA Sectors
bea_mapped_awards = map_naics_to_bea(
    fiscal_prepared_awards,
    naics_to_bea_mapping={
        '611310': 'professional_services',
        ...
    }
)

# 3. Aggregate into Economic Shocks
shocks = aggregate_economic_shocks(
    bea_mapped_awards,
    shock_type='direct_industry_output'  # Dollar amounts by sector/region
)

# 4. Model Economic Impacts (StateIO/USEEIO via R)
impacts = compute_economic_impacts(
    shocks,
    model='stateio',
    multiplier_type='gross_output',  # Industry multipliers
    geographic_level='state'
)

# 5. Extract Tax Components
tax_components = extract_tax_components(
    impacts,
    components=[
        'wage_income',
        'proprietor_income',
        'corporate_profits'
    ]
)

# 6. Calculate Federal Tax Receipts
tax_estimates = estimate_federal_taxes(
    tax_components,
    tax_rates={
        'wage_income': 0.20,      # 20% effective federal rate
        'proprietor_income': 0.25,
        'corporate_profit': 0.21
    }
)

# 7. Compute ROI Metrics
roi = calculate_roi(
    sbir_investment=award.award_amount,
    tax_receipts=tax_estimates.total_federal_tax,
    discount_rate=0.03,
    analysis_period_years=10
)
# Output: ROI ratio, NPV, payback period, sensitivity analysis
```

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

**21 NSTC Technology Areas:**
- Artificial Intelligence & Machine Learning
- Quantum Computing
- Biotechnology
- Advanced Manufacturing
- ... (18 more)

**Classification Process:**

1. **Taxonomy Loading** (`cet_taxonomy` asset)
   - Load YAML/JSON definitions from config/cet/
   - Extract keywords for each CET area
   - Create feature mapping

2. **Award Classification** (`enriched_cet_award_classifications` asset)
   - Input: `enriched_sbir_awards` + `cet_taxonomy`
   - Model: TF-IDF + Logistic Regression (calibrated)
   - Process:
     - Vectorize award abstract/keywords/title
     - Boost CET-specific keywords (2x multiplier)
     - Predict probabilities for all 21 categories
     - Apply multi-threshold scoring (HIGH ≥70, MEDIUM 40-69, LOW <40)
     - Extract supporting evidence (top 3 excerpts per classification)
   - Output: `enriched_cet_award_classifications.parquet`
     - Columns: award_id, cet_id, score, classification, primary, evidence
   - Quality checks: High-confidence rate ≥60%, evidence coverage ≥80%

3. **Patent Classification** (`enriched_cet_patent_classifications` asset)
   - Same pipeline applied to patent titles/abstracts
   - Identifies SBIR-funded patents by CET area

4. **Company Profiling** (`transformed_cet_company_profiles` asset)
   - Aggregate award classifications to company level
   - Compute CET specialization scores
   - Rank technologies by company focus
   - Output: company-level CET profiles

5. **Neo4j Graph Loading**
   - Create `CETArea` nodes (upsert via cet_id)
   - Add enrichment properties to Award nodes
   - Create `APPLICABLE_TO` relationships (Award → CETArea)
   - Add enrichment properties to Company nodes
   - Create `SPECIALIZES_IN` relationships (Company → CETArea)

### 5.2 Transition Detection Tags

**6-Signal Scoring System:**

Each transition is flagged with:
- **Likelihood Score** (0.0-1.0 composite)
- **Confidence Band** (HIGH ≥0.85, LIKELY 0.65-0.84, POSSIBLE <0.65)
- **Signal Breakdown** (what drove the detection)
- **Evidence Bundle** (supporting facts: dates, amounts, relationships)

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
| **Orchestration** | Dagster Cloud Solo Plan | Managed workflow DAG, asset dependencies, cloud observability |
| **Compute** | AWS Lambda | Serverless compute for scheduled data refresh workflows |
| **Storage** | AWS S3 | Primary data lake for CSV files, intermediate results, artifacts |
| **Secrets Management** | AWS Secrets Manager | Secure storage for Neo4j credentials, API keys |
| **Database (Production)** | Neo4j Aura | Cloud-hosted graph database, free tier available |
| **Database (Development)** | Neo4j 5.x (Docker) | Local graph database for development and testing |
| **Data Processing** | DuckDB + Pandas | Efficient CSV/SQL processing + transformation |
| **Configuration** | Pydantic 2.x | Type-safe YAML loading with validation |
| **ML Classification** | scikit-learn | TF-IDF + Logistic Regression for CET |
| **Fuzzy Matching** | RapidFuzz 3.x | Company name matching (vendor resolution) |
| **Economic Modeling** | StateIO (R) | Input-output impact modeling via rpy2 |
| **Logging** | Loguru | Structured logging |
| **CLI** | Typer + Rich | Interactive dashboard commands |
| **Testing** | Pytest + Pytest-Cov | Unit/integration/E2E tests |
| **Local Development** | Docker + Docker Compose | Local dev/test environment (secondary deployment) |

### 6.2 Data Flow Connections (Cloud Architecture)

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
│   Dagster Cloud / Lambda Processing     │
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
│ ├─ Fiscal Analysis (StateIO via R)      │
│ ├─ Patent Chain Analysis                │
│ └─ Company Aggregation                  │
└─────────────────────┬───────────────────┘
                      ↓
┌─────────────────────────────────────────┐
│   Neo4j Aura Loading (Batch Upsert)    │
├─────────────────────────────────────────┤
│ CREATE CONSTRAINT ... UNIQUE            │
│ CREATE INDEX ...                        │
│ MERGE (node {id}) ON CREATE/MATCH ...   │
│ CREATE (n)-[rel]->(m) ...               │
└─────────────────────┬───────────────────┘
                      ↓
┌─────────────────────────────────────────┐
│   Neo4j Aura Cloud Database             │
│   (Queryable Knowledge Graph)           │
└─────────────────────────────────────────┘

Local Development Alternative:
- S3 → Local filesystem fallback (data/ directory)
- Neo4j Aura → Docker Neo4j (docker-compose.yml)
- Dagster Cloud → Local Dagster (dagster dev)
```

### 6.3 Neo4j Integration

**Production (Neo4j Aura):**

```python
# 1. Configure Neo4j Aura (Production)
neo4j_config = Neo4jConfig(
    uri=os.getenv("NEO4J_URI", "neo4j+s://xxxxx.databases.neo4j.io"),
    username=os.getenv("NEO4J_USERNAME", "neo4j"),
    password=os.getenv("NEO4J_PASSWORD"),  # Stored in AWS Secrets Manager
    database="neo4j",
    batch_size=5000
)

# Local Development Alternative
neo4j_config = Neo4jConfig(
    uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    username=os.getenv("NEO4J_USERNAME", "neo4j"),
    password=os.getenv("NEO4J_PASSWORD", "neo4j"),
    database="neo4j",
    batch_size=5000
)

# 2. Initialize Client
client = Neo4jClient(neo4j_config)

# 3. Create Schema (Constraints + Indexes)
client.create_constraints()  # UNIQUE constraints on primary keys
client.create_indexes()      # Performance indexes on common queries

# 4. Upsert Nodes (Batch Processing)
with client.session() as session:
    # Merge Award nodes
    query = """
    UNWIND $awards as award
    MERGE (a:Award {award_id: award.award_id})
    ON CREATE SET a += award, a.__created = true
    ON MATCH SET a += award
    RETURN a
    """
    session.run(query, awards=awards_list, batch_size=5000)

# 5. Create Relationships
    query = """
    MATCH (a:Award {award_id: $award_id}), (c:Company {company_id: $company_id})
    CREATE (c)-[:RECEIVED]->(a)
    """
    session.run(query, award_id="...", company_id="...")
```

**Node Types Loaded:**

| Node Type | Count | Key Properties | Relationships |
|-----------|-------|-----------------|---|
| Award | ~250K | award_id, company_name, amount, date | RECEIVED, INVOLVED_IN, APPLICABLE_TO |
| Company | ~50K | company_id (UEI/DUNS), name | RECEIVED (inverse), OWNS, SPECIALIZES_IN |
| Patent | ~2M | patent_id (grant_doc_num), title | GENERATED_FROM, OWNS, ASSIGNED_VIA |
| CETArea | 21 | cet_id, name | APPLICABLE_TO, SPECIALIZES_IN |
| Transition | ~50K | transition_id, likelihood_score | RESULTED_IN, ENABLED_BY |
| Contract | ~6M+ | contract_id (PIID) | TRANSITIONED_FROM |

**Example Queries:**

```cypher
-- Find all SBIR-funded transitions
MATCH (a:Award)-[:TRANSITIONED_TO]->(t:Transition)-[:RESULTED_IN]->(c:Contract)
WHERE t.confidence IN ["HIGH", "LIKELY"]
RETURN a.award_id, c.contract_id, t.likelihood_score
LIMIT 100

-- Identify patent-backed transitions
MATCH (a:Award)<-[:GENERATED_FROM]-(p:Patent)-[:ASSIGNED_VIA]->(pa:PatentAssignment)
  -[:ASSIGNMENT_FROM]-(assignor:PatentEntity)
  -[:ASSIGNMENT_TO]-(assignee:PatentEntity)
WHERE a.award_id = "SBIR-2020-PHASE-II-001"
RETURN p.title, assignor.name, pa.recorded_date, assignee.name

-- Company technology specialization
MATCH (c:Company {name: "Acme Inc"})-[:SPECIALIZES_IN]->(cet:CETArea)
WHERE c.cet_specialization_score > 0.7
RETURN cet.name, c.cet_specialization_score
ORDER BY c.cet_specialization_score DESC
```

---

## 7. How Data Flows to Key Integration Points

### 7.1 CET Classification Integration Points

**Where CET classification can be added/enhanced:**

1. **Input enrichment**
   - `src/assets/cet/classifications.py` → Award abstract/keywords/title
   - Currently: TF-IDF classification with keyword boosting
   - Enhancement: Could integrate LLM-based classifiers, BERT embeddings, multi-modal features

2. **Feature engineering**
   - `src/ml/models/cet_classifier.py` → TF-IDF vectorization
   - Current: Keyword boosting (2x multiplier for CET keywords)
   - Enhancement: Entity extraction, semantic similarity, domain-specific embeddings

3. **Model training**
   - `src/assets/cet/training.py` → scikit-learn pipeline
   - Current: Logistic Regression with calibration
   - Enhancement: Ensemble methods, ensemble diversity, active learning

4. **Validation/evaluation**
   - `src/assets/cet/validation.py` → Human sampling, IAA (inter-annotator agreement)
   - Current: Manual sampling, drift detection
   - Enhancement: Confidence thresholds, disagreement analysis

5. **Neo4j enrichment**
   - `src/assets/cet/loading.py` → Load CET relationships
   - Current: APPLICABLE_TO (Award→CET), SPECIALIZES_IN (Company→CET)
   - Enhancement: Temporal CET evolution, CET relationship networks

### 7.2 Transition Detection Integration Points

**Where transitions flow through the system:**

1. **Evidence collection**
   - `src/assets/transition/evidence.py` → Assemble evidence bundles
   - Contains: signal scores, timestamps, relationships

2. **Analytics computation**
   - `src/assets/transition/analytics.py` → Aggregate metrics
   - Award-level vs company-level effectiveness
   - By-agency breakdown
   - CET-focused analysis

3. **Neo4j loading**
   - `src/loaders/neo4j/transitions.py` → Load Transition nodes
   - Relationships: TRANSITIONED_TO, RESULTED_IN, ENABLED_BY

### 7.3 Fiscal Analysis Integration Points

**Economic model flow:**

```
enriched_sbir_awards (with NAICS)
    ↓
    └─→ StateIO (R models via rpy2)
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
- **Fiscal Analysis**: StateIO integration via R/rpy2 (economic rigor)

---

## 9. Key Integration Points for CET Classification Addition

### Where to Add New CET Features

1. **Model Enhancement** (`src/ml/models/cet_classifier.py`)
   - Swap TF-IDF for BERT embeddings
   - Add hierarchical classification (parent → child CET areas)
   - Integrate LLM-based probability calibration

2. **Feature Engineering** (`src/assets/cet/classifications.py`)
   - Extract entities (organizations, technologies)
   - Compute semantic similarity to CET definitions
   - Multi-modal features (if abstracts include structured data)

3. **Quality Control** (`src/assets/cet/validation.py`)
   - Drift detection (compare current vs baseline distribution)
   - Human-in-the-loop (flag low-confidence for manual review)
   - Disagreement analysis (identify model uncertainty)

4. **Neo4j Relationships** (`src/loaders/neo4j/cet.py`)
   - Add CET relationship networks (which CET areas are related)
   - Temporal evolution (track CET focus over time)
   - Strength scoring (degree of alignment per company/award)

5. **Aggregation** (`src/transformers/company_cet_aggregator.py`)
   - Company CET profiles from award classifications
   - Market positioning analysis
   - Competitive landscape by CET area

---

## 10. Performance Characteristics

### 10.1 Processing Throughput

| Stage | Dataset | Throughput | Duration |
|-------|---------|-----------|----------|
| SBIR Extraction | 250K awards | 50-100K/min | 3-5 min |
| SBIR Validation | 250K awards | 100K+/min | 2-3 min |
| Enrichment (SAM.gov) | 50K unique cos. | 600-1000/min | 50-80 min |
| CET Classification | 250K awards | 10-15K/min | 20-30 min |
| Transition Detection | 250K awards | 15-20K/min | 15-20 min |
| Fiscal Analysis | 250K awards | 5-10K/min | 30-50 min |
| Neo4j Loading | ~500K nodes + rels | 5-10K/min | 60-100 min |

### 10.2 Resource Requirements

- **Memory**: 2-6 GB (depending on chunk size)
- **Disk**: 50 GB (raw data + processed artifacts)
- **Time**: 4-6 hours for full pipeline (parallel job execution)

### 10.3 Quality Gates

- **SBIR Validation**: ≥95% pass rate
- **Enrichment Success**: ≥70% match rate (SAM.gov)
- **CET Classification**: ≥60% high-confidence (score ≥70)
- **Transition Detection**: Evidence completeness ≥80%
- **Neo4j Loading**: ≥99% successful node/relationship creation

---

## 11. Entry Points for CET Classifier Review/Integration

### Immediate Integration Opportunities

1. **Classification Asset** (`src/assets/cet/classifications.py`)
   - Input: `enriched_sbir_awards` (parquet)
   - Process: Batch classify with CET classifier
   - Output: `enriched_cet_award_classifications` (parquet)
   - **Hook**: Replace scikit-learn model with new classifier at `ApplicabilityModel` instantiation

2. **Training Data Generation** (`src/assets/cet/training.py`)
   - Input: Sample of awards + manual labels
   - Process: Generate training dataset
   - Output: `cet_award_training_dataset` (parquet)
   - **Hook**: Integrate new labeling strategy or active learning

3. **Model Evaluation** (`src/assets/cet/validation.py`)
   - Input: Classifications + human annotations
   - Process: Compute precision/recall/F1
   - Output: `validated_cet_iaa_report` (JSON)
   - **Hook**: Add new evaluation metrics or calibration analysis

4. **Drift Detection** (`src/assets/cet/validation.py`)
   - Input: Current classifications vs baseline
   - Process: Detect distribution shifts
   - Output: `validated_cet_drift_detection` (JSON)
   - **Hook**: Compare model outputs to baseline distribution

### CET Classifier API Contract

```python
# Expected interface for CET classifier integration
class CETClassifier(Protocol):
    def fit(self, X: List[str], y: List[dict]) -> None:
        """Train on award abstracts + labels"""
        pass

    def predict_proba(self, X: List[str]) -> Dict[str, float]:
        """Return {cet_id: score} for each document"""
        pass

    def get_evidence(self, X: str, cet_id: str) -> List[str]:
        """Extract supporting evidence snippets"""
        pass

# Current implementation uses sklearn Pipeline:
# TF-IDF → SelectKBest → CalibratedClassifierCV(LogisticRegression)
```

---

## Summary

The **sbir-analytics** codebase is a comprehensive, production-grade ETL system that:

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
