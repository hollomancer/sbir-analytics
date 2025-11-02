# Project Structure & Organization

## 🎉 Consolidated Architecture (2025-01-01)

The project has undergone major consolidation to eliminate code duplication and improve maintainability. The architecture now follows a streamlined modular ETL design with clear separation of concerns:

**Key Consolidation Achievements:**
- ✅ **Asset Consolidation**: USPTO assets unified into single file (`src/assets/uspto_assets.py`)
- ✅ **Configuration Consolidation**: Hierarchical PipelineConfig with 16+ consolidated schemas
- ✅ **Model Consolidation**: Unified Award model replaces separate implementations
- ✅ **Docker Consolidation**: Single profile-based docker-compose.yml
- ✅ **Utility Consolidation**: Performance monitoring and utilities streamlined

## Source Code Architecture

The project follows a consolidated modular ETL architecture with clear separation of concerns:

```
src/
├── assets/                 # Dagster asset definitions (pipeline orchestration)
├── config/                 # Configuration management and schemas
├── extractors/             # Stage 1: Data extraction from various sources
├── validators/             # Stage 2: Schema validation and data quality checks
├── enrichers/              # Stage 3: External enrichment and fuzzy matching (includes fiscal enrichers)
├── transformers/           # Stage 4: Business logic and graph preparation (includes fiscal transformers)
├── loaders/                # Stage 5: Neo4j loading and relationship creation
├── models/                 # Pydantic data models and type definitions
├── utils/                  # Shared utilities (logging, metrics, performance)
├── quality/                # Data quality validation modules
├── ml/                     # Machine learning models (CET classification)
└── transition/             # Technology transition detection logic
```

## Key Architectural Patterns

### ETL Pipeline Stages
1. **Extract**: Raw data ingestion (SBIR CSV, USAspending PostgreSQL, USPTO)
2. **Validate**: Schema validation using Pydantic models
3. **Enrich**: External API enrichment and fuzzy entity matching
4. **Transform**: Business logic, deduplication, graph preparation
5. **Load**: Neo4j batch loading with relationship creation

### Consolidated Dagster Asset Organization
- **Unified Assets**: Major consolidation completed - USPTO assets in single file (`src/assets/uspto_assets.py`)
- **Consistent Naming**: Standardized prefixes (raw_, validated_, enriched_, transformed_, loaded_)
- **Jobs**: Defined in `src/assets/jobs/` for pipeline orchestration
- **Asset Checks**: Co-located with assets for quality validation
- **Groups**: Assets organized by functional area (sbir_ingestion, cet_pipeline, etc.)

### Consolidated Configuration Management
- **Hierarchical Schema**: Single PipelineConfig with 16+ consolidated schemas in `src/config/schemas.py`
- **Type Safety**: Complete Pydantic validation with custom validators
- **YAML Files**: Environment-specific configs in `config/` directory
- **Environment Overrides**: Standardized `SBIR_ETL__SECTION__KEY` format for runtime configuration
- **No Duplication**: All configuration patterns unified and documented

### Unified Data Models
- **Consolidated Models**: Award model replaces separate SbirAward implementations
- **Pydantic Validation**: All data structures use Pydantic for validation
- **Field Validation**: Custom validators for business rules (UEI format, date ranges)
- **Type Safety**: Strict typing throughout with MyPy enforcement
- **Consistent Patterns**: Standardized model structure across all domains

## Directory Conventions

### Configuration Files
```
config/
├── base.yaml              # Default settings (version controlled)
├── dev.yaml               # Development overrides
├── prod.yaml              # Production settings
├── cet/                   # CET-specific configurations
└── envs/                  # Environment-specific configs
```

### Data Organization
```
data/
├── raw/                   # Source data files (not in git)
├── processed/             # Intermediate processing results
├── transformed/           # Business logic outputs
├── validated/             # Quality-checked data
└── enriched/              # Externally enriched data
```

### Testing Structure
```
tests/
├── unit/                  # Component-level tests
├── integration/           # Multi-component tests
├── e2e/                   # End-to-end pipeline tests
├── fixtures/              # Test data and mock objects
└── conftest.py            # Shared test configuration
```

### Documentation
```
docs/
├── architecture/          # System design documents
├── data/                  # Data dictionaries and schemas
├── deployment/            # Deployment guides and runbooks
├── schemas/               # Neo4j schema documentation
└── performance/           # Performance benchmarks and analysis
```

## Naming Conventions

### Files and Modules
- **Snake case**: `sbir_awards.py`, `company_enricher.py`
- **Descriptive names**: Clearly indicate purpose and scope
- **Asset files**: End with `_assets.py` for Dagster asset modules

### Classes and Functions
- **PascalCase**: Classes use `SbirAward`, `CompanyEnricher`
- **Snake case**: Functions use `validate_awards()`, `enrich_companies()`
- **Type hints**: All functions must include complete type annotations

### Constants and Configuration
- **UPPER_SNAKE_CASE**: `DEFAULT_BATCH_SIZE`, `MAX_RETRY_ATTEMPTS`
- **Environment variables**: `SBIR_ETL__` prefix for all project variables

## Code Organization Principles

### Separation of Concerns
- **Single responsibility**: Each module has one clear purpose
- **Dependency injection**: Configuration and clients passed as parameters
- **Interface segregation**: Small, focused interfaces over large monolithic ones

### Error Handling
- **Explicit exceptions**: Custom exception classes for different error types
- **Graceful degradation**: Continue processing when possible, log failures
- **Quality gates**: Configurable thresholds for data quality validation

### Performance Considerations
- **Chunked processing**: Large datasets processed in configurable batches
- **Memory monitoring**: Built-in memory usage tracking and alerts
- **Lazy evaluation**: Data loaded and processed on-demand where possible

### Testing Strategy
- **Unit tests**: Test individual functions in isolation
- **Integration tests**: Test component interactions with real databases
- **Asset checks**: Dagster asset checks for data quality validation
- **Coverage target**: Maintain ≥85% test coverage

## Import Conventions

### Standard Import Order
1. Standard library imports
2. Third-party library imports
3. Local application imports (relative imports discouraged)

### Example Import Structure
```python
from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from src.config.loader import load_config
from src.models.sbir_award import SbirAward
```

## Related Documents

- **[product.md](product.md)** - Project overview and business context
- **[tech.md](tech.md)** - Technology stack and development tools
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Dagster asset organization patterns
- **[configuration-patterns.md](configuration-patterns.md)** - Configuration management examples
- **[quick-reference.md](quick-reference.md)** - Common commands and development setup