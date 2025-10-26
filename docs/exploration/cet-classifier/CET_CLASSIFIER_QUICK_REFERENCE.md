# SBIR CET Classifier - Quick Reference Guide

## Overview at a Glance

**Project**: Production-ready ML system for classifying SBIR awards against 21 Critical and Emerging Technology areas

**Status**: ✅ Production Ready | **Tests**: 232/232 passing | **Coverage**: >85% | **Performance**: All SLAs exceeded

---

## Architecture Diagram

```
SBIR Awards Data
       ↓
┌──────────────────────────────────────────────────┐
│  1. DATA INGESTION (bootstrap.py)                │
│     - CSV validation & normalization             │
│     - Agency code mapping                        │
│     - State/date standardization                 │
└──────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────┐
│  2. ENRICHMENT (enrichment.py, lazy)             │
│     - NIH API integration (no auth required)     │
│     - SQLite cache (90% hit rate)                │
│     - Fallback handling                          │
└──────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────┐
│  3. CLASSIFICATION (applicability.py)            │
│     ┌─ TF-IDF Vectorization (trigrams)          │
│     ├─ Feature Selection (chi-squared)          │
│     ├─ Logistic Regression (balanced weights)   │
│     └─ Probability Calibration (sigmoid)        │
│                                                  │
│     Output: 0-100 score + confidence band       │
└──────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────┐
│  4. EVIDENCE EXTRACTION (evidence.py)            │
│     - spaCy sentence extraction                 │
│     - CET keyword matching                      │
│     - 50-word excerpt generation                │
│     - Source location tracking                  │
└──────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────┐
│  5. STORAGE (Parquet format)                    │
│     - awards.parquet                            │
│     - assessments.parquet                       │
│     - taxonomy.parquet                          │
└──────────────────────────────────────────────────┘
```

---

## Classification Pipeline

```
Award Text
    ↓
TF-IDF (50k → 20k features)
    ├─ Unigrams: individual terms
    ├─ Bigrams: 2-word phrases
    └─ Trigrams: 3-word technical combinations
    ↓
Feature Selection (Chi-squared)
    └─ Reduces noise, improves performance
    ↓
Logistic Regression
    ├─ Balanced class weights
    ├─ Multi-core processing
    └─ Returns probability per CET category
    ↓
Probability Calibration
    └─ Sigmoid method (3-fold CV)
    ↓
Score Conversion (0-100)
    ├─ High: 70-100
    ├─ Medium: 40-69
    └─ Low: 0-39
```

---

## Key Statistics

| Metric | Value | Target |
|--------|-------|--------|
| **Success Rate** | 97.9% | ≥95% ✅ |
| **Per-Award Latency** | 0.17ms | ≤500ms ✅ |
| **Portfolio Summary** | <1 min | ≤3 min ✅ |
| **Award Drill-down** | <5 min | ≤5 min ✅ |
| **Export (50k awards)** | <5 min | ≤10 min ✅ |
| **Throughput** | 5,979 rec/s | Baseline |
| **Test Pass Rate** | 100% (232/232) | ≥95% ✅ |

---

## CET Categories (21 Total)

```
CORE TECHNOLOGIES
├─ Artificial Intelligence
├─ Quantum Computing
│  └─ Quantum Sensing (child)
├─ Hypersonics
├─ Advanced Materials
│  └─ Thermal Protection (child)
├─ Semiconductors & Microelectronics
├─ Advanced Communications (5G/6G)
├─ Autonomous Systems
└─ Space Technology

ENERGY & ENVIRONMENT
├─ Energy Storage
├─ Renewable Energy
└─ Environmental Technology

BIOLOGY & MEDICINE
├─ Biotechnology
└─ Medical Devices

DEFENSE & SECURITY
├─ Cybersecurity
├─ Directed Energy
├─ Hypersonics (also here)
└─ Human-Machine Interface

DATA & ANALYTICS
├─ Data Analytics & Visualization

MANUFACTURING
└─ Advanced Manufacturing

UNCATEGORIZED
└─ None / Uncategorized
```

---

## Configuration Files (YAML)

