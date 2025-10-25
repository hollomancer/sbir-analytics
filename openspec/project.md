# Project Context

## Purpose

This project implements an ETL (Extract, Transform, Load) pipeline for processing SBIR (Small Business Innovation Research) program data into a Neo4j graph database. The pipeline ingests data from multiple government sources to create a comprehensive knowledge graph tracking:

- **Company Performance**: SBIR/STTR award recipients and their outcomes
- **Technology Transition**: Commercialization and adoption of research
- **Critical & Emerging Technologies**: Technology maturation and development
- **Patents**: Intellectual property generated from SBIR funding
- **Researchers & Principal Investigators**: Key personnel and their contributions

The goal is to enable graph-based analysis and queries to understand relationships between companies, technologies, researchers, and outcomes in the SBIR ecosystem.

## Tech Stack

### Core Technologies
- **Python 3.11+**: Primary language for data processing and transformations
- **Dagster**: Asset-based orchestration and workflow management
- **Neo4j**: Graph database for storing processed data and relationships
- **Docker**: Containerization for deployment and reproducibility
- **pandas**: Data manipulation and cleaning
- **neo4j-driver**: Python driver for Neo4j database operations

### Data Processing
- **DuckDB**: In-memory analytical database for fast querying and enrichment of large datasets, such as the 51GB USAspending database.

### Development Tools
- **pytest**: Testing framework
- **black**: Code formatting
- **ruff**: Fast Python linter
- **mypy**: Static type checking
- **poetry** or **pip-tools**: Dependency management

## Project Conventions

### Code Style
- **Python Style**: Follow PEP 8 with black formatting (line length: 100)
- **Type Hints**: Required for all function signatures and public APIs
- **Naming Conventions**:
  - Snake_case for functions, variables, and file names
  - PascalCase for classes
  - UPPER_CASE for constants
  - Descriptive names reflecting data domain (e.g., `sbir_award`, `patent_citation`)

### Architecture Patterns

#### ETL Pipeline Structure
```
src/
├── extractors/      # Data extraction from sources (APIs, CSVs, dumps)
├── transformers/    # Data cleaning, normalization, enrichment
├── loaders/         # Loading into Neo4j with relationship creation
├── models/          # Pydantic models for data validation
├── assets/          # Dagster asset definitions
└── utils/           # Shared utilities and helpers
```

#### Key Patterns
- **Asset-Based Design**: Each data entity (companies, patents, awards) is a Dagster asset
- **Idempotency**: All transformations should be repeatable with same results
- **Schema Validation**: Use Pydantic models to validate data before loading
- **Graph Modeling**: Design Neo4j nodes and relationships to reflect domain entities
- **Error Handling**: Graceful degradation with comprehensive logging for data quality issues

### Testing Strategy

Following the **Testing Pyramid Structure** pattern from production SBIR projects:

#### Three-Layer Testing Approach
```
         /\
        /E2E\      End-to-End Tests (~5-10% of tests)
       /------\    - Full pipeline execution
      /  INT   \   Integration Tests (~15-20% of tests)
     /----------\  - Cross-module workflows
    /    UNIT    \ Unit Tests (~70-80% of tests)
   /--------------\- Isolated function testing
```

**Unit Tests** (Fast, Isolated)
- Test individual transformers, validators, and utilities
- Mock external dependencies (APIs, databases)
- Coverage: Individual functions, edge cases, error handling
- Example: `test_clean_company_name()`, `test_parse_award_date()`

**Integration Tests** (Medium Speed)
- Test extraction → transformation → loading workflows
- Use test database instances or in-memory databases
- Validate cross-module interactions
- Example: `test_sbir_award_to_neo4j_flow()`

**End-to-End Tests** (Slow, Full Pipeline)
- Full Dagster asset materialization with sample datasets
- Validate complete data lineage and relationships
- Test idempotency and incremental updates
- Example: `test_complete_sbir_ingestion_pipeline()`

**Data Quality Tests**
- Dagster asset checks for:
  - Completeness (required fields present)
  - Uniqueness (primary key constraints)
  - Referential integrity (foreign key validation)
  - Value ranges (amounts > 0, dates in valid range)
  - Coverage metrics (% of records successfully processed)

**Test Fixtures**
- Maintain representative sample datasets for each source
- Include edge cases (missing data, duplicates, malformed records)
- Store in `tests/fixtures/` directory

**Coverage Targets**
- Overall: ≥85% code coverage
- Core transformation logic: ≥90%
- Extractors/Loaders: ≥80%
- Utilities: ≥95%

**Test Execution**
```bash
# Run all tests
pytest tests/

# Run specific layer
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Generate coverage report
pytest --cov=src --cov-report=html
```

### Git Workflow
- **Branching**: Feature branches from `main` (e.g., `feature/add-patent-extractor`)
- **Commits**: Conventional commits format (`feat:`, `fix:`, `refactor:`, `docs:`)
- **Pull Requests**: Required for all changes with automated tests passing
- **Code Review**: At least one approval before merging

## Domain Context

### SBIR/STTR Program Knowledge
- **SBIR**: Small Business Innovation Research program providing phased funding (Phase I: $50-250k, Phase II: $750k-1.5M, Phase III: non-SBIR funded commercialization)
- **STTR**: Small Business Technology Transfer, similar but requires research institution partnership
- **Agencies**: Multiple agencies participate (DOD, NIH, NASA, NSF, DOE, etc.)
- **Solicitations**: Periodic topic releases with specific technology needs

### Key Data Entities and Relationships
- **Companies** ← awarded ← **Awards** → associated with → **Topics**
- **Awards** → generate → **Patents**
- **Principal Investigators** → lead → **Awards** → affiliated with → **Institutions**
- **Technologies** → mature through → **Awards** → transition to → **Programs**
- **Companies** → cite → **Patents** → reference → **Prior Art**

### Data Quality Challenges
- **Inconsistent Naming**: Same company/person referenced with variations
- **Missing Data**: Incomplete records in government databases
- **Duplicates**: Same entities appearing multiple times across sources
- **Temporal Issues**: Awards span decades with changing data formats
- **Entity Resolution**: Linking records across different data sources

## Important Constraints

### Technical Constraints
- **Data Volume**: Expect 250k+ awards, 2.5M+ relationships
- **API Rate Limits**: Government APIs may have throttling (respect rate limits)
- **Memory Limits**: Large CSV files may require chunked processing
- **Neo4j Resources**: Graph queries must be optimized for performance

### Data Constraints
- **PII Handling**: Be cautious with personal information about researchers
- **Data Freshness**: Some sources updated quarterly, others annually
- **Data Retention**: Historical data must be preserved (append-only where possible)
- **Licensing**: Respect terms of use for government data sources

### Business Constraints
- **Reproducibility**: Pipeline runs must be auditable and reproducible
- **Data Provenance**: Track source and transformation lineage for each data point
- **Update Cadence**: Support incremental updates without full reprocessing

## Initial Setup

- **Initial Data Load**: The initial data load will be from CSV files for both SBIR and USAspending data.
- **Data Enrichment**: The data will be enriched with information from the SAM.gov API.

