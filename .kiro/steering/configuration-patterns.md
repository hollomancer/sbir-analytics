# Configuration Patterns

This document centralizes all configuration examples and patterns used throughout the SBIR analytics project.

## 🎉 Consolidated Configuration System (2025-01-01)

### Major consolidation completed:

- ✅ **Hierarchical PipelineConfig**: Single root configuration model with 16+ consolidated schemas
- ✅ **Unified Validation**: All configuration uses Pydantic for type safety and validation
- ✅ **Standardized Overrides**: Consistent `SBIR_ETL__SECTION__KEY` environment variable pattern
- ✅ **No Duplication**: All configuration patterns unified and documented in this single source

## Configuration Architecture

### Three-Layer Configuration System

```text
Layer 1: YAML Files (config/)
    ↓
Layer 2: Pydantic Validation (src/config/schemas.py)
    ↓
Layer 3: Runtime Configuration with Environment Overrides
```

### Configuration Files Structure

```text
config/
├── base.yaml              # Default settings (version controlled)
├── dev.yaml               # Development overrides
├── prod.yaml              # Production settings
├── cet/                   # CET-specific configurations
└── envs/                  # Environment-specific configs
```

## Data Quality Configuration

### Quality Thresholds

```yaml
data_quality:
  # Completeness requirements (percentage of non-null values)
  completeness:
    award_id: 1.00          # 100% required
    company_name: 0.95      # 95% required
    award_amount: 0.98      # 98% required
    naics_code: 0.85        # 85% required (enrichment target)
    
  # Uniqueness requirements (no duplicates allowed)
  uniqueness:
    award_id: 1.00          # No duplicate award IDs
    
  # Validity ranges
  validity:
    award_amount_min: 0.0
    award_amount_max: 5000000.0  # $5M max for Phase II
    award_date_min: "1983-01-01"
    award_date_max: "2025-12-31"
    
  # Quality gates and thresholds
  thresholds:
    max_duplicate_rate: 0.10      # Block if >10% duplicates
    max_missing_rate: 0.15        # Warn if >15% missing
    min_enrichment_success: 0.90  # Target 90% enrichment
    
  # Severity-based actions
  actions:
    on_error: "block"       # Block pipeline on errors
    on_warning: "continue"  # Log warnings but continue
    on_info: "log"          # Just log info
```

## Enrichment Configuration

### Enrichment Sources and Fallback Chain

```yaml
enrichment:
  # Source configuration with priority and confidence
  sources:
    original_data:
      enabled: true
      priority: 1
      confidence: 0.95
      
    usaspending_api:
      enabled: true
      priority: 2
      confidence: 0.90
      rate_limit: 100
      timeout_seconds: 30
      
    sam_gov_api:
      enabled: true
      priority: 3
      confidence: 0.85
      api_key_env: "SAM_GOV_API_KEY"  # pragma: allowlist secret
      rate_limit: 60
      timeout_seconds: 30
      
    fuzzy_match:
      enabled: true
      priority: 4
      similarity_threshold: 0.80
      confidence_base: 0.70
      
  # Batch processing configuration
  batch_size: 100              # Records per API call
  max_retries: 3               # Retry attempts
  timeout_seconds: 30          # Request timeout
  rate_limit_per_second: 10.0  # API rate limit
  
  # Confidence thresholds
  confidence_thresholds:
    high: 0.80
    medium: 0.60
    low: 0.40
    
  # Quality thresholds
  quality:
    min_success_rate: 0.90       # 90% enrichment target
    min_high_confidence: 0.75    # 75% high confidence target
    max_fallback_rate: 0.20      # Max 20% fallbacks
    
  # Fallback rules
  fallback_rules:
    enable_agency_defaults: true
    enable_sector_fallback: true
    sector_fallback_code: "5415"
    
    # Agency default mappings
    agency_defaults:
      DOD: "3364"    # Aerospace manufacturing
      HHS: "5417"    # Biotechnology R&D
      DOE: "5417"    # Energy R&D
      NASA: "5417"   # Space R&D
```

## Pipeline Orchestration Configuration

### Pipeline Processing Configuration

