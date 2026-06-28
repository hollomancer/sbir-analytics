# Project Structure & Organization

For the full directory tree and pipeline architecture, see [architecture/detailed-overview.md](../architecture/detailed-overview.md). This document covers the developer-facing conventions: directory layout, naming rules, and code organization principles.

## Directory Conventions

### Configuration Files

```text
config/
├── base.yaml              # Default settings (version controlled)
├── dev.yaml               # Development overrides
├── prod.yaml              # Production settings
├── cet/                   # CET-specific configurations
└── envs/                  # Environment-specific configs
```

### Data Organization

```text
data/
├── raw/                   # Source data files (not in git)
├── processed/             # Intermediate processing results
├── transformed/           # Business logic outputs
├── validated/             # Quality-checked data
└── enriched/              # Externally enriched data
```

### Testing Structure

```text
tests/
├── unit/                  # Component-level tests
├── integration/           # Multi-component tests
├── e2e/                   # End-to-end pipeline tests
├── fixtures/              # Test data and mock objects
└── conftest.py            # Shared test configuration
```

### Documentation

```text
docs/
├── architecture/          # System design documents
├── data/                  # Data dictionaries and schemas
├── deployment/            # Deployment guides and runbooks
├── schemas/               # Neo4j schema documentation
└── performance/           # Performance benchmarks and analysis
```

## Naming Conventions

### Files and Modules

- **Snake case**: `sbir_awards.py`, `company_fuzzy_matcher.py`
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

from sbir_etl.config.loader import load_config
from sbir_etl.models.sbir_award import SbirAward
```

## Related Documents

- **[product.md](product.md)** - Project overview and business context
- **[tech.md](tech.md)** - Technology stack and development tools
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Dagster asset organization patterns
- **[configuration.md](../configuration.md)** - Configuration management examples
- **[quick-reference.md](quick-reference.md)** - Common commands and development setup