## External Dependencies

### Data Sources
- **SBIR.gov API**: Primary source for award data and company information (initially CSV, will transition to API)
- **USPTO Bulk Data**: Patent data and citations
- **USASpending.gov**: Federal spending and contract data (initially CSV, will transition to API)
- **SAM.gov API**: System for Award Management (SAM) API for entity information
- **Agency-Specific Databases**: DOD SBIR portal, NIH RePORTER, NASA SBIR/STTR
- **CSV/Excel Exports**: Various one-time data dumps from agencies

### Services
- **Neo4j Database**: Graph database instance (Aura or self-hosted)
- **Dagster Cloud** (optional): Hosted orchestration platform
- **Docker Registry**: For storing container images

### APIs and Libraries
- **requests**: HTTP client for API calls
- **neo4j-driver**: Official Neo4j Python driver
- **dagster**: Orchestration framework
- **pandas**: Data manipulation
- **pydantic**: Data validation
- **python-dotenv**: Environment configuration management
- **duckdb**: In-memory analytical database library
- **rich**: Terminal UI with progress bars and formatted output
- **loguru**: Structured logging with context
- **tenacity**: Retry logic with exponential backoff

---

## Design Patterns & Best Practices

The following patterns are extracted from production SBIR projects and should be implemented throughout this codebase.

### 1. Configuration Management Architecture

**Three-Layer Configuration System** for flexibility and type safety:

```
Layer 1: YAML Files (config/)
    ↓
Layer 2: Pydantic Validation (src/config/schemas.py)
    ↓
Layer 3: Runtime Configuration with Environment Overrides
```

#### Implementation Structure

**Directory Layout:**
```
config/
├── base.yaml              # Base configuration (checked into git)
├── dev.yaml               # Development overrides
├── staging.yaml           # Staging environment settings
├── prod.yaml              # Production configuration
└── README.md              # Configuration documentation
```

**Configuration Schema (src/config/schemas.py):**
```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

class DataQualityConfig(BaseModel):
    """Data quality validation thresholds."""
    max_duplicate_rate: float = Field(0.10, ge=0.0, le=1.0)
    max_missing_rate: float = Field(0.15, ge=0.0, le=1.0)
    enable_duplicate_check: bool = True
    enable_amount_validation: bool = True
    min_award_amount: float = Field(0.0, ge=0.0)

class EnrichmentConfig(BaseModel):
    """External API enrichment settings."""
    sam_gov_api_key: Optional[str] = None
    max_retries: int = Field(3, ge=1, le=10)
    timeout_seconds: int = Field(30, ge=5, le=300)
    batch_size: int = Field(100, ge=1, le=1000)
    rate_limit_per_second: float = Field(10.0, ge=0.1)

class PipelineConfig(BaseModel):
    """Main pipeline configuration."""
    data_quality: DataQualityConfig
    enrichment: EnrichmentConfig
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    chunk_size: int = Field(10000, ge=100)
    enable_incremental: bool = True
    log_level: str = Field("INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
```

**Configuration Loader (src/config/loader.py):**
```python
import yaml
import os
from pathlib import Path
from functools import lru_cache
from .schemas import PipelineConfig

@lru_cache(maxsize=1)
def load_config(env: str = None) -> PipelineConfig:
    """Load and merge configuration files with environment overrides.

    Priority order:
    1. Environment variables (SBIR_ETL_*)
    2. Environment-specific YAML (config/{env}.yaml)
    3. Base YAML (config/base.yaml)

    Args:
        env: Environment name (dev/staging/prod). Defaults to SBIR_ETL_ENV.

    Returns:
        Validated PipelineConfig instance.
    """
    env = env or os.getenv("SBIR_ETL_ENV", "dev")
    config_dir = Path(__file__).parent.parent.parent / "config"

    # Load base configuration
    base_path = config_dir / "base.yaml"
    with open(base_path) as f:
        config_data = yaml.safe_load(f)

    # Merge environment-specific overrides
    env_path = config_dir / f"{env}.yaml"
    if env_path.exists():
        with open(env_path) as f:
            env_config = yaml.safe_load(f)
            config_data = deep_merge(config_data, env_config)

    # Apply environment variable overrides
    config_data = apply_env_overrides(config_data, prefix="SBIR_ETL_")

    # Validate with Pydantic
    return PipelineConfig(**config_data)

def apply_env_overrides(config: dict, prefix: str) -> dict:
    """Apply environment variable overrides to nested config.

    Example: SBIR_ETL__DATA_QUALITY__MAX_DUPLICATE_RATE=0.05
    Overrides: config["data_quality"]["max_duplicate_rate"] = 0.05
    """
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue

        # Parse nested path: SBIR_ETL__SECTION__SUBSECTION__KEY
        path = key[len(prefix):].lower().split("__")
        set_nested_value(config, path, coerce_type(value))

    return config
```

**Example Configuration (config/base.yaml):**
```yaml
data_quality:
  max_duplicate_rate: 0.10        # 10% duplicate tolerance
  max_missing_rate: 0.15           # 15% missing data tolerance
  enable_duplicate_check: true
  enable_amount_validation: true
  min_award_amount: 0.0

enrichment:
  sam_gov_api_key: null            # Set via env var or override
  max_retries: 3
  timeout_seconds: 30
  batch_size: 100
  rate_limit_per_second: 10.0

neo4j_uri: "bolt://localhost:7687"
neo4j_user: "neo4j"
neo4j_password: null               # Set via env var

chunk_size: 10000
enable_incremental: true
log_level: "INFO"
```

**Environment Variable Overrides:**
```bash
# Override nested configuration values
export SBIR_ETL_ENV=prod
export SBIR_ETL__NEO4J_PASSWORD=secret_password
export SBIR_ETL__DATA_QUALITY__MAX_DUPLICATE_RATE=0.05
export SBIR_ETL__ENRICHMENT__SAM_GOV_API_KEY=abc123xyz
export SBIR_ETL__LOG_LEVEL=DEBUG
```

**Benefits:**
- Type-safe configuration with Pydantic validation
- Environment-specific overrides without code changes
- Secret management via environment variables
- Clear documentation of all parameters
- Easy testing with configuration injection

---

### 2. Multi-Stage Data Pipeline Design