### taxonomy.yaml
```yaml
# 21 CET categories with definitions and keywords
categories:
  - id: artificial_intelligence
    name: Artificial Intelligence
    definition: "AI and machine learning technologies..."
    keywords:
      - artificial intelligence
      - machine learning
      - neural networks
      - deep learning
```

### classification.yaml
```yaml
# ML model hyperparameters
vectorizer:
  ngram_range: [1, 3]      # Trigrams
  max_features: 50000
  min_df: 2
  max_df: 0.95

feature_selection:
  method: chi2
  k: 20000

classifier:
  max_iter: 500
  solver: lbfgs
  n_jobs: -1               # Multi-core

scoring:
  bands:
    high: {min: 70, max: 100}
    medium: {min: 40, max: 69}
    low: {min: 0, max: 39}
```

### enrichment.yaml
```yaml
# External API integration and mappings
nih_matcher:
  amount_tolerance_min: 0.9
  amount_tolerance_max: 1.1
  similarity_threshold: 0.5

topic_domains:
  AI: Artificial Intelligence
  BC: Biological/Chemical
  BT: Biotechnology
  # ... 15 more NSF topic codes
```

---

## Data Models (Pydantic Schemas)

### Award (Input)
```python
class Award:
    award_id: str
    agency: str              # "DOD", "NSF", "NIH"
    abstract: str|None
    keywords: list[str]
    phase: Literal["I", "II", "III", "Other"]
    firm_name: str
    award_amount: float
    award_date: date
```

### ApplicabilityAssessment (Output)
```python
class ApplicabilityAssessment:
    award_id: str
    primary_cet_id: str      # "artificial_intelligence"
    score: int               # 0-100
    classification: str      # "High", "Medium", "Low"
    supporting_cet_ids: list[str]     # Top 3
    evidence_statements: list[EvidenceStatement]
    assessed_at: datetime
```

### EvidenceStatement (Supporting Details)
```python
class EvidenceStatement:
    excerpt: str             # ≤50 words
    source_location: str     # "abstract", "keywords", etc
    rationale_tag: str       # Why this relates to CET
```

---

## Core Source Files

| File | Purpose | Key Classes |
|------|---------|------------|
| `models/applicability.py` | ML classification pipeline | `ApplicabilityModel`, `ApplicabilityScore` |
| `models/enhanced_vectorization.py` | CET-aware text processing | `CETAwareTfidfVectorizer` |
| `features/summary.py` | Portfolio analytics | `SummaryService` |
| `features/awards.py` | Award listing/filtering | `AwardsService` |
| `features/enrichment.py` | Lazy enrichment orchestration | `EnrichmentOrchestrator` |
| `features/evidence.py` | Evidence extraction | `extract_evidence_sentences()` |
| `data/bootstrap.py` | CSV data ingestion | `load_bootstrap_csv()` |
| `common/schemas.py` | Data models | `Award`, `ApplicabilityAssessment` |
| `common/yaml_config.py` | Configuration loading | `load_taxonomy_config()`, etc |
| `evaluation/reviewer_agreement.py` | Quality metrics | `ReviewerAgreementEvaluator` |

---

## API Endpoints

```bash
# Health check
GET /health
→ {"status": "ok"}

# Portfolio summary
GET /applicability/summary?fiscal_year_start=2023&fiscal_year_end=2025&cet_area=artificial_intelligence
→ Aggregated CET portfolio with counts, funding, top awards

# Award list
GET /applicability/awards?fiscal_year_start=2023&fiscal_year_end=2025&page=1
→ Paginated award list with CET classifications

# Award detail
GET /applicability/awards/{award_id}
→ Award + assessment with evidence statements

# Create export
POST /applicability/exports
→ Trigger background export job

# Export status
GET /applicability/exports/{export_id}
→ Export progress and download link
```

---

## CLI Commands

```bash
# Portfolio summary
python -m sbir_cet_classifier.cli.app summary \
  --fiscal-year-start 2023 --fiscal-year-end 2025

# Award listing
python -m sbir_cet_classifier.cli.app awards list \
  --fiscal-year-start 2023 --fiscal-year-end 2025 \
  --cet-areas artificial_intelligence --page 1

# Export data
python -m sbir_cet_classifier.cli.app export \
  --fiscal-year-start 2023 --fiscal-year-end 2025 \
  --format csv --output-file awards.csv

# Enrichment
python -m sbir_cet_classifier.cli.app enrichment enrich \
  --fiscal-year 2024 --max-workers 4
```

