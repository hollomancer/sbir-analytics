# Shared Tech Stack Architecture

**Date**: October 26, 2025
**Purpose**: Document shared technical infrastructure across SBIR ETL, USPTO Patent ETL, and CET Classification modules

---

## Executive Summary

The sbir-etl project leverages a highly reusable tech stack where **85% of dependencies and 90% of infrastructure patterns are shared** across all three major feature areas (SBIR ingestion, USPTO patent ETL, CET classification). This document identifies shared components and provides guidance on standardization opportunities.

---

## 1. Core Shared Dependencies (Already Available)

These libraries are already installed and used across all modules:

### Data Processing & Manipulation

| Library | Version | Usage | Modules |
|---------|---------|-------|---------|
| **pandas** | 2.2.0+ | CSV/Stata parsing, data transformation, chunked streaming | All (SBIR, USPTO, CET) |
| **pydantic** | 2.8.0+ | Data validation, schema enforcement, configuration models | All |
| **pyyaml** | 6.0.0+ | Configuration files (taxonomy, classification, pipeline) | All |

**Key Insight**: pandas supports Stata (.dta) format out-of-box via `read_stata()`, eliminating need for separate Stata library.

### Orchestration & Workflow

| Library | Version | Usage | Modules |
|---------|---------|-------|---------|
| **dagster** | 1.7.0+ | Asset-based orchestration, dependency management, scheduling | All |
| **dagster-webserver** | 1.7.0+ | UI for monitoring, asset visualization, job execution | All |

### Shared Patterns

- Asset-based design (`@asset` decorator)
- Dependency injection via asset parameters
- Asset checks for data quality validation
- Partitioned assets for incremental processing

### Storage & Database

| Library | Version | Usage | Modules |
|---------|---------|-------|---------|
| **neo4j** | 5.20.0+ | Graph database driver, Cypher queries, relationship management | All |
| **duckdb** | 1.0.0+ | In-memory SQL analytics for large datasets | SBIR, USPTO (optional for CET) |

### Shared Patterns

- Batch Neo4j writes (1K nodes/transaction)
- MERGE operations for idempotent upserts
- Index creation before bulk loads
- Relationship property storage for metadata

### Logging & Observability

| Library | Version | Usage | Modules |
|---------|---------|-------|---------|
| **loguru** | 0.7.0+ | Structured logging with context, JSON output | All |
| **rich** | 13.7.0+ | Terminal UI, progress bars, formatted tables | All (CLI/reporting) |

### Shared Patterns

- Structured logging with `logger.bind()`
- Context managers for stage tracking
- Performance metrics logging (throughput, duration)

### CLI & User Interface

| Library | Version | Usage | Modules |
|---------|---------|-------|---------|
| **typer** | 0.12.0+ | CLI commands, parameter validation | All |
| **rich** | 13.7.0+ | Formatted CLI output, progress bars | All |

### Development Tools (Already Shared)

| Library | Version | Purpose | Applied To |
|---------|---------|---------|------------|
| **pytest** | 8.0.0+ | Unit/integration/e2e testing | All modules |
| **pytest-cov** | 5.0.0+ | Coverage reporting (target: ≥85%) | All |
| **black** | 24.0.0+ | Code formatting (100 char line length) | All |
| **ruff** | 0.5.0+ | Linting & import sorting | All |
| **mypy** | 1.8.0+ | Static type checking | All |
| **bandit** | 1.7.0+ | Security vulnerability scanning | All |

---

## 2. Newly Required Dependencies

These libraries need to be added for new features:

### ML & NLP (CET Classification Only)

| Library | Version | Purpose | Installation |
|---------|---------|---------|-------------|
| **scikit-learn** | ≥1.4.0 | TF-IDF, Logistic Regression, feature selection, calibration | `poetry add scikit-learn>=1.4` |
| **spacy** | ≥3.7.0 | Sentence segmentation, evidence extraction | `poetry add spacy>=3.7` |
| **en_core_web_sm** | Latest | English NLP model for spaCy | `python -m spacy download en_core_web_sm` |