```yaml
pipeline:
  # Processing configuration
  chunk_size: 10000              # Records per processing chunk
  memory_threshold_mb: 2048      # Memory pressure threshold
  timeout_seconds: 300           # Processing timeout per chunk
  enable_incremental: true       # Support incremental processing
  
  # Asset execution configuration
  asset_execution:
    max_retries: 3
    retry_delay_seconds: 5
    enable_parallel: true
    max_parallel_assets: 4
    
## Performance tuning

performance:
  batch_size: 1000              # Neo4j batch size
  parallel_threads: 4           # Parallel processing threads
  retry_attempts: 3             # Retry failed operations
  backoff_strategy: exponential # Retry backoff strategy
  
  # Memory management
  memory_monitoring:
    enabled: true
    warning_threshold_mb: 1500
    critical_threshold_mb: 2000
    
  # Performance thresholds
  thresholds:
    duration_warning_seconds: 5.0
    memory_delta_warning_mb: 500.0
    memory_pressure_warn_percent: 80.0
    memory_pressure_critical_percent: 95.0
```

## Neo4j Configuration

### Database Connection and Performance

```yaml
neo4j:
  # Connection configuration
  uri_env_var: "NEO4J_URI"
  user_env_var: "NEO4J_USER"
  password_env_var: "NEO4J_PASSWORD"  # pragma: allowlist secret
  
  # Loading configuration
  loading:
    batch_size: 1000
    parallel_threads: 4
    transaction_timeout_seconds: 300
    retry_on_deadlock: true
    max_deadlock_retries: 3
    
  # Performance optimization
  performance:
    create_indexes: true
    create_constraints: true
    batch_operations: true
    enable_query_cache: true
    
  # Quality gates
  quality:
    load_success_threshold: 0.99 # 99% success rate required
    max_constraint_violations: 10
    enable_data_validation: true
```

## CET Classification Configuration

### CET Taxonomy Configuration

```yaml
cet:
  # Taxonomy configuration
  taxonomy:
    version: "NSTC-2025Q1"
    taxonomy_file: "config/cet/taxonomy.yaml"
    enable_hierarchy: true
    
  # Classification configuration
  classification:
    # TF-IDF vectorization
    vectorizer:
      ngram_range: [1, 3]      # Unigrams, bigrams, trigrams
      max_features: 50000      # Maximum vocabulary size
      min_df: 2                # Minimum document frequency
      max_df: 0.95             # Maximum document frequency
      sublinear_tf: true       # Apply sublinear term frequency scaling
      norm: l2                 # L2 normalization
      
    # Feature selection
    feature_selection:
      enabled: true
      method: chi2             # Chi-squared test
      k: 20000                 # Select top 20,000 features
      
    # Classifier parameters
    classifier:
      max_iter: 500
      solver: lbfgs           # Limited-memory BFGS
      n_jobs: -1              # Use all CPU cores
      class_weight: balanced  # Handle imbalanced classes
      random_state: 42        # Reproducibility
      
    # Probability calibration
    calibration:
      enabled: true
      method: sigmoid         # Platt scaling
      cv: 3                   # 3-fold cross-validation
      min_samples_per_class: 3
      
    # Confidence scoring bands
    scoring:
      bands:
        high:
          min: 70
          max: 100
          label: "High"
        medium:
          min: 40
          max: 69
          label: "Medium"
        low:
          min: 0
          max: 39
          label: "Low"
      max_supporting: 3       # Maximum supporting CET areas
```

## Environment Variable Overrides

### Override Format

```bash

## Format: SBIR_ETL__SECTION__SUBSECTION__KEY=value

export SBIR_ETL__DATA_QUALITY__MAX_DUPLICATE_RATE=0.05
export SBIR_ETL__ENRICHMENT__BATCH_SIZE=200
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__PIPELINE__CHUNK_SIZE=5000
```

### Common Environment Overrides