---

## Testing

```bash
# All tests
pytest tests/ -v
→ 232/232 passing

# Unit tests only
pytest tests/unit/ -v
→ 130 tests

# Integration tests
pytest tests/integration/ -v
→ 27 tests

# Contract tests
pytest tests/contract/ -v
→ 5 tests

# With coverage
pytest tests/ --cov=src/sbir_cet_classifier --cov-report=html
```

---

## Integration Checklist

- [ ] Read CET_CLASSIFIER_ANALYSIS.md (this document's companion)
- [ ] Review source code: models/applicability.py
- [ ] Review data models: common/schemas.py
- [ ] Review service pattern: features/summary.py
- [ ] Review configuration system: common/yaml_config.py
- [ ] Review configuration files: config/{taxonomy,classification,enrichment}.yaml
- [ ] Run sample classification workflow
- [ ] Design integration architecture (standalone vs embedded)
- [ ] Define interface contracts
- [ ] Plan configuration sharing
- [ ] Implement integration module
- [ ] Write integration tests
- [ ] Validate with real data
- [ ] Document integration patterns

---

## Performance Optimizations

**Applied in Phase O**:
- Agency name normalization: +25% data recovery
- Batch validation with pandas vectorization: +40% recovery
- N-gram features (trigrams): Better technical phrase capture
- Feature selection (50k → 20k features): Reduced overfitting
- Class weight balancing: Better minority category handling
- Parallel scoring: 2-4x faster with multi-core

**Result**: 5,979 records/second throughput, 0.17ms per-award latency

---

## Design Patterns Used

1. **Service Layer Pattern** - Isolate business logic from I/O
2. **Repository Pattern** - Abstract storage operations
3. **Registry Pattern** - Manage global service configuration
4. **Strategy Pattern** - Pluggable enrichment strategies
5. **Dependency Injection** - Testable, decoupled components
6. **Configuration Management** - Externalized YAML configs
7. **Lazy Loading** - On-demand enrichment with caching

---

## Dependencies

```
pandas>=2.2              # Data processing
scikit-learn>=1.4        # ML pipeline
spacy>=3.7               # NLP
pydantic>=2.5            # Data validation
typer>=0.12              # CLI
fastapi>=0.110           # Web API
pyarrow>=15.0            # Parquet storage
httpx>=0.27              # HTTP client
pyyaml>=6.0              # YAML config
tenacity>=8.2.0          # Retry logic
```

---

## Environment Variables

```bash
SBIR_RAW_DIR=data/raw                    # Input data location
SBIR_PROCESSED_DIR=data/processed        # Output location
SBIR_ARTIFACTS_DIR=artifacts             # Telemetry storage
SBIR_BATCH_SIZE=100                      # Batch processing size
SBIR_MAX_WORKERS=4                       # Parallel workers
```

---

## Key Learnings for Integration

1. **Externalize Configuration**: Use YAML files, not code constants
2. **Type Everything**: Comprehensive type hints improve maintainability
3. **Test Pyramid**: Unit → Integration → Contract tests
4. **Lazy Enrichment**: On-demand processing with caching > upfront enrichment
5. **Graceful Degradation**: Continue without enrichment, not fail
6. **Service Orientation**: Dependency injection for testability
7. **Evidence Tracking**: Always include rationale for classifications
8. **Performance First**: Profile and optimize early

---

## Support Resources

- **Main Docs**: README.md, DEVELOPMENT.md, STATUS.md
- **Configuration**: config/README.md
- **Source Code**: /src/sbir_cet_classifier/
- **Tests**: /tests/ (232 tests, good examples)
- **Historical Analysis**: /docs/archive/ (20+ reports)

---

## Next Steps

1. **Review** this quick reference guide (5 min)
2. **Read** CET_CLASSIFIER_ANALYSIS.md (30-60 min)
3. **Study** key source files in sbir-cet-classifier
4. **Run** sample classification workflow
5. **Plan** integration approach
6. **Design** interface contracts
7. **Implement** integration module
8. **Validate** with full SBIR dataset