### Why Not Shared with Other Modules?

- SBIR and USPTO ETL don't require ML classification
- spaCy is 100MB+ download (only needed for CET evidence extraction)
- Keeps other modules lightweight

### Conditional Loading Pattern

```python

## src/ml/models/cet_classifier.py

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logger.warning("ML libraries not available. CET classification disabled.")
```

### Text Processing (Already Available in Dev)

| Library | Version | Purpose | Current Status |
|---------|---------|---------|----------------|
| **rapidfuzz** | 2.16.0+ | Fuzzy string matching for entity resolution | Dev dependency → Promote to main |

**Action Required**: Move `rapidfuzz` from `[tool.poetry.group.dev.dependencies]` to `[tool.poetry.dependencies]`

### Usage Across Modules

- **SBIR**: Company name matching
- **USPTO**: Assignee/assignor entity deduplication
- **CET**: Company-award linkage validation

---

## 3. Shared Infrastructure Patterns

### 3.1 Configuration Management System

**Shared Pattern**: Three-layer YAML → Pydantic → Environment Variables

**File Structure** (all modules use this):

```text
config/
├── base.yaml                    # Shared base configuration
├── dev.yaml / staging.yaml / prod.yaml
├── sbir/
│   ├── ingestion.yaml
│   └── enrichment.yaml
├── uspto/
│   └── extraction.yaml
├── cet/
│   ├── taxonomy.yaml            # CET-specific
│   └── classification.yaml      # CET-specific
└── README.md
```

### Shared Loader Pattern

```python

## src/config/loader.py (used by all modules)

from functools import lru_cache
from pathlib import Path
import yaml
from pydantic import BaseModel

@lru_cache(maxsize=1)
def load_config(config_name: str, config_class: type[BaseModel]) -> BaseModel:
    """Load and validate configuration with environment overrides.

    Usage:
        sbir_config = load_config("sbir/ingestion", SBIRIngestionConfig)
        cet_config = load_config("cet/taxonomy", CETTaxonomyConfig)
    """
    config_path = Path("config") / f"{config_name}.yaml"
    with open(config_path) as f:
        data = yaml.safe_load(f)

    # Apply environment variable overrides
    data = apply_env_overrides(data, prefix=f"SBIR_ETL_{config_name.upper()}")

    # Validate with Pydantic
    return config_class(**data)
```

**Environment Variable Convention** (all modules):

```bash

## Shared infrastructure

export SBIR_ETL_ENV=prod
export SBIR_ETL_NEO4J_URI=bolt://localhost:7687
export SBIR_ETL_LOG_LEVEL=INFO

## Module-specific overrides

export SBIR_ETL_SBIR__CHUNK_SIZE=5000
export SBIR_ETL_USPTO__CHUNK_SIZE=10000
export SBIR_ETL_CET__CONFIDENCE_HIGH_MIN=75
```

### 3.2 Pydantic Data Models

### Shared Base Models

```python

## src/models/base.py (used by all modules)

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional

class BaseEntity(BaseModel):
    """Base class for all domain entities."""
    model_config = ConfigDict(
        validate_assignment=True,
        str_strip_whitespace=True,
        use_enum_values=True
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    source_version: str  # Data version tracking

class BaseConfig(BaseModel):
    """Base class for configuration models."""
    model_config = ConfigDict(
        validate_assignment=True,
        frozen=False,  # Allow runtime updates
        extra="forbid"  # Catch typos in config files
    )
```

### Module-Specific Models Extend Base

```python

## SBIR Award

class Award(BaseEntity):
    award_id: str
    firm_name: str
    award_amount: float

## USPTO Patent

class Patent(BaseEntity):
    grant_doc_num: str
    title: str
    grant_date: date

## CET Classification

class CETClassification(BaseEntity):
    award_id: str
    primary_cet_id: str
    score: int
```

### 3.3 Dagster Asset Patterns

### Shared Asset Structure