```bash

## Database connections

export SBIR_ETL__NEO4J__URI="bolt://production-neo4j:7687"
export SBIR_ETL__NEO4J__PASSWORD="secure_password"  # pragma: allowlist secret

## API keys

export SBIR_ETL__ENRICHMENT__SAM_GOV_API_KEY="your_api_key"  # pragma: allowlist secret

## Performance tuning

export SBIR_ETL__PIPELINE__CHUNK_SIZE=20000
export SBIR_ETL__PERFORMANCE__BATCH_SIZE=2000
export SBIR_ETL__PERFORMANCE__PARALLEL_THREADS=8

## Quality thresholds

export SBIR_ETL__DATA_QUALITY__MIN_ENRICHMENT_SUCCESS=0.85
export SBIR_ETL__ENRICHMENT__MIN_SUCCESS_RATE=0.88

## CET configuration

export SBIR_ETL__CET__CLASSIFICATION__MAX_FEATURES=75000
export SBIR_ETL__CET__SCORING__HIGH_MIN=75
```

### Override Model and Secret Mapping

There are two complementary layers for runtime configuration:

- SBIR_ETL overrides: Prefer `SBIR_ETL__...` env vars that mirror the YAML structure. These directly override loaded config values at runtime.
- Secret mapping: Some sections (e.g., `neo4j`) reference raw env var names such as `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`. The YAML keys (e.g., `uri_env_var`) specify which raw environment variables to read.

Example:

```yaml
neo4j:
  uri_env_var: "NEO4J_URI"
  user_env_var: "NEO4J_USER"
  password_env_var: "NEO4J_PASSWORD"
```

You can either set raw secrets:

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="dev_password"  # pragma: allowlist secret
```

Or override resolved values directly via SBIR_ETL overrides:

```bash
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__NEO4J__PASSWORD="dev_password"
```

Prefer SBIR_ETL overrides in development/CI for clarity and portability; use raw env secrets where infrastructure already manages them.

## Configuration Validation

### Pydantic Schema Example

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List

class DataQualityConfig(BaseModel):
    """Data quality validation thresholds."""
    max_duplicate_rate: float = Field(0.10, ge=0.0, le=1.0)
    max_missing_rate: float = Field(0.15, ge=0.0, le=1.0)
    min_enrichment_success: float = Field(0.90, ge=0.0, le=1.0)
    
    @field_validator('max_duplicate_rate')
    def validate_duplicate_rate(cls, v):
        if v > 0.5:
            raise ValueError('Duplicate rate cannot exceed 50%')
        return v

class EnrichmentConfig(BaseModel):
    """External API enrichment settings."""
    batch_size: int = Field(100, ge=1, le=1000)
    max_retries: int = Field(3, ge=1, le=10)
    timeout_seconds: int = Field(30, ge=5, le=300)
    rate_limit_per_second: float = Field(10.0, ge=0.1)
    
class PipelineConfig(BaseModel):
    """Main pipeline configuration."""
    data_quality: DataQualityConfig
    enrichment: EnrichmentConfig
    chunk_size: int = Field(10000, ge=100)
    enable_incremental: bool = True
```

## Configuration Loading Pattern

### Configuration Loader

```python
import yaml
import os
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def load_config(env: str = None) -> PipelineConfig:
    """Load and merge configuration files with environment overrides."""
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
    config_data = apply_env_overrides(config_data, prefix="SBIR_ETL__")
    
    # Validate with Pydantic
    return PipelineConfig(**config_data)
```

## Best Practices

### Configuration Management

- **Single source of truth**: Use this document for all configuration examples
- **Environment-specific**: Use environment files for deployment-specific settings
- **Secret management**: Never store secrets in YAML files, use environment variables
- **Validation**: Always use Pydantic schemas for type safety and validation
- **Documentation**: Document all configuration parameters with comments

### Configuration Updates

- **Update this document first** when adding new configuration patterns
- **Remove duplicate configuration** from other steering documents
- **Add references** to this document from other steering documents
- **Test configuration changes** in development environment first
- **Version configuration** changes with clear commit messages

## Related Documents

- **[data-quality.md](data-quality.md)** - Uses data quality configuration patterns
- **[enrichment-patterns.md](enrichment-patterns.md)** - Uses enrichment configuration patterns
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Uses pipeline configuration patterns
- **[neo4j-patterns.md](neo4j-patterns.md)** - Uses Neo4j configuration patterns
- **[tech.md](tech.md)** - Environment variable override examples
