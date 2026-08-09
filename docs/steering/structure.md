---
Type: Steering
Owner: engineering@project
Last-Reviewed: 2026-08-03
Status: active
---

# Project Structure and Organization

For the full directory tree and pipeline architecture, see [architecture/detailed-overview.md](../architecture/detailed-overview.md). This document covers the developer-facing conventions: directory layout, naming rules, and code organization principles.

The conventions below organize code by **technical role** — extractors,
enrichers, transformers, loaders. That axis is orthogonal to
[epistemic tiers](epistemic-tiers.md), which govern what an artifact can be
trusted to support and what it costs to maintain. A module's directory tells you
what it does; its tier tells you how much weight it carries. Both apply.

## Directory Conventions

### Configuration Files

```text
config/
├── base.yaml              # Default settings (version controlled)
├── dev.yaml               # Local development overrides
├── docker.yaml            # Compose overrides
├── prod.yaml              # Live/server profile
├── test.yaml              # Test profile
└── <subsystem>/           # CET, transition, fiscal, Neo4j, and report config
```

### Data Organization

```text
data/                      # Local inputs and outputs; not committed
studies/<study-id>/        # Frozen analytical contract and study artifacts
reports/                   # Generated reports when a workflow creates them
```

### Testing Structure

```text
tests/
├── unit/                  # Component-level tests
├── integration/           # Multi-component tests
├── functional/            # Pipeline-level behavior
├── e2e/                   # End-to-end pipeline tests
├── golden/                # Stable expected outputs
├── validation/            # Numerical/reference checks and operators
└── fixtures/              # Test data and mock objects
```

### Documentation

```text
docs/
├── architecture/          # System design documents
├── data/                  # Sources, refreshes, and data dictionaries
├── deployment/            # Deployment guides and runbooks
├── schemas/               # Neo4j schema documentation
├── steering/              # Durable engineering and evidence rules
└── archive/               # Historical, non-operational documents
```

## Naming Conventions

### Files and Modules

- **Snake case**: `sbir_awards.py`, `company_fuzzy_matcher.py`
- **Descriptive names**: Clearly indicate purpose and scope
- **Asset files**: End with `_assets.py` for Dagster asset modules

### Classes and Functions

- **PascalCase**: Classes use `SbirAward`, `CompanyEnricher`
- **Snake case**: Functions use `validate_awards()`, `enrich_companies()`
- **Type hints**: New and changed public interfaces include useful annotations

### Constants and Configuration

- **UPPER_SNAKE_CASE**: `DEFAULT_BATCH_SIZE`, `MAX_RETRY_ATTEMPTS`
- **Configuration overrides**: `SBIR_ETL__SECTION__KEY` for nested application settings

## Code Organization Principles

Company-name normalization and similarity belong in `sbir_etl/identity`; callers select
an explicit versioned profile. See [company-identity.md](company-identity.md).

U.S. state, district, and territory normalization belongs in
`sbir_etl.identity.geography`. Callers use the strict profile unless they explicitly need
the named permissive compatibility behavior; no caller carries its own jurisdiction map.

Exact official award-key resolution and fail-closed recipient-identifier reconciliation
belong in `sbir_etl.identity.exact_awards`. USAspending and NIH adapters prepare canonical
source keys, but they share the same versioned resolver and recovery-status contract.

### Study Evidence Contracts

Externally citable studies declare a versioned contract in `studies/<study-id>/study.yaml`.
The evidence status records epistemic maturity (`exploratory` through `citable`), while the
materialization gate independently records whether production outputs may currently run.
A reproducible study may therefore have either an open or closed gate. Operational assets
must enforce their gate before reading sources or writing outputs; CI separately verifies
the manifest schema, frozen-artifact hashes, and implementation references.

### Transitional Script Dependencies

First-party packages may not add dependencies on `scripts/`. All three transitional execution
bridges are retired: the architecture guard's import and execution allowlists are empty, and
every formerly bridged script is now reached through a package API with the CLI retained as an
entry point. Any future bridge must be named in the guard with a reason and a removal
condition; it is a migration device, not a fifth epistemic tier and not an implicit
promotion of the script, and an `evidence` artifact may never depend on one.

The guard inspects both imports and literal Python-script targets in `subprocess` command
arguments, following simple local assignments. It is an architecture lint, not a runtime
sandbox, so dynamically constructed paths remain outside its static view. Hiding a
package-to-script dependency behind process execution does not change its direction.

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
- **Precision benchmark**: Transition scoring changes maintain the repository's ≥85% precision
  benchmark. Other coverage and quality gates are owned by CI and subsystem tests rather than a
  global prose target.

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
- **[company-identity.md](company-identity.md)** - Versioned company identity policies
- **[configuration.md](../configuration.md)** - Configuration management examples
- **[Getting started](../getting-started/README.md)** - Installation and common commands