```python

## All modules follow this pattern

from dagster import asset, AssetExecutionContext, AssetCheckResult, asset_check

@asset(
    deps=[upstream_asset],
    group_name="sbir",  # or "uspto" or "cet"
    metadata={"priority": "high"}
)
def my_asset(
    context: AssetExecutionContext,
    upstream_asset: pd.DataFrame,
    config: MyConfig = load_config(...)
) -> pd.DataFrame:
    """Asset docstring."""
    context.log.info("Starting asset processing")

    # Processing logic
    result = process_data(upstream_asset, config)

    # Log metrics
    context.log.info(f"Processed {len(result)} records")

    return result

@asset_check(asset=my_asset)
def my_asset_quality_check(my_asset: pd.DataFrame) -> AssetCheckResult:
    """Check data quality."""
    pass_rate = calculate_pass_rate(my_asset)

    return AssetCheckResult(
        passed=pass_rate >= 0.95,
        metadata={"pass_rate": pass_rate}
    )
```

### Shared Asset Grouping

```python

## src/assets/__init__.py

from dagster import load_assets_from_modules
from . import sbir_assets, uspto_assets, cet_assets

all_assets = [

    *load_assets_from_modules([sbir_assets]),
    *load_assets_from_modules([uspto_assets]),
    *load_assets_from_modules([cet_assets])

]
```

### 3.4 Neo4j Loader Patterns

### Shared Base Loader

```python

## src/loaders/base_loader.py (used by all modules)

from neo4j import GraphDatabase, Session
from typing import List, Dict, Any
from contextlib import contextmanager

class BaseNeo4jLoader:
    """Base class for all Neo4j loaders."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    @contextmanager
    def session(self) -> Session:
        """Context manager for Neo4j sessions."""
        session = self.driver.session()
        try:
            yield session
        finally:
            session.close()

    def batch_write(
        self,
        query: str,
        data: List[Dict[str, Any]],
        batch_size: int = 1000
    ):
        """Write data in batches with transaction management."""
        with self.session() as session:
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                session.execute_write(
                    lambda tx: tx.run(query, {"batch": batch})
                )

    def create_index(self, label: str, property: str):
        """Create index if not exists."""
        query = f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{property})"
        with self.session() as session:
            session.run(query)
```

### Module-Specific Loaders Extend Base

```python

## SBIR Loader

class SBIRAwardLoader(BaseNeo4jLoader):
    def load_awards(self, awards: List[Dict]):
        self.create_index("Award", "award_id")
        self.batch_write(MERGE_AWARD_QUERY, awards)

## USPTO Loader

class PatentLoader(BaseNeo4jLoader):
    def load_patents(self, patents: List[Dict]):
        self.create_index("Patent", "grant_doc_num")
        self.batch_write(MERGE_PATENT_QUERY, patents)

## CET Loader

class CETLoader(BaseNeo4jLoader):
    def load_cet_areas(self, cet_areas: List[Dict]):
        self.create_index("CETArea", "cet_id")
        self.batch_write(MERGE_CET_AREA_QUERY, cet_areas)
```

### 3.5 Data Quality Validation Framework

### Shared Validator Base

```python

## src/quality/base_validator.py (used by all modules)

from dataclasses import dataclass
from typing import List, Callable
import pandas as pd

@dataclass
class QualityIssue:
    issue_type: str
    severity: str  # "error", "warning", "info"
    affected_records: int
    message: str
    sample_ids: List[str]

@dataclass
class QualityReport:
    total_records: int
    passed_records: int
    failed_records: int
    issues: List[QualityIssue]

    @property
    def pass_rate(self) -> float:
        return self.passed_records / self.total_records if self.total_records > 0 else 0.0

class BaseValidator:
    """Base class for data quality validators."""

    def __init__(self, config: dict):
        self.config = config
        self.validators: List[Callable] = []

    def register_check(self, check_fn: Callable):
        """Register a validation check."""
        self.validators.append(check_fn)

    def validate(self, df: pd.DataFrame) -> QualityReport:
        """Run all validation checks."""
        issues = []
        for validator in self.validators:
            result = validator(df, self.config)
            if result:
                issues.extend(result)

        # Calculate pass/fail
        has_errors = any(issue.severity == "error" for issue in issues)
        passed = 0 if has_errors else len(df)
        failed = len(df) if has_errors else sum(i.affected_records for i in issues)

        return QualityReport(
            total_records=len(df),
            passed_records=passed,
            failed_records=failed,
            issues=issues
        )
```

### Module-Specific Validators

```python

## SBIR validator

class SBIRAwardValidator(BaseValidator):
    def __init__(self, config: SBIRConfig):
        super().__init__(config)
        self.register_check(self.validate_award_amount)
        self.register_check(self.validate_award_id_unique)

## USPTO validator

class USPTOPatentValidator(BaseValidator):
    def __init__(self, config: USPTOConfig):
        super().__init__(config)
        self.register_check(self.validate_rf_id_unique)
        self.register_check(self.validate_referential_integrity)

## CET validator

class CETClassificationValidator(BaseValidator):
    def __init__(self, config: CETConfig):
        super().__init__(config)
        self.register_check(self.validate_score_range)
        self.register_check(self.validate_taxonomy_version)
```

### 3.6 Logging & Monitoring Patterns

### Shared Logging Configuration

```python

## src/logging_config.py (used by all modules)

from loguru import logger
import sys
import json

def setup_logging(log_level: str = "INFO", log_dir: Path = None):
    """Configure structured logging for all modules."""

    # Remove default handler
    logger.remove()

    # Console handler (pretty format)
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[module]}</cyan> | <level>{message}</level>",
        level=log_level,
        colorize=True,
    )

    # File handler (JSON format)
    if log_dir:
        logger.add(
            log_dir / "sbir-etl_{time:YYYY-MM-DD}.log",
            format=json_formatter,
            level=log_level,
            rotation="00:00",
            retention="30 days",
            compression="zip",
        )
```

### Module-Specific Context

```python

## SBIR module

logger = logger.bind(module="sbir-ingestion")

## USPTO module

logger = logger.bind(module="uspto-patent")

## CET module

logger = logger.bind(module="cet-classification")
```

### 3.7 Testing Infrastructure

### Shared Test Fixtures

```python

## tests/conftest.py (shared across all test modules)

import pytest
from neo4j import GraphDatabase
from testcontainers.neo4j import Neo4jContainer

@pytest.fixture(scope="session")
def neo4j_container():
    """Provide Neo4j test container for integration tests."""
    with Neo4jContainer("neo4j:5.20") as neo4j:
        yield neo4j

@pytest.fixture
def neo4j_loader(neo4j_container):
    """Provide Neo4j loader for testing."""
    return BaseNeo4jLoader(
        uri=neo4j_container.get_connection_url(),
        user="neo4j",
        password="test"
    )

@pytest.fixture
def sample_awards():
    """Provide sample SBIR awards for testing."""
    return pd.read_csv("tests/fixtures/sample_awards.csv")

@pytest.fixture
def sample_patents():
    """Provide sample patents for testing."""
    return pd.read_csv("tests/fixtures/sample_patents.csv")

@pytest.fixture
def sample_cet_taxonomy():
    """Provide sample CET taxonomy for testing."""
    return yaml.safe_load(Path("tests/fixtures/sample_taxonomy.yaml").read_text())
```

### Shared Test Utilities

```python

## tests/utils.py (used by all test modules)

import pandas as pd
from typing import Any, Dict, List

def assert_dataframe_equal_ignore_order(df1: pd.DataFrame, df2: pd.DataFrame):
    """Assert DataFrames are equal, ignoring row order."""
    pd.testing.assert_frame_equal(
        df1.sort_index().reset_index(drop=True),
        df2.sort_index().reset_index(drop=True)
    )

def create_mock_neo4j_session():
    """Create mock Neo4j session for unit testing."""
    from unittest.mock import MagicMock
    session = MagicMock()
    session.run.return_value = MagicMock()
    return session

def generate_test_data(entity_type: str, count: int) -> List[Dict[str, Any]]:
    """Generate synthetic test data for any entity type."""
    # Implementation
    pass
```

---

## 4. Module-Specific (Not Shared)

These components are intentionally module-specific:

### SBIR Module Only

- **SAM.gov API client**: SBIR-specific enrichment
- **SBIR award schema**: Domain-specific fields
- **Award phase logic**: Phase I/II/III-specific business rules

### USPTO Module Only

- **Stata file readers**: USPTO-specific .dta format handling
- **Patent assignment logic**: rf_id relationship management
- **Conveyance text parsing**: Patent-specific field extraction

### CET Module Only

- **ML models** (TF-IDF, LogReg): Classification algorithms
- **spaCy NLP**: Evidence extraction (sentence segmentation)
- **CET taxonomy**: 21-category NSTC framework
- **USPTO AI validation**: CET-specific ground truth comparison

---

## 5. Dependency Installation Strategy

### Current State (pyproject.toml)

```toml
[tool.poetry.dependencies]
python = ">=3.11,<3.12"
dagster = "^1.7.0"
pandas = "^2.2.0"
neo4j = "^5.20.0"
duckdb = "^1.0.0"
pydantic = "^2.8.0"
loguru = "^0.7.0"
pyyaml = "^6.0.0"
typer = "^0.12.0"
rich = "^13.7.0"
```

### Recommended Updates

```toml
[tool.poetry.dependencies]

## Core (no changes)

python = ">=3.11,<3.12"
dagster = "^1.7.0"
pandas = "^2.2.0"
neo4j = "^5.20.0"
duckdb = "^1.0.0"
pydantic = "^2.8.0"
loguru = "^0.7.0"
pyyaml = "^6.0.0"
typer = "^0.12.0"
rich = "^13.7.0"

## NEW: Promote from dev to main (used by all modules)

rapidfuzz = "^2.16.0"

## NEW: ML stack for CET classification (optional extras)

scikit-learn = {version = "^1.4.0", optional = true}
spacy = {version = "^3.7.0", optional = true}

[tool.poetry.extras]
ml = ["scikit-learn", "spacy"]

[tool.poetry.group.dev.dependencies]
pytest = "^8.0.0"
pytest-cov = "^5.0.0"
black = "^24.0.0"
ruff = "^0.5.0"
mypy = "^1.8.0"
bandit = "^1.7.0"

## rapidfuzz moved to main dependencies

```

### Installation Commands

```bash

## Base installation (SBIR + USPTO modules)

poetry install

## With ML capabilities (adds CET classification)

poetry install --extras ml

## Download spaCy model (if using ML extras)

poetry run python -m spacy download en_core_web_sm

## Development installation (includes testing tools)

poetry install --with dev
```

---

## 6. Shared vs. Module-Specific Breakdown

### Summary Matrix

| Component | Shared? | SBIR | USPTO | CET | Notes |
|-----------|---------|------|-------|-----|-------|
| **Core Libraries** |
| pandas | ✅ | ✓ | ✓ | ✓ | Universal data processing |
| pydantic | ✅ | ✓ | ✓ | ✓ | Schema validation |
| dagster | ✅ | ✓ | ✓ | ✓ | Orchestration |
| neo4j | ✅ | ✓ | ✓ | ✓ | Graph database |
| pyyaml | ✅ | ✓ | ✓ | ✓ | Configuration |
| loguru | ✅ | ✓ | ✓ | ✓ | Logging |
| **Data Processing** |
| duckdb | ✅ | ✓ | ✓ | - | Large dataset analytics |
| rapidfuzz | ✅ | ✓ | ✓ | ✓ | Entity matching |
| scikit-learn | ❌ | - | - | ✓ | CET-only ML |
| spacy | ❌ | - | - | ✓ | CET-only NLP |
| **Infrastructure** |
| Configuration system | ✅ | ✓ | ✓ | ✓ | Three-layer pattern |
| Base validators | ✅ | ✓ | ✓ | ✓ | Quality framework |
| Base loaders | ✅ | ✓ | ✓ | ✓ | Neo4j patterns |
| Test fixtures | ✅ | ✓ | ✓ | ✓ | Shared utilities |
| **Domain-Specific** |
| SAM.gov client | ❌ | ✓ | - | - | SBIR enrichment |
| Stata readers | ❌ | - | ✓ | - | USPTO patents |
| ML models | ❌ | - | - | ✓ | CET classification |

