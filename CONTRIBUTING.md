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
- Neo4j Aura account (Free tier available) or Docker for local Neo4j
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

3. **Set up Neo4j Aura (recommended):**

   - Create a Neo4j Aura instance at [neo4j.com/cloud/aura](https://neo4j.com/cloud/aura)
   - Copy your connection URI and credentials

4. **Configure environment:**

   ```bash
   cp .env.example .env
   # Edit .env: set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
   ```

5. **Verify setup:**

   ```bash
   uv run pytest
   uv run black --check .
   uv run ruff check .
   uv run mypy src/
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
uv run black .
uv run ruff check . --fix
uv run mypy src/
uv run pytest -v --cov=src
```

### 4. Commit Your Changes

Follow the commit message guidelines (see below).

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on the repository.

## Code Quality Standards

### Code Formatting

- **Black**: Line length 100, Python 3.11 target

  ```bash
  black --line-length 100 .
  ```

### Linting

- **Ruff**: Configured in `pyproject.toml`

  ```bash
  ruff check .
  ```

  Key rules:

  - Follow PEP 8 style guide
  - Use type hints for all functions
  - No unused imports or variables
  - Consistent import ordering (isort)

### Type Checking

- **MyPy**: Strict type checking enabled

  ```bash
  mypy src/
  ```

  Requirements:

  - All functions must have type hints
  - No `Any` types without justification
  - Handle Optional types explicitly

### Security

- **Bandit**: Security linting for Python

  ```bash
  bandit -r src/
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

All custom exceptions must use the centralized exception hierarchy in `src/exceptions.py`. This provides structured error information, retry guidance, and consistent logging.

For detailed patterns and best practices, see the [Exception Handling Guide](docs/development/exception-handling.md).

#### When to Use Custom Exceptions

1. **Use specific exceptions** instead of generic Python exceptions:

   ```python
   # ❌ Don't use generic exceptions
   raise ValueError("Invalid config")
   raise RuntimeError("API call failed")

   # ✅ Use specific SBIR ETL exceptions
   from src.exceptions import ConfigurationError, APIError

   raise ConfigurationError(
       "Invalid config value",
       config_key="neo4j.uri",
       details={"provided_value": "invalid"}
   )

   raise APIError(
       "USAspending API request failed",
       api_name="usaspending",
       endpoint="/v2/awards/123",
       http_status=503,
       retryable=True
   )
   ```

2. **Provide rich context** in exception details:

   ```python
   from src.exceptions import DataQualityError

   raise DataQualityError(
       "Match rate below threshold",
       threshold=0.70,
       actual_value=0.58,
       component="enricher.usaspending",
       operation="enrich_awards",
       details={
           "awards_processed": 10000,
           "matches_found": 5800,
           "batch_id": "batch_2024_01"
       }
   )
   ```

3. **Wrap external exceptions** using `wrap_exception`:

   ```python
   from src.exceptions import wrap_exception, APIError, FileSystemError
   import httpx

   # Wrap HTTP errors
   try:
       response = httpx.get(url)
       response.raise_for_status()
   except httpx.HTTPError as e:
       raise wrap_exception(
           e,
           APIError,
           api_name="usaspending",
           endpoint=url,
           http_status=e.response.status_code if e.response else None
       )

   # Wrap file I/O errors
   try:
       with open(file_path) as f:
           data = f.read()
   except IOError as e:
       raise wrap_exception(
           e,
           FileSystemError,
           file_path=file_path,
           operation="read_file"
       )
   ```

4. **Use retryable flag** for transient errors:

   ```python
   from src.exceptions import Neo4jError

   raise Neo4jError(
       "Connection timeout",
       retryable=True,  # Caller should retry
       operation="create_node",
       query="MERGE (a:Award {award_id: $id})"
   )
   ```

#### Exception Hierarchy Quick Reference

```text
SBIRETLError (base - don't raise directly)
├── ExtractionError              # Data extraction failures
├── ValidationError              # Schema/quality validation failures
│   └── DataQualityError         # Quality thresholds not met
├── EnrichmentError              # Enrichment stage failures
│   └── APIError                 # External API failures
│       └── RateLimitError       # Rate limits exceeded
├── TransformationError          # Transformation stage failures
│   ├── TransitionDetectionError # Transition detection specific
│   ├── FiscalAnalysisError      # Fiscal analysis specific
│   ├── CETClassificationError   # CET classification specific
│   └── PatentProcessingError    # Patent processing specific
├── LoadError                    # Loading stage failures
│   └── Neo4jError               # Neo4j database operations
├── ConfigurationError           # Config loading/validation
├── FileSystemError              # File I/O operations
└── DependencyError              # Missing dependencies
    └── RFunctionError           # R function failures
```

#### Error Codes

All exceptions include optional status codes from `ErrorCode` enum for programmatic handling:

- **1xxx**: Configuration errors (CONFIG_LOAD_FAILED, CONFIG_VALIDATION_FAILED)
- **2xxx**: Data quality errors (VALIDATION_FAILED, QUALITY_THRESHOLD_NOT_MET)
- **3xxx**: External dependencies (NEO4J_QUERY_FAILED, API_REQUEST_FAILED, R_FUNCTION_FAILED)
- **4xxx**: File I/O errors (FILE_NOT_FOUND, FILE_READ_FAILED)
- **5xxx**: Pipeline stage errors (EXTRACTION_FAILED, ENRICHMENT_FAILED)

#### Best Practices

1. **Always provide component and operation** for debugging:
   ```python
   raise Neo4jError(
       "Failed to create node",
       component="loader.neo4j",
       operation="upsert_award_nodes"
   )
   ```

2. **Include actionable details** for operators:
   ```python
   raise DependencyError(
       "Required R package not installed",
       dependency_name="stateior",
       details={
           "install_command": "remotes::install_github('USEPA/stateior')",
           "required_version": ">=2.1.0"
       }
   )
   ```

3. **Document exceptions in docstrings**:
   ```python
   def enrich_awards(awards: pd.DataFrame) -> pd.DataFrame:
       """Enrich SBIR awards with USAspending data.

       Raises:
           APIError: If USAspending API request fails
           DataQualityError: If match rate below threshold
           ConfigurationError: If API credentials missing
       """
   ```

4. **Log exceptions with context**:
   ```python
   from src.exceptions import APIError
   import logging

   logger = logging.getLogger(__name__)

   try:
       enrich_data()
   except APIError as e:
       logger.error(
           "Enrichment failed",
           extra=e.to_dict(),
           exc_info=True
       )
       if e.retryable:
           retry_operation()
       else:
           raise
   ```

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
- Docs live in `docs/` (see `docs/index.md`). Specs and tasks live in `.kiro/specs/`.
- Changes to architecture, data contracts, or performance must update relevant docs/specs in the same PR.
- Neo4j schema changes must update `docs/schemas/neo4j.md` and `src/loaders/` together.
- New features requiring user documentation should include guides in `docs/guides/` (e.g., statistical reporting, containerization).
- Configuration changes must be documented in relevant guides and configuration examples.

## Project Structure

```text
sbir-analytics/
├── src/                    # Source code
│   ├── assets/            # Dagster asset definitions (pipeline orchestration)
│   ├── config/            # Configuration management and schemas
│   ├── extractors/        # Stage 1: Data extraction from various sources
│   ├── validators/        # Stage 2: Schema validation and data quality checks
│   ├── enrichers/         # Stage 3: External enrichment and fuzzy matching
│   │   └── usaspending_api_client.py  # Iterative enrichment refresh (see docs/enrichment/usaspending-iterative-refresh.md)
│   ├── transformers/      # Stage 4: Business logic and graph preparation
│   ├── loaders/           # Stage 5: Neo4j loading and relationship creation
│   ├── models/            # Pydantic data models and type definitions
│   ├── utils/             # Shared utilities (logging, metrics, performance)
│   ├── quality/           # Data quality validation modules
│   ├── ml/                # Machine learning models (CET classification)
│   ├── transition/        # Technology transition detection logic
│   ├── migration/         # Migration utilities
│   └── definitions.py     # Dagster repository definitions
├── tests/                 # Test suite
├── config/                # Configuration files
├── data/                  # Data files (not in git)
├── docs/                  # Additional documentation
├── .kiro/specs/           # Kiro specifications (active system)
├── .kiro/steering/        # Agent steering documents (architectural patterns)
└── archive/openspec/      # Archived OpenSpec content (historical reference)
```

## Questions or Issues?

- Open an issue on GitHub
- Reach out to @hollomancer
- Check existing documentation and issues

Thank you for contributing! 🎉
