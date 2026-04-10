# Contributing to SBIR ETL Pipeline

Thank you for your interest in contributing to the SBIR ETL Pipeline project! This document provides guidelines and instructions for development.

## Table of Contents

- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Code Quality Standards](#code-quality-standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Pull Request Process](#pull-request-process)
- [Documentation Standards](#documentation-standards)

## Development Setup

### Prerequisites

- Python 3.11 or 3.12
- uv for dependency management ([install uv](https://github.com/astral-sh/uv))
- Docker (for local Neo4j)
- Git

### Initial Setup

1. **Clone the repository:**

   ```bash
   git clone <repository-url>
   cd sbir-analytics
   ```

2. **Install dependencies with uv:**

   ```bash
   uv sync
   ```

3. **Start Neo4j with Docker:**

   ```bash
   docker compose --profile dev up neo4j -d
   ```

4. **Configure environment:**

   ```bash
   cp .env.example .env
   # Edit .env: set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
   ```

5. **Verify setup:**

   ```bash
   uv run pytest
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy sbir_etl/
   ```

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes

- Follow the project structure and conventions
- Add tests for new functionality
- Update documentation as needed
- Keep commits atomic and well-described

### 3. Run Code Quality Checks

See the [Testing Index](docs/testing/index.md) for the complete list of commands.

```bash
# Run all checks (lint, type, test)
make check-all

# Or run individually:
uv run ruff format .
uv run ruff check . --fix
uv run mypy sbir_etl/
uv run pytest -v --cov=sbir_etl
```

### 4. Commit Your Changes

Follow the commit message guidelines (see below).

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on the repository.

## Code Quality Standards

### Code Formatting and Linting

- **Ruff**: Handles both formatting and linting, configured in `pyproject.toml`

  ```bash
  # Format code
  ruff format .

  # Check and fix issues
  ruff check . --fix
  ```

  Key rules:

  - Follow PEP 8 style guide
  - Use type hints for all functions
  - No unused imports or variables
  - Consistent import ordering (isort)
  - Line length: 100 characters
  - Target version: Python 3.11

### Type Checking

- **MyPy**: Standard type checking with gradual typing support

  ```bash
  mypy sbir_etl/
  ```

  Requirements:

  - Functions should have type hints (gradual typing supported)
  - Minimize `Any` types where possible
  - Handle Optional types explicitly

### Security

- **Bandit**: Security linting for Python

  ```bash
  bandit -r sbir_etl/
  ```

### Documentation

- All modules, classes, and functions must have docstrings
- Use Google-style docstrings
- Example:

  ```python
  def process_data(data: pd.DataFrame, threshold: float = 0.95) -> pd.DataFrame:
      """Process and validate SBIR award data.

      Args:
          data: Raw SBIR award DataFrame
          threshold: Minimum completeness threshold (default: 0.95)

      Returns:
          Validated DataFrame with quality checks applied

      Raises:
          ValidationError: If data is empty or fails quality checks
          ConfigurationError: If threshold is invalid
      """
  ```

### Logging Standards

We use `loguru` for structured logging. See the [Logging Standards Guide](docs/development/logging-standards.md) for details on:

- When to use `logger` vs `console.print`
- Structured context and log levels
- Performance considerations

### Exception Handling

All custom exceptions must use the centralized exception hierarchy in `sbir_etl/exceptions.py`. This provides structured error information, retry guidance, and consistent logging.

**Quick Reference:**

```python
# ✅ Use specific SBIR ETL exceptions
from sbir_etl.exceptions import ConfigurationError, APIError

# Provide rich context
raise ConfigurationError(
    "Invalid config value",
    config_key="neo4j.uri",
    component="config.loader",
    details={"provided_value": "invalid"}
)

# Wrap external exceptions with cause
try:
    response = httpx.get(url)
except httpx.HTTPError as e:
    raise APIError("Request failed", api_name="usaspending", cause=e)
```

**Exception Hierarchy:**

- `ExtractionError` - Data extraction failures
- `ValidationError` - Schema/quality validation
- `EnrichmentError` / `APIError` / `RateLimitError` - Enrichment and API failures
- `TransformationError` / `CETClassificationError` - Transformation stage failures
- `ConfigurationError` - Configuration issues
- `FileSystemError` - File I/O operations
- `DependencyError` / `RFunctionError` - Missing dependencies

**Best Practices:**

1. Always use specific exceptions (not generic `ValueError`, `RuntimeError`)
2. Provide `component` and `operation` context for debugging
3. Include actionable details in error messages
4. Document raised exceptions in function docstrings
5. Use `retryable=True` for transient errors

For comprehensive patterns, error codes, and detailed examples, see the [Exception Handling Guide](docs/development/exception-handling.md).

## Pull Request Process

### Before Submitting

1. ✅ All tests pass
2. ✅ Code coverage is ≥85%
3. ✅ Black, Ruff, and MyPy checks pass
4. ✅ Documentation is updated
5. ✅ Commit messages follow guidelines
6. ✅ Branch is up to date with main

### PR Template

```markdown

## Description

Brief description of changes

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] All tests pass locally

## Checklist

- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] Tests cover new functionality
- [ ] No breaking changes (or documented)
```

### Review Process

1. At least one approval required
2. All CI checks must pass
3. No merge conflicts
4. Address all review comments

## Documentation Standards

- Use Diátaxis types: Tutorials, How-to guides, Explanations, References.
- Every doc includes front-matter: `Type`, `Owner`, `Last-Reviewed`, `Status`.
- Docs live in `docs/` (see `docs/index.md`). Specs and tasks live in `specs/`.
- Changes to architecture, data contracts, or performance must update relevant docs/specs in the same PR.
- Neo4j schema changes must update `docs/schemas/neo4j.md` and `packages/sbir-graph/sbir_graph/loaders/` together.
- New features requiring user documentation should include guides in `docs/guides/` (e.g., statistical reporting, containerization).
- Configuration changes must be documented in relevant guides and configuration examples.

## Project Structure

```text
sbir-analytics/
├── sbir_etl/              # Core ETL library
│   ├── config/            # Configuration management and schemas
│   ├── extractors/        # Stage 1: Data extraction from various sources
│   ├── validators/        # Stage 2: Schema validation and data quality checks
│   ├── enrichers/         # Stage 3: External enrichment and fuzzy matching
│   │   └── usaspending_api_client.py  # Iterative enrichment refresh (see docs/enrichment/usaspending-iterative-refresh.md)
│   ├── transformers/      # Stage 4: Business logic and graph preparation
│   ├── models/            # Pydantic data models and type definitions
│   ├── utils/             # Shared utilities (logging, metrics, performance)
│   ├── quality/           # Data quality validation modules
│   └── exceptions.py      # Centralized exception hierarchy
├── packages/
│   ├── sbir-analytics/    # Dagster orchestration
│   │   └── sbir_analytics/
│   │       ├── assets/    # Dagster asset definitions (pipeline orchestration)
│   │       ├── cli/       # Command-line interface
│   │       └── definitions.py  # Dagster repository definitions
│   ├── sbir-graph/        # Graph database integration
│   │   └── sbir_graph/
│   │       └── loaders/   # Stage 5: Neo4j loading and relationship creation
│   └── sbir-ml/           # Machine learning (CET, transition, PaECTER)
├── tests/                 # Test suite
├── config/                # Configuration files
├── data/                  # Data files (not in git)
├── docs/                  # Additional documentation
├── specs/           # specifications (active system)
├── docs/steering/        # Agent steering documents (architectural patterns)
└── archive/openspec/      # Archived OpenSpec content (historical reference)
```

## Questions or Issues?

- Open an issue on GitHub
- Reach out to @hollomancer
- Check existing documentation and issues

Thank you for contributing! 🎉