### Reusability Metrics

- **Shared Dependencies**: 10 / 12 (83%)
- **Shared Patterns**: 7 / 7 (100%)
- **Shared Infrastructure Code**: ~2,000 LOC (estimated 90% reuse)
- **Module-Specific Code**: ~1,500 LOC per module (10% unique)

---

## 7. Implementation Recommendations

### 7.1 Directory Structure for Shared Code (Post-Consolidation)

**Current Structure** (to be refactored):

```text
src/
├── extractors/              # Stage 1: Data extraction
├── validators/              # Stage 2: Schema validation
├── enrichers/               # Stage 3: External enrichment
├── transformers/            # Stage 4: Business logic
├── loaders/                 # Stage 5: Neo4j loading
├── assets/                  # Dagster asset definitions
├── config/                  # Configuration management
├── models/                  # Pydantic data models
└── utils/                   # Shared utilities
```

### Target Consolidated Structure

```text
src/
├── core/                    # Consolidated core functionality
│   ├── assets/             # Unified asset definitions
│   │   ├── base_asset.py   # Base asset class with monitoring
│   │   ├── ingestion.py    # Consolidated ingestion assets
│   │   ├── enrichment.py   # Consolidated enrichment assets
│   │   └── loading.py      # Consolidated loading assets
│   ├── config/             # Single configuration system
│   │   ├── loader.py       # Unified configuration loader
│   │   ├── schemas.py      # Consolidated Pydantic schemas
│   │   └── validation.py   # Configuration validation
│   ├── models/             # Consolidated data models
│   │   ├── base.py         # Base model classes
│   │   ├── awards.py       # Award-related models
│   │   ├── companies.py    # Company-related models
│   │   └── patents.py      # Patent-related models
│   └── monitoring/         # Unified performance monitoring
│       ├── metrics.py      # Performance metrics collection
│       ├── alerts.py       # Alert management
│       └── dashboard.py    # Monitoring dashboard
├── pipeline/               # Pipeline-specific logic
│   ├── extraction/         # Data extraction components
│   ├── enrichment/         # Data enrichment components
│   ├── transformation/     # Data transformation components
│   └── loading/            # Data loading components
├── shared/                 # Shared utilities and helpers
│   ├── database/           # Database clients and utilities
│   │   ├── neo4j_client.py # Neo4j client wrapper
│   │   ├── duckdb_client.py# DuckDB client wrapper
│   │   └── connection.py   # Connection management
│   ├── validation/         # Validation logic
│   │   ├── base.py         # Base validation framework
│   │   ├── quality.py      # Data quality checks
│   │   └── schema.py       # Schema validation
│   └── utils/              # Common utilities
│       ├── text.py         # Text processing utilities
│       ├── dates.py        # Date handling utilities
│       ├── files.py        # File processing utilities
│       └── performance.py  # Performance utilities
└── tests/                  # Unified testing framework
    ├── fixtures/           # Shared test fixtures
    ├── helpers/            # Test utilities
    └── scenarios/          # Test scenarios
```

### Migration Benefits

- **Reduced Duplication**: 30-60% reduction in duplicate code
- **Consistent Patterns**: Unified approaches across all components
- **Better Organization**: Clear separation of concerns
- **Easier Maintenance**: Centralized shared functionality

### 7.2 Import Conventions

```python

## Shared infrastructure (always available)

from src.common.config import load_config
from src.common.quality import BaseValidator, QualityReport
from src.loaders.base_loader import BaseNeo4jLoader
from src.models.base import BaseEntity

## Module-specific (only import what you need)

from src.sbir.enrichment import SAMGovClient
from src.uspto.extractors import StataExtractor
from src.ml.models import CETClassifier  # Requires ml extras
```

