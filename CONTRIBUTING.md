# Contributing to SBIR ETL Pipeline

Thank you for your interest in contributing to the SBIR ETL Pipeline project! This document provides guidelines and instructions for development.

## Table of Contents

- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Code Quality Standards](#code-quality-standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Pull Request Process](#pull-request-process)

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Poetry for dependency management
- Docker and Docker Compose (for running Neo4j locally)
- Git

### Initial Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd sbir-etl
   ```

2. **Install dependencies with Poetry:**
   ```bash
   poetry install
   ```

3. **Activate the virtual environment:**
   ```bash
   poetry shell
   ```

4. **Start local services (Neo4j) with Docker Compose:**
   ```bash
   docker-compose up -d neo4j
   ```

5. **Verify setup:**
   ```bash
   pytest
   black --check .
   ruff check .
   mypy src/
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

Before committing, ensure your code passes all quality checks:

```bash
# Format code with black
black .

# Lint with ruff
ruff check . --fix

# Type check with mypy
mypy src/

# Run tests with coverage
pytest --cov=src --cov-report=term-missing

# Security scan with bandit
bandit -r src/
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
          ValueError: If data is empty or threshold is invalid
      """
  ```

## Testing Guidelines

### Test Organization

```
tests/
├── unit/           # Unit tests for individual components
├── integration/    # Integration tests for multiple components
├── e2e/            # End-to-end pipeline tests
└── fixtures/       # Test data and fixtures
```

### Writing Tests

1. **Unit Tests**: Test individual functions/methods in isolation
   ```python
   def test_validate_awards_completeness():
       awards = [{"award_id": "A001", "agency": "DOD"}]
       report = validate_sbir_awards(awards, min_completeness=0.9)
       assert len(report.issues) == 0
   ```

2. **Integration Tests**: Test component interactions
   ```python
   def test_neo4j_batch_upsert(neo4j_client):
       nodes = [{"uei": "UEI001", "name": "Company A"}]
       metrics = neo4j_client.batch_upsert_nodes("Company", "uei", nodes)
       assert metrics.nodes_created["Company"] == 1
   ```

3. **Test Coverage**: Aim for ≥85% code coverage
   ```bash
   pytest --cov=src --cov-report=html
   # View coverage report: open htmlcov/index.html
   ```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_validators.py

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run tests in parallel
pytest -n auto
```

## SBIR Data Ingestion Guidelines

### Working with SBIR Data

When contributing to SBIR data ingestion components:

1. **Data Source Awareness**: Always reference the official SBIR.gov data dictionary and field definitions
2. **Validation Rules**: Any changes to validation logic must maintain backward compatibility
3. **Performance Considerations**: Test changes with the full ~533K record dataset
4. **Sample Data**: Use `tests/fixtures/sbir_sample.csv` for development testing

### SBIR-Specific Testing

- **Validation Tests**: Add unit tests for new validation rules in `test_sbir_validators.py`
- **Integration Tests**: Test end-to-end SBIR pipeline in `test_sbir_ingestion_assets.py`
- **Edge Cases**: Include tests for missing UEI, old awards, and invalid formats
- **Performance**: Monitor memory usage and processing time for large datasets

### Configuration Changes

When modifying SBIR configuration:

- Update `config/base.yaml` for new settings
- Add validation in `src/config/schemas.py`
- Document configuration options in `docs/sbir_ingestion.md`
- Test configuration loading and overrides

### Documentation Updates

- Update field descriptions in `docs/sbir_ingestion.md` when data structure changes
- Maintain API documentation for extractor and validator classes
- Keep validation rules documentation current
- Update README.md SBIR section for user-facing changes

## Commit Message Guidelines

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

### Examples

```bash
feat(validators): add uniqueness check for award IDs

Implement deduplication logic to identify duplicate award IDs
in the dataset. Adds new QualityIssue for duplicate records.

Closes #123
```

```bash
fix(neo4j): handle connection timeout gracefully

Add retry logic and better error messages for Neo4j connection
failures. Prevents pipeline crashes on transient network issues.
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

## Project Structure

```
sbir-etl/
├── src/                    # Source code
│   ├── core/              # Consolidated core functionality
│   │   ├── assets/        # Unified asset definitions
│   │   ├── config/        # Single configuration system
│   │   ├── models/        # Consolidated data models
│   │   └── monitoring/    # Unified performance monitoring
│   ├── pipeline/          # Pipeline-specific logic
│   │   ├── extraction/    # Data extraction components
│   │   ├── enrichment/    # Data enrichment components
│   │   ├── transformation/# Data transformation components
│   │   └── loading/       # Data loading components
│   ├── shared/            # Shared utilities and helpers
│   │   ├── database/      # Database clients and utilities
│   │   ├── validation/    # Validation logic
│   │   └── utils/         # Common utilities
│   └── tests/             # Unified testing framework
│       ├── fixtures/      # Shared test fixtures
│       ├── helpers/       # Test utilities
│       └── scenarios/     # Test scenarios
├── tests/                 # Test suite
├── config/                # Configuration files
├── data/                  # Data files (not in git)
├── docs/                  # Additional documentation
├── .kiro/specs/           # Kiro specifications (active system)
└── archive/openspec/      # Archived OpenSpec content (historical reference)
```

## Questions or Issues?

- Open an issue on GitHub
- Reach out to @hollomancer
- Check existing documentation and issues

Thank you for contributing! 🎉