**Five-Stage ETL Architecture** with clear separation of concerns:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   EXTRACT   │────▶│   VALIDATE  │────▶│  ENRICH     │────▶│  TRANSFORM  │────▶│    LOAD     │
│             │     │             │     │             │     │             │     │             │
│ Download    │     │ Schema      │     │ SAM.gov API │     │ Normalize   │     │ Neo4j       │
│ CSV/API     │     │ Quality     │     │ USPTO Data  │     │ Standardize │     │ Nodes/Edges │
│ Parse       │     │ Dedup       │     │ Text Enrich │     │ Calculate   │     │ Indexes     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │                   │                   │
      ▼                   ▼                   ▼                   ▼                   ▼
  raw/*.csv         validated/           enriched/           transformed/        Neo4j Database
  raw/*.json        ├─ pass/             ├─ success/         ├─ companies/
                    └─ fail/             └─ partial/         ├─ awards/
                                                              └─ patents/
```

#### Stage 1: Extract
**Purpose:** Download and parse raw data from sources
**Inputs:** URLs, file paths, API endpoints
**Outputs:** Raw CSV/JSON files in `data/raw/`
**Dagster Assets:** `raw_sbir_awards`, `raw_usaspending_contracts`, `raw_patent_data`

**Quality Gates:**
- File download success
- Basic parsing validation
- Record counts logged

#### Stage 2: Validate
**Purpose:** Schema validation and initial quality checks
**Inputs:** Raw files from Stage 1
**Outputs:** Validated data in `data/validated/pass/`, failures in `data/validated/fail/`
**Dagster Assets:** `validated_sbir_awards`, `validated_contracts`

**Quality Gates:**
- Required columns present
- Data types correct
- Primary key uniqueness
- Duplicate detection
- Missing value thresholds
- Value range validation

#### Stage 3: Enrich
**Purpose:** Augment data with external sources
**Inputs:** Validated data from Stage 2
**Outputs:** Enriched data in `data/enriched/`
**Dagster Assets:** `enriched_sbir_awards`, `enriched_companies`

**Quality Gates:**
- Enrichment success rate (target: ≥90%)
- API call success/failure tracking
- Coverage metrics by enrichment source

#### Stage 4: Transform
**Purpose:** Business logic, calculations, standardization
**Inputs:** Enriched data from Stage 3
**Outputs:** Graph-ready entities in `data/transformed/`
**Dagster Assets:** `transformed_companies`, `transformed_awards`, `transformed_patents`

**Quality Gates:**
- Business rule validation
- Referential integrity
- Completeness checks
- Transformation success rate

#### Stage 5: Load
**Purpose:** Write to Neo4j with relationships
**Inputs:** Transformed entities from Stage 4
**Outputs:** Neo4j nodes and relationships
**Dagster Assets:** `neo4j_companies`, `neo4j_awards`, `neo4j_patents`

**Quality Gates:**
- Load success rate
- Relationship creation validation
- Index creation
- Constraint enforcement

#### Pipeline Orchestration with Dagster

**Asset Dependencies:**
```python
from dagster import asset, AssetExecutionContext

@asset
def raw_sbir_awards(context: AssetExecutionContext) -> pd.DataFrame:
    """Extract: Download SBIR awards from CSV."""
    # Implementation
    return df

@asset
def validated_sbir_awards(
    context: AssetExecutionContext,
    raw_sbir_awards: pd.DataFrame
) -> pd.DataFrame:
    """Validate: Check schema and quality."""
    # Implementation
    return validated_df

@asset
def enriched_sbir_awards(
    context: AssetExecutionContext,
    validated_sbir_awards: pd.DataFrame,
    config: PipelineConfig
) -> pd.DataFrame:
    """Enrich: Add SAM.gov data."""
    # Implementation
    return enriched_df

# ... continue chain
```

**Benefits:**
- Clear stage boundaries with quality gates
- Easy debugging (inspect intermediate outputs)
- Parallel execution where possible
- Incremental processing support
- Audit trail of data lineage

---

### 3. Data Quality Framework

**Comprehensive quality assurance** at every pipeline stage.

#### Quality Dimensions

| Dimension | Definition | Validation Method | Target |
|-----------|------------|-------------------|--------|
| **Completeness** | Required fields populated | Not null checks, coverage % | ≥95% |
| **Uniqueness** | No duplicate records | Primary key constraints | 100% |
| **Validity** | Values within expected ranges | Type checks, regex, enums | ≥98% |
| **Consistency** | Data agrees across sources | Cross-reference validation | ≥90% |
| **Accuracy** | Data matches source of truth | Sample manual verification | ≥95% |
| **Timeliness** | Data is current and fresh | Timestamp checks | Daily updates |

#### Quality Check Implementation

**Validation Functions (src/quality/validators.py):**
```python
from pydantic import BaseModel, field_validator
from typing import List, Dict, Any
from dataclasses import dataclass
from enum import Enum

class QualitySeverity(str, Enum):
    ERROR = "error"      # Blocks processing
    WARNING = "warning"  # Logs but continues
    INFO = "info"        # Informational only

@dataclass
class QualityIssue:
    """Data quality issue found during validation."""
    issue_type: str
    severity: QualitySeverity
    affected_records: int
    message: str
    sample_ids: List[str]

class QualityReport(BaseModel):
    """Quality validation report."""
    total_records: int
    passed_records: int
    failed_records: int
    issues: List[QualityIssue]
    coverage_metrics: Dict[str, float]

    @property
    def pass_rate(self) -> float:
        return self.passed_records / self.total_records if self.total_records > 0 else 0.0

def validate_sbir_awards(
    df: pd.DataFrame,
    config: DataQualityConfig
) -> QualityReport:
    """Validate SBIR awards dataset.

    Checks:
    - Required columns present
    - Data types correct
    - Award amounts valid (> 0)
    - Dates in valid range
    - Duplicate detection
    - Missing value thresholds
    """
    issues = []

    # Required columns
    required = ["award_id", "company_name", "award_amount", "award_date", "agency"]
    missing_cols = set(required) - set(df.columns)
    if missing_cols:
        issues.append(QualityIssue(
            issue_type="missing_columns",
            severity=QualitySeverity.ERROR,
            affected_records=len(df),
            message=f"Missing required columns: {missing_cols}",
            sample_ids=[]
        ))

    # Duplicate check
    if config.enable_duplicate_check:
        duplicates = df.duplicated(subset=["award_id"], keep=False)
        dup_count = duplicates.sum()
        dup_rate = dup_count / len(df)
        if dup_rate > config.max_duplicate_rate:
            issues.append(QualityIssue(
                issue_type="duplicate_records",
                severity=QualitySeverity.ERROR,
                affected_records=dup_count,
                message=f"Duplicate rate {dup_rate:.2%} exceeds threshold {config.max_duplicate_rate:.2%}",
                sample_ids=df[duplicates]["award_id"].head(5).tolist()
            ))

    # Missing value check
    for col in required:
        if col not in df.columns:
            continue
        missing = df[col].isna().sum()
        missing_rate = missing / len(df)
        if missing_rate > config.max_missing_rate:
            issues.append(QualityIssue(
                issue_type="missing_values",
                severity=QualitySeverity.WARNING,
                affected_records=missing,
                message=f"Column '{col}' missing rate {missing_rate:.2%} exceeds threshold",
                sample_ids=df[df[col].isna()].head(5).index.tolist()
            ))

    # Award amount validation
    if config.enable_amount_validation and "award_amount" in df.columns:
        invalid_amounts = (df["award_amount"] <= config.min_award_amount) | df["award_amount"].isna()
        invalid_count = invalid_amounts.sum()
        if invalid_count > 0:
            issues.append(QualityIssue(
                issue_type="invalid_amounts",
                severity=QualitySeverity.WARNING,
                affected_records=invalid_count,
                message=f"Invalid award amounts (≤ {config.min_award_amount})",
                sample_ids=df[invalid_amounts]["award_id"].head(5).tolist()
            ))

    # Calculate pass/fail
    has_errors = any(issue.severity == QualitySeverity.ERROR for issue in issues)
    passed = 0 if has_errors else len(df)
    failed = len(df) if has_errors else sum(issue.affected_records for issue in issues)

    # Coverage metrics
    coverage = {
        "award_id_coverage": 1.0 - (df["award_id"].isna().sum() / len(df)),
        "company_name_coverage": 1.0 - (df["company_name"].isna().sum() / len(df)),
        "award_amount_coverage": 1.0 - (df["award_amount"].isna().sum() / len(df)),
    }

    return QualityReport(
        total_records=len(df),
        passed_records=passed,
        failed_records=failed,
        issues=issues,
        coverage_metrics=coverage
    )
```

#### Dagster Asset Checks

```python
from dagster import asset_check, AssetCheckResult

@asset_check(asset=validated_sbir_awards)
def sbir_awards_completeness_check(validated_sbir_awards: pd.DataFrame) -> AssetCheckResult:
    """Check that required fields are ≥95% populated."""
    required_fields = ["award_id", "company_name", "award_amount"]
    coverage = {
        field: 1.0 - (validated_sbir_awards[field].isna().sum() / len(validated_sbir_awards))
        for field in required_fields
    }

    min_coverage = min(coverage.values())
    passed = min_coverage >= 0.95

    return AssetCheckResult(
        passed=passed,
        metadata={
            "min_coverage": min_coverage,
            "field_coverage": coverage,
        }
    )

@asset_check(asset=enriched_sbir_awards)
def enrichment_success_rate_check(enriched_sbir_awards: pd.DataFrame) -> AssetCheckResult:
    """Check that ≥90% of awards have enrichment data."""
    enriched_count = enriched_sbir_awards["sam_gov_data"].notna().sum()
    enrichment_rate = enriched_count / len(enriched_sbir_awards)

    return AssetCheckResult(
        passed=enrichment_rate >= 0.90,
        metadata={
            "enrichment_rate": enrichment_rate,
            "enriched_count": enriched_count,
            "total_count": len(enriched_sbir_awards),
        }
    )
```

#### Quality Monitoring Dashboard

Track quality metrics over time in Dagster UI:
- Pass rates by stage
- Issue distribution by type and severity
- Coverage trends
- Enrichment success rates
- Pipeline execution duration

**Benefits:**
- Early detection of data issues
- Automated quality gates prevent bad data propagation
- Clear accountability for quality thresholds
- Historical quality trend analysis

---

### 4. Structured Logging Pattern

**Context-aware, searchable logging** for debugging and monitoring.

#### Logging Architecture

```
Application Code
    ↓
loguru (structured logging)
    ↓
Formatters (JSON, Console)
    ↓
Outputs (File, Stdout, Sinks)
```

#### Implementation (src/logging_config.py)

```python
import sys
from loguru import logger
from pathlib import Path
from typing import Dict, Any
import json

def setup_logging(log_level: str = "INFO", log_dir: Path = None):
    """Configure structured logging with loguru.

    Features:
    - JSON format for production (machine-readable)
    - Pretty format for development (human-readable)
    - Daily rotating files
    - Context injection for request tracking
    - Structured fields for querying
    """
    # Remove default handler
    logger.remove()

    # Console handler (pretty format for development)
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
        level=log_level,
        colorize=True,
    )

    # File handler (JSON format for production)
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_dir / "sbir-etl_{time:YYYY-MM-DD}.log",
            format=json_formatter,
            level=log_level,
            rotation="00:00",  # Rotate daily at midnight
            retention="30 days",
            compression="zip",
        )

def json_formatter(record: Dict[str, Any]) -> str:
    """Format log record as JSON."""
    log_entry = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }

    # Add extra context fields
    if record.get("extra"):
        log_entry.update(record["extra"])

    return json.dumps(log_entry) + "\n"

# Context manager for pipeline stage tracking
from contextvars import ContextVar

pipeline_stage: ContextVar[str] = ContextVar("pipeline_stage", default="unknown")
run_id: ContextVar[str] = ContextVar("run_id", default="")

def log_with_context(stage: str, run_id_val: str = None):
    """Context manager to add stage and run_id to all logs."""
    from contextlib import contextmanager

    @contextmanager
    def _context():
        token_stage = pipeline_stage.set(stage)
        token_run = None
        if run_id_val:
            token_run = run_id.set(run_id_val)

        try:
            yield
        finally:
            pipeline_stage.reset(token_stage)
            if token_run:
                run_id.reset(token_run)

    return _context()
```

#### Usage Patterns

```python
from loguru import logger
from src.logging_config import setup_logging, log_with_context

# Initialize logging
setup_logging(log_level="INFO", log_dir=Path("logs"))

# Basic logging
logger.info("Starting SBIR ETL pipeline")
logger.warning("SAM.gov API rate limit approaching", remaining=15, limit=100)
logger.error("Failed to parse award", award_id="12345", error=str(e))

# Structured logging with context
logger.bind(
    records_processed=5234,
    naics_coverage=87.3,
    duration_seconds=35.8
).info("Processing complete")

# Context manager for stage tracking
with log_with_context(stage="enrichment", run_id="abc-123"):
    logger.info("Enriching awards with SAM.gov data")
    # All logs in this block automatically include stage="enrichment" and run_id="abc-123"

# Performance logging
import time
start = time.time()
# ... processing ...
logger.bind(
    stage="transform",
    records=len(df),
    duration_ms=(time.time() - start) * 1000,
    throughput_per_sec=len(df) / (time.time() - start)
).info("Transformation complete")

# Error logging with exception
try:
    process_awards()
except Exception as e:
    logger.exception("Award processing failed")  # Automatically includes traceback
```

#### Log Output Examples

**Console (Development):**
```
2025-10-25 14:32:15 | INFO     | pipeline.extract:fetch_awards | Starting SBIR ETL pipeline
2025-10-25 14:32:18 | WARNING  | enrichment:enrich_sam_gov | SAM.gov API rate limit approaching
2025-10-25 14:32:22 | INFO     | pipeline.transform:normalize | Processing complete
```

**JSON (Production):**
```json
{
  "timestamp": "2025-10-25T14:32:22.123456",
  "level": "INFO",
  "logger": "pipeline.transform",
  "function": "normalize",
  "line": 145,
  "message": "Processing complete",
  "stage": "transform",
  "run_id": "abc-123",
  "records_processed": 5234,
  "naics_coverage": 87.3,
  "duration_seconds": 35.8
}
```

#### Log Querying

**Search logs with jq:**
```bash
# Find all errors in enrichment stage
cat logs/sbir-etl_2025-10-25.log | jq 'select(.level == "ERROR" and .stage == "enrichment")'

# Calculate average processing duration
cat logs/sbir-etl_2025-10-25.log | jq -s 'map(select(.duration_seconds)) | map(.duration_seconds) | add / length'

# Count records processed by stage
cat logs/sbir-etl_2025-10-25.log | jq -s 'group_by(.stage) | map({stage: .[0].stage, total_records: map(.records_processed // 0) | add})'
```

**Benefits:**
- Searchable structured logs
- Performance metrics tracking
- Error debugging with context
- Audit trail for compliance
- Integration with log aggregation tools (ELK, Splunk, Datadog)

---

### 5. Hierarchical Data Enrichment with Fallbacks

**Multi-source enrichment strategy** with documented fallback chain for maximum data coverage.

#### Enrichment Architecture

```
Primary Source (Highest Quality)
    ↓ Success? → Continue
    ↓ Fail? → Fallback
Secondary Source (Good Quality)
    ↓ Success? → Continue
    ↓ Fail? → Fallback
Tertiary Source (Acceptable Quality)
    ↓ Success? → Continue
    ↓ Fail? → Fallback
Rule-Based Default (Lowest Quality)
    ↓
Log Enrichment Path & Confidence Score
```

#### Example: Company NAICS Code Enrichment

**9-Step Enrichment Workflow:**

```python
from typing import Optional, Tuple
from enum import Enum
from dataclasses import dataclass

class EnrichmentSource(str, Enum):
    """Source of enrichment data."""
    ORIGINAL = "original"
    USASPENDING_API = "usaspending_api"
    SAM_GOV_API = "sam_gov_api"
    FUZZY_MATCH = "fuzzy_match"
    PROXIMITY_FILTER = "proximity_filter"
    AGENCY_DEFAULT = "agency_default"
    SECTOR_FALLBACK = "sector_fallback"

@dataclass
class EnrichmentResult:
    """Result of enrichment attempt."""
    naics_code: Optional[str]
    source: EnrichmentSource
    confidence: float  # 0.0-1.0
    metadata: dict

def enrich_naics_hierarchical(
    award: Dict[str, Any],
    config: EnrichmentConfig
) -> EnrichmentResult:
    """Enrich NAICS code using hierarchical fallback strategy.

    Priority:
    1. Original SBIR data (if valid)
    2. USAspending.gov API (by UEI/contract ID)
    3. SAM.gov API (by company DUNS/UEI)
    4. Fuzzy name matching (company name similarity)
    5. Proximity filtering (geographic validation)
    6. Agency defaults (DOD → manufacturing, NIH → biotech)
    7. Sector fallback (default to "5415" R&D services)

    Returns:
        EnrichmentResult with NAICS code, source, and confidence.
    """
    logger.bind(award_id=award["award_id"]).info("Starting NAICS enrichment")

    # Step 1: Original SBIR NAICS (confidence: 0.95)
    if award.get("naics_code") and is_valid_naics(award["naics_code"]):
        logger.debug("Using original NAICS code", naics=award["naics_code"])
        return EnrichmentResult(
            naics_code=award["naics_code"],
            source=EnrichmentSource.ORIGINAL,
            confidence=0.95,
            metadata={"validation": "passed"}
        )

    # Step 2: USAspending API (confidence: 0.90)
    try:
        result = fetch_usaspending_naics(award["uei"], award["contract_id"])
        if result:
            logger.debug("Enriched from USAspending", naics=result)
            return EnrichmentResult(
                naics_code=result,
                source=EnrichmentSource.USASPENDING_API,
                confidence=0.90,
                metadata={"api": "usaspending", "uei": award["uei"]}
            )
    except Exception as e:
        logger.warning("USAspending enrichment failed", error=str(e))

    # Step 3: SAM.gov API (confidence: 0.85)
    if config.sam_gov_api_key:
        try:
            result = fetch_sam_gov_naics(award["company_name"], award["duns"])
            if result:
                logger.debug("Enriched from SAM.gov", naics=result)
                return EnrichmentResult(
                    naics_code=result,
                    source=EnrichmentSource.SAM_GOV_API,
                    confidence=0.85,
                    metadata={"api": "sam_gov", "duns": award["duns"]}
                )
        except Exception as e:
            logger.warning("SAM.gov enrichment failed", error=str(e))

    # Step 4: Fuzzy name matching (confidence: 0.65-0.80)
    matches = fuzzy_match_company_to_contracts(
        award["company_name"],
        similarity_threshold=0.80
    )
    if matches:
        best_match = matches[0]
        logger.debug(
            "Enriched via fuzzy matching",
            naics=best_match["naics"],
            similarity=best_match["score"]
        )
        return EnrichmentResult(
            naics_code=best_match["naics"],
            source=EnrichmentSource.FUZZY_MATCH,
            confidence=best_match["score"] * 0.80,  # Discount for uncertainty
            metadata={"matched_company": best_match["name"], "similarity": best_match["score"]}
        )

    # Step 5: Proximity filtering (validate fuzzy matches by location)
    # ... implementation ...

    # Step 6: Agency defaults (confidence: 0.50)
    agency_naics_map = {
        "DOD": "3364",  # Aerospace manufacturing
        "HHS": "5417",  # Biotechnology R&D
        "DOE": "5417",  # Energy R&D
        "NASA": "5417", # Space R&D
    }
    if award["agency"] in agency_naics_map:
        default_naics = agency_naics_map[award["agency"]]
        logger.debug("Using agency default NAICS", agency=award["agency"], naics=default_naics)
        return EnrichmentResult(
            naics_code=default_naics,
            source=EnrichmentSource.AGENCY_DEFAULT,
            confidence=0.50,
            metadata={"agency": award["agency"]}
        )

    # Step 7: Sector fallback (confidence: 0.30)
    fallback_naics = "5415"  # Scientific R&D services
    logger.warning(
        "All enrichment methods failed, using sector fallback",
        naics=fallback_naics
    )
    return EnrichmentResult(
        naics_code=fallback_naics,
        source=EnrichmentSource.SECTOR_FALLBACK,
        confidence=0.30,
        metadata={"reason": "all_methods_failed"}
    )
```

#### Enrichment Tracking

**Store enrichment metadata** for audit and quality analysis:

```python
@dataclass
class EnrichedAward:
    """Award with enrichment metadata."""
    award_id: str
    company_name: str
    naics_code: str
    naics_source: EnrichmentSource
    naics_confidence: float
    enrichment_attempts: List[str]  # ["original", "usaspending", "sam_gov", ...]
    enrichment_timestamp: datetime
    # ... other fields

# Track enrichment coverage
enrichment_stats = {
    "total_awards": 10000,
    "enrichment_sources": {
        "original": 3500,
        "usaspending_api": 4200,
        "sam_gov_api": 1800,
        "fuzzy_match": 400,
        "agency_default": 80,
        "sector_fallback": 20,
    },
    "average_confidence": 0.82,
    "high_confidence_rate": 0.75,  # ≥0.80 confidence
}

logger.bind(**enrichment_stats).info("Enrichment complete")
```

#### Configuration-Driven Fallback Rules

```yaml
# config/enrichment.yaml
enrichment:
  naics:
    enable_original: true
    enable_usaspending: true
    enable_sam_gov: true
    enable_fuzzy_match: true
    fuzzy_similarity_threshold: 0.80
    enable_proximity_filter: false
    enable_agency_default: true
    enable_sector_fallback: true

  fallback_rules:
    agency_defaults:
      DOD: "3364"
      HHS: "5417"
      DOE: "5417"
      NASA: "5417"
    sector_fallback: "5415"

  confidence_thresholds:
    high: 0.80
    medium: 0.60
    low: 0.40
```

**Benefits:**
- Maximum data coverage (approaching 100%)
- Transparent data provenance
- Confidence scoring for downstream filtering
- Configurable without code changes
- Clear audit trail

---

### 6. Configuration-Driven Quality Thresholds

**Externalize quality rules** to YAML for non-technical adjustment.

Already covered in **Configuration Management Architecture** and **Data Quality Framework** sections above. Key pattern:

```yaml
# config/quality.yaml
data_quality:
  completeness:
    award_id: 1.00          # 100% required
    company_name: 0.95      # 95% required
    award_amount: 0.98      # 98% required
    naics_code: 0.85        # 85% required (enrichment target)

  uniqueness:
    award_id: 1.00          # No duplicates allowed

  validity:
    award_amount_min: 0.0
    award_amount_max: 5000000.0  # $5M max for Phase II
    award_date_min: "1983-01-01"
    award_date_max: "2025-12-31"

  thresholds:
    max_duplicate_rate: 0.10      # Block if >10% duplicates
    max_missing_rate: 0.15        # Warn if >15% missing
    min_enrichment_success: 0.90  # Target 90% enrichment

  actions:
    on_error: "block"       # Block pipeline on errors
    on_warning: "continue"  # Log warnings but continue
    on_info: "log"          # Just log info
```

**Benefits:**
- Business users can adjust thresholds
- A/B test different quality rules
- Environment-specific standards (dev vs prod)

---

### 7. Rich CLI with Progress Tracking

**Professional terminal UI** for pipeline execution and monitoring.

#### Implementation (src/cli/app.py)

```python
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint
from typing import Optional
import pandas as pd

app = typer.Typer()
console = Console()

@app.command()
def ingest(
    source: str = typer.Option(..., help="Data source: sbir|usaspending|patents"),
    year: Optional[int] = typer.Option(None, help="Fiscal year to ingest"),
    incremental: bool = typer.Option(False, help="Incremental update (vs full refresh)"),
):
    """Ingest data from external sources."""
    console.print(Panel.fit(
        f"[bold cyan]SBIR ETL Pipeline - Data Ingestion[/bold cyan]\n"
        f"Source: {source}\n"
        f"Year: {year or 'All'}\n"
        f"Mode: {'Incremental' if incremental else 'Full'}",
        border_style="cyan"
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:

        # Task 1: Download
        download_task = progress.add_task(
            "[cyan]Downloading data...",
            total=100
        )
        # ... download logic with progress updates ...
        progress.update(download_task, completed=100)

        # Task 2: Parse
        parse_task = progress.add_task(
            "[yellow]Parsing CSV files...",
            total=len(files)
        )
        for file in files:
            # ... parse logic ...
            progress.update(parse_task, advance=1)

        # Task 3: Validate
        validate_task = progress.add_task(
            "[magenta]Validating data quality...",
            total=len(df)
        )
        # ... validation logic ...
        progress.update(validate_task, completed=len(df))

    # Summary table
    table = Table(title="Ingestion Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="green")

    table.add_row("Records Downloaded", f"{records_downloaded:,}")
    table.add_row("Records Parsed", f"{records_parsed:,}")
    table.add_row("Records Validated", f"{records_validated:,}")
    table.add_row("Pass Rate", f"{pass_rate:.1%}")
    table.add_row("Duration", f"{duration:.2f}s")

    console.print(table)

    if errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in errors[:5]:
            console.print(f"  • {error}")

@app.command()
def status():
    """Show pipeline status and data quality metrics."""
    # Query Dagster/database for status

    # Status panel
    status_panel = Panel(
        "[green]✓[/green] All pipelines healthy\n"
        "[yellow]⚠[/yellow] 2 warnings in enrichment stage\n"
        "[blue]ℹ[/blue] Last run: 2 hours ago",
        title="Pipeline Status",
        border_style="green"
    )
    console.print(status_panel)

    # Quality metrics table
    metrics_table = Table(title="Data Quality Metrics", show_header=True)
    metrics_table.add_column("Stage", style="cyan")
    metrics_table.add_column("Records", justify="right")
    metrics_table.add_column("Pass Rate", justify="right")
    metrics_table.add_column("Coverage", justify="right")

    metrics_table.add_row("Extract", "252,341", "100.0%", "-")
    metrics_table.add_row("Validate", "252,341", "98.5%", "-")
    metrics_table.add_row("Enrich", "248,550", "97.9%", "87.3%")
    metrics_table.add_row("Transform", "248,550", "99.2%", "-")
    metrics_table.add_row("Load", "246,789", "99.8%", "-")

    console.print(metrics_table)

@app.command()
def enrich(
    batch_size: int = typer.Option(100, help="Batch size for API calls"),
    dry_run: bool = typer.Option(False, help="Dry run without API calls"),
):
    """Enrich awards with external data sources."""

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:

        task = progress.add_task(
            "[cyan]Enriching from SAM.gov API...",
            total=total_records
        )

        for batch in batches:
            # ... enrichment logic ...
            progress.update(task, advance=len(batch))

    # Enrichment summary
    rprint(f"\n[bold green]✓ Enrichment complete![/bold green]")
    rprint(f"  • Total records: {total_records:,}")
    rprint(f"  • Successfully enriched: {enriched_count:,} ({enriched_count/total_records:.1%})")
    rprint(f"  • Fallback to defaults: {fallback_count:,}")
    rprint(f"  • Duration: {duration:.2f}s")
    rprint(f"  • Throughput: {total_records/duration:.0f} records/sec")

if __name__ == "__main__":
    app()
```

#### CLI Usage

```bash
# Ingest SBIR awards
python -m src.cli.app ingest --source sbir --year 2024

# Enrich with progress bar
python -m src.cli.app enrich --batch-size 100

# Check pipeline status
python -m src.cli.app status

# Show data quality report
python -m src.cli.app quality-report --stage enrichment
```

**Benefits:**
- Professional user experience
- Real-time progress visibility
- Clear error messaging
- Summary statistics
- Non-technical user friendly

---

### 8. Evidence-Based Explainability

**Provide supporting evidence** for automated decisions (enrichment, matching, classification).

#### Pattern: Return Confidence + Evidence

```python
from typing import List
from dataclasses import dataclass

@dataclass
class MatchEvidence:
    """Evidence supporting a match decision."""
    evidence_type: str  # "exact_match", "fuzzy_match", "proximity", "api_lookup"
    confidence: float   # 0.0-1.0
    source_field: str
    matched_value: str
    original_value: str
    metadata: dict

@dataclass
class EnrichmentResult:
    """Enrichment result with supporting evidence."""
    field_name: str
    enriched_value: Any
    original_value: Any
    confidence: float
    evidence: List[MatchEvidence]
    timestamp: datetime

def match_company_with_evidence(
    award: Dict[str, Any],
    contracts_db: pd.DataFrame
) -> EnrichmentResult:
    """Match company to contracts database with evidence trail.

    Returns enriched NAICS code plus evidence for manual review.
    """
    evidence_list = []

    # Try exact name match first
    exact_match = contracts_db[
        contracts_db["company_name"].str.upper() == award["company_name"].upper()
    ]
    if not exact_match.empty:
        evidence_list.append(MatchEvidence(
            evidence_type="exact_match",
            confidence=0.95,
            source_field="company_name",
            matched_value=exact_match.iloc[0]["company_name"],
            original_value=award["company_name"],
            metadata={"match_count": len(exact_match)}
        ))

    # Try UEI match
    if award.get("uei"):
        uei_match = contracts_db[contracts_db["uei"] == award["uei"]]
        if not uei_match.empty:
            evidence_list.append(MatchEvidence(
                evidence_type="uei_match",
                confidence=0.98,
                source_field="uei",
                matched_value=award["uei"],
                original_value=award["uei"],
                metadata={"contract_count": len(uei_match)}
            ))

    # Try fuzzy name match
    fuzzy_matches = fuzzy_match_names(
        award["company_name"],
        contracts_db["company_name"],
        threshold=0.80
    )
    if fuzzy_matches:
        best_match = fuzzy_matches[0]
        evidence_list.append(MatchEvidence(
            evidence_type="fuzzy_match",
            confidence=best_match["similarity"],
            source_field="company_name",
            matched_value=best_match["name"],
            original_value=award["company_name"],
            metadata={"similarity_score": best_match["similarity"]}
        ))

    # Calculate overall confidence (weighted average)
    if evidence_list:
        overall_confidence = sum(e.confidence for e in evidence_list) / len(evidence_list)
        enriched_naics = best_match["naics"]
    else:
        overall_confidence = 0.0
        enriched_naics = None

    return EnrichmentResult(
        field_name="naics_code",
        enriched_value=enriched_naics,
        original_value=award.get("naics_code"),
        confidence=overall_confidence,
        evidence=evidence_list,
        timestamp=datetime.now()
    )
```

#### Store Evidence in Neo4j

```python
# Neo4j relationship with evidence metadata
CREATE (a:Award {award_id: "12345"})
CREATE (c:Company {name: "Acme Corp"})
CREATE (a)-[r:AWARDED_TO {
    matched_by: "fuzzy_match",
    confidence: 0.82,
    evidence: [
        {type: "fuzzy_match", similarity: 0.82, field: "company_name"},
        {type: "proximity", distance_miles: 5.2, field: "location"}
    ],
    enriched_at: datetime("2025-10-25T14:32:22")
}]->(c)
```

#### Manual Review Interface

```python
@app.command()
def review_low_confidence(
    threshold: float = typer.Option(0.70, help="Review matches below this confidence"),
):
    """Show low-confidence enrichments for manual review."""

    # Query enrichments below threshold
    low_confidence_results = query_enrichments(confidence_lt=threshold)

    console.print(Panel(
        f"[bold yellow]Manual Review Required[/bold yellow]\n"
        f"Found {len(low_confidence_results)} enrichments with confidence < {threshold}",
        border_style="yellow"
    ))

    for result in low_confidence_results:
        # Display evidence table
        evidence_table = Table(title=f"Award: {result['award_id']}", show_header=True)
        evidence_table.add_column("Evidence Type", style="cyan")
        evidence_table.add_column("Matched Value")
        evidence_table.add_column("Confidence", justify="right")

        for evidence in result["evidence"]:
            evidence_table.add_row(
                evidence["type"],
                evidence["matched_value"],
                f"{evidence['confidence']:.2%}"
            )

        console.print(evidence_table)

        # Prompt for manual decision
        decision = typer.prompt(
            "Accept (a), Reject (r), or Edit (e)?",
            type=str
        )
        # ... handle decision ...
```

**Benefits:**
- Transparency in automated decisions
- Support for manual review workflows
- Confidence-based filtering
- Audit trail for compliance

---

### 9. Comprehensive Evaluation Framework

**Systematic metrics tracking** to measure pipeline performance and quality.

#### Evaluation Dimensions

| Dimension | Metrics | Target | Tracking Method |
|-----------|---------|--------|----------------|
| **Data Coverage** | % records processed successfully | ≥95% | Pipeline telemetry |
| **Enrichment Success** | % records enriched from each source | ≥90% | Source tracking |
| **Data Quality** | Pass rates by validation rule | ≥98% | Quality reports |
| **Performance** | Throughput (records/sec), latency | Documented SLAs | Instrumentation |
| **Reliability** | Pipeline success rate, uptime | ≥99.5% | Dagster monitoring |
| **Accuracy** | Sample validation vs. ground truth | ≥95% | Manual audits |

#### Implementation (src/evaluation/metrics.py)

```python
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime
import json
from pathlib import Path

@dataclass
class PipelineMetrics:
    """Comprehensive pipeline evaluation metrics."""
    run_id: str
    run_timestamp: datetime

    # Coverage metrics
    total_records_extracted: int
    total_records_validated: int
    total_records_enriched: int
    total_records_transformed: int
    total_records_loaded: int

    # Quality metrics
    validation_pass_rate: float
    enrichment_success_rate: float
    transformation_success_rate: float
    load_success_rate: float

    # Enrichment breakdown
    enrichment_by_source: Dict[str, int] = field(default_factory=dict)
    average_enrichment_confidence: float = 0.0
    high_confidence_enrichment_rate: float = 0.0  # ≥0.80

    # Performance metrics
    total_duration_seconds: float = 0.0
    stage_durations: Dict[str, float] = field(default_factory=dict)
    throughput_records_per_sec: float = 0.0

    # Error tracking
    error_count: int = 0
    error_breakdown: Dict[str, int] = field(default_factory=dict)

    # Data quality details
    duplicate_rate: float = 0.0
    missing_value_rate: float = 0.0
    invalid_value_rate: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "run_timestamp": self.run_timestamp.isoformat(),
            "coverage": {
                "extracted": self.total_records_extracted,
                "validated": self.total_records_validated,
                "enriched": self.total_records_enriched,
                "transformed": self.total_records_transformed,
                "loaded": self.total_records_loaded,
            },
            "quality": {
                "validation_pass_rate": self.validation_pass_rate,
                "enrichment_success_rate": self.enrichment_success_rate,
                "transformation_success_rate": self.transformation_success_rate,
                "load_success_rate": self.load_success_rate,
            },
            "enrichment": {
                "by_source": self.enrichment_by_source,
                "average_confidence": self.average_enrichment_confidence,
                "high_confidence_rate": self.high_confidence_enrichment_rate,
            },
            "performance": {
                "total_duration_seconds": self.total_duration_seconds,
                "stage_durations": self.stage_durations,
                "throughput_records_per_sec": self.throughput_records_per_sec,
            },
            "errors": {
                "total_count": self.error_count,
                "breakdown": self.error_breakdown,
            },
            "data_quality": {
                "duplicate_rate": self.duplicate_rate,
                "missing_value_rate": self.missing_value_rate,
                "invalid_value_rate": self.invalid_value_rate,
            },
        }

    def save(self, output_dir: Path):
        """Save metrics to JSON file."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"metrics_{self.run_id}.json"

        with open(output_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        logger.info("Metrics saved", path=str(output_path))

class MetricsCollector:
    """Collect metrics during pipeline execution."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.start_time = datetime.now()
        self.stage_start_times: Dict[str, datetime] = {}
        self.metrics = PipelineMetrics(
            run_id=run_id,
            run_timestamp=self.start_time
        )

    def start_stage(self, stage: str):
        """Mark start of pipeline stage."""
        self.stage_start_times[stage] = datetime.now()
        logger.info("Stage started", stage=stage, run_id=self.run_id)

    def end_stage(self, stage: str, records_processed: int):
        """Mark end of pipeline stage."""
        if stage not in self.stage_start_times:
            logger.warning("Stage not started", stage=stage)
            return

        duration = (datetime.now() - self.stage_start_times[stage]).total_seconds()
        self.metrics.stage_durations[stage] = duration

        logger.info(
            "Stage completed",
            stage=stage,
            duration_seconds=duration,
            records_processed=records_processed,
            throughput=records_processed / duration if duration > 0 else 0
        )

    def record_enrichment(self, source: str, count: int, avg_confidence: float):
        """Record enrichment metrics."""
        self.metrics.enrichment_by_source[source] = count

    def record_error(self, error_type: str):
        """Record pipeline error."""
        self.metrics.error_count += 1
        self.metrics.error_breakdown[error_type] = \
            self.metrics.error_breakdown.get(error_type, 0) + 1

    def finalize(self) -> PipelineMetrics:
        """Finalize metrics collection."""
        self.metrics.total_duration_seconds = \
            (datetime.now() - self.start_time).total_seconds()

        if self.metrics.total_records_extracted > 0:
            self.metrics.throughput_records_per_sec = \
                self.metrics.total_records_loaded / self.metrics.total_duration_seconds

        logger.bind(**self.metrics.to_dict()).info("Pipeline metrics finalized")
        return self.metrics
```

#### Usage in Dagster Assets

```python
from src.evaluation.metrics import MetricsCollector

@asset
def enriched_sbir_awards(
    validated_sbir_awards: pd.DataFrame,
    context: AssetExecutionContext
) -> pd.DataFrame:
    """Enrich SBIR awards with external data."""

    # Initialize metrics collector
    run_id = context.run_id
    metrics = MetricsCollector(run_id)
    metrics.start_stage("enrichment")

    try:
        # Enrichment logic
        enriched = enrich_awards(validated_sbir_awards)

        # Record enrichment metrics
        metrics.metrics.total_records_enriched = len(enriched)
        metrics.metrics.enrichment_success_rate = \
            len(enriched) / len(validated_sbir_awards)

        # Track enrichment by source
        for source, count in enriched["enrichment_source"].value_counts().items():
            metrics.record_enrichment(source, count, 0.0)  # Calculate avg confidence

        metrics.end_stage("enrichment", len(enriched))

        return enriched

    except Exception as e:
        metrics.record_error(type(e).__name__)
        raise
    finally:
        # Save metrics
        final_metrics = metrics.finalize()
        final_metrics.save(Path("artifacts/metrics"))
```

#### Metrics Dashboard

**CLI command to view metrics:**
```python
@app.command()
def metrics(
    run_id: Optional[str] = typer.Option(None, help="Specific run ID"),
    last_n: int = typer.Option(5, help="Show last N runs"),
):
    """Display pipeline metrics."""

    if run_id:
        # Show specific run
        metrics_path = Path(f"artifacts/metrics/metrics_{run_id}.json")
        with open(metrics_path) as f:
            metrics = json.load(f)

        # Display detailed metrics
        console.print(Panel(f"[bold cyan]Pipeline Metrics: {run_id}[/bold cyan]"))

        # Coverage table
        coverage_table = Table(title="Coverage", show_header=True)
        coverage_table.add_column("Stage", style="cyan")
        coverage_table.add_column("Records", justify="right", style="green")

        for stage, count in metrics["coverage"].items():
            coverage_table.add_row(stage.title(), f"{count:,}")

        console.print(coverage_table)

        # Quality table
        quality_table = Table(title="Quality Metrics", show_header=True)
        quality_table.add_column("Metric", style="cyan")
        quality_table.add_column("Value", justify="right")

        for metric, value in metrics["quality"].items():
            quality_table.add_row(
                metric.replace("_", " ").title(),
                f"{value:.1%}"
            )

        console.print(quality_table)

        # Performance summary
        rprint(f"\n[bold]Performance:[/bold]")
        rprint(f"  • Total Duration: {metrics['performance']['total_duration_seconds']:.2f}s")
        rprint(f"  • Throughput: {metrics['performance']['throughput_records_per_sec']:.0f} records/sec")

    else:
        # Show summary of last N runs
        metrics_files = sorted(
            Path("artifacts/metrics").glob("metrics_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:last_n]

        # Trend table
        trend_table = Table(title=f"Last {last_n} Pipeline Runs", show_header=True)
        trend_table.add_column("Run ID", style="cyan")
        trend_table.add_column("Timestamp")
        trend_table.add_column("Records", justify="right")
        trend_table.add_column("Success Rate", justify="right")
        trend_table.add_column("Duration", justify="right")

        for metrics_file in metrics_files:
            with open(metrics_file) as f:
                m = json.load(f)

            trend_table.add_row(
                m["run_id"][:8],
                m["run_timestamp"][:19],
                f"{m['coverage']['loaded']:,}",
                f"{m['quality']['load_success_rate']:.1%}",
                f"{m['performance']['total_duration_seconds']:.1f}s"
            )

        console.print(trend_table)
```

**Benefits:**
- Historical performance tracking
- Quality trend analysis
- Early detection of regressions
- Data-driven optimization
- Compliance reporting

---

## Summary: Adopted Patterns

This project incorporates production-proven patterns from three mature SBIR projects:

✅ **Common Patterns (5)**
1. Configuration Management Architecture - Three-layer YAML + Pydantic + env overrides
2. Multi-Stage Data Pipeline Design - Five-stage ETL with quality gates
3. Data Quality Framework - Comprehensive validation with asset checks
4. Testing Pyramid Structure - Unit/Integration/E2E with 85%+ coverage
5. Structured Logging Pattern - JSON logs with context and querying

✅ **From sbir-fiscal-returns (2)**
1. Hierarchical Data Enrichment with Fallbacks - 9-step enrichment chain
2. Configuration-Driven Quality Thresholds - Externalized quality rules

✅ **From sbir-transition-classifier (1)**
4. Rich CLI with Progress Tracking - Professional terminal UI

✅ **From sbir-cet-classifier (2)**
2. Evidence-Based Explainability - Confidence scores + supporting evidence
4. Comprehensive Evaluation Framework - Metrics tracking and dashboards

These patterns ensure production-grade quality, maintainability, and operational excellence for the SBIR ETL pipeline.