### 7.3 Configuration Naming Conventions

```yaml

## config/base.yaml (shared settings)

neo4j:
  uri: bolt://localhost:7687
  batch_size: 1000

logging:
  level: INFO
  dir: logs/

## config/sbir/ingestion.yaml (module-specific)

sbir:
  chunk_size: 5000
  sam_gov_api_key: ${SAM_GOV_API_KEY}

## config/uspto/extraction.yaml (module-specific)

uspto:
  chunk_size: 10000
  handle_missing_dates: true

## config/cet/classification.yaml (module-specific)

cet:
  confidence_thresholds:
    high: 70
    medium: 40
```

---

## 8. Future Standardization Opportunities

### 8.1 Shared Entity Resolution Framework

Currently each module has custom fuzzy matching logic. Consider:

```python

## src/common/entity_resolution.py

from rapidfuzz import fuzz
from typing import List, Tuple

class EntityResolver:
    """Shared entity resolution across SBIR, USPTO, CET modules."""

    def fuzzy_match(
        self,
        query: str,
        candidates: List[str],
        threshold: float = 0.80
    ) -> List[Tuple[str, float]]:
        """Universal fuzzy matching."""
        matches = []
        for candidate in candidates:
            score = fuzz.ratio(query, candidate) / 100.0
            if score >= threshold:
                matches.append((candidate, score))
        return sorted(matches, key=lambda x: x[1], reverse=True)
```

**Benefit**: Consistency across SBIR company matching, USPTO entity deduplication, and CET validation.

### 8.2 Shared Caching Layer

Consider SQLite-based caching for all modules:

```python

## src/common/cache.py

import sqlite3
from functools import wraps

class CacheManager:
    """Shared cache for API responses, lookups, computations."""

    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)

    def cached(self, key_fn):
        """Decorator for caching function results."""
        @wraps(key_fn)
        def wrapper(*args, **kwargs):
            key = key_fn(*args, **kwargs)
            cached_value = self.get(key)
            if cached_value:
                return cached_value
            result = key_fn(*args, **kwargs)
            self.set(key, result)
            return result
        return wrapper
```

### Usage

- SBIR: Cache SAM.gov API responses
- USPTO: Cache patent lookups
- CET: Cache classification results

### 8.3 Shared Evaluation Framework

Extend CET evaluation framework to all modules:

```python

## src/common/evaluation.py

class EvaluationFramework:
    """Shared evaluation across all pipelines."""

    def calculate_agreement(
        self,
        predictions: List[Any],
        ground_truth: List[Any]
    ) -> Dict[str, float]:
        """Calculate precision, recall, F1, Cohen's kappa."""
        pass

    def generate_confusion_matrix(
        self,
        predictions: List[str],
        ground_truth: List[str],
        labels: List[str]
    ) -> pd.DataFrame:
        """Generate confusion matrix for any classification task."""
        pass
```

---

## 9. Key Takeaways

### ✅ Strengths

1. **High Reusability**: 85% of dependencies shared across modules
2. **Consistent Patterns**: Configuration, logging, validation, loading patterns are standardized
3. **Modular Design**: Clear separation between shared infrastructure and module-specific logic
4. **Optional ML**: ML dependencies isolated with `poetry extras` - other modules remain lightweight

### ⚠️ Risks

1. **Dependency Bloat**: Adding scikit-learn + spaCy increases installation size by ~500MB
2. **Version Conflicts**: Ensure pandas/pydantic versions compatible across all module needs
3. **Coupling Risk**: Shared base classes can create tight coupling if not carefully designed

### 🎯 Recommendations

1. **Promote rapidfuzz to main dependencies** (used by all modules)
2. **Use optional extras for ML stack** (keeps base installation lean)
3. **Document shared patterns in code comments** (improve discoverability)
4. **Create shared utilities library** (entity resolution, caching, evaluation)
5. **Standardize configuration naming** (module/feature/parameter hierarchy)

---

**Document Version**: 1.0
**Last Updated**: October 26, 2025
**Next Review**: After first module deployment
