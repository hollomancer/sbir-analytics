---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-01-XX
Status: active

---

# Testing Documentation

This directory contains comprehensive testing documentation for the SBIR ETL project.

## Testing Philosophy

Our testing strategy aims for a balance of speed, reliability, and coverage across different layers of the application. We prioritize fast feedback for developers while ensuring robust validation of the entire ETL pipeline.

## Quick Start

New to testing in this project? Start here:

-   **[Neo4j Testing Environments Guide](neo4j-testing-environments-guide.md)**: Get up and running with tests quickly, covering both local Docker and cloud Neo4j Aura setups.
-   **[E2E Testing Guide](e2e-testing-guide.md)**: Comprehensive guide for end-to-end testing, including scenarios and optimizations.

## Test Tiers and Execution

The project utilizes a tiered testing approach to optimize for speed and coverage:

| Tier | Purpose | Recommended Environment | Execution Command |
|------|---------|-------------------------|-------------------|
| **Unit Tests** | Component-level validation | Local (no services) | `uv run pytest tests/unit/` |
| **Integration Tests** | Multi-component interactions | Local Docker / Aura Free | `uv run pytest tests/integration/` |
| **E2E Tests** | Full pipeline validation | Local Docker | `make docker-e2e-standard` |
| **Performance Tests** | Benchmarks, regression | Local Docker | `make docker-e2e-large` |

### Running All Tests

```bash
uv run pytest -v --cov=src
```

### Running Specific Test Tiers

```bash
# Run fast tests only (unit tests and small integration tests)
uv run pytest -v -m "not slow"

# Run slow tests only (e.g., ML training, heavy computation)
uv run pytest -v -m "slow"

# Run E2E tests (requires Docker)
make docker-e2e-standard
```

## Test Coverage Strategy

Our goal is to achieve and maintain high test coverage across all critical modules.

-   **[Test Coverage Strategy](test-coverage-strategy.md)**: A detailed document outlining current coverage gaps, a phased improvement plan, and best practices for maintaining coverage.

## Specific Testing Guides

-   **[Categorization Testing](categorization-testing.md)**: Guide for testing the company categorization system.
-   **[Validation Testing](validation-testing.md)**: Guide for testing the company categorization system against a specific validation dataset.
-   **[CLI Testing Guide](../cli/TESTING.md)**: Covers how to test the SBIR CLI implementation.

## Testing Best Practices

When writing tests for this project:

1.  **Follow Test Naming Conventions**:
    *   Test files: `test_<module_name>.py`
    *   Test functions: `test_<function_name>_<scenario>_<expected_outcome>()`
    *   Test classes: `Test<ClassName>`
2.  **Use Appropriate Fixtures**: Leverage `pytest` fixtures for setup, teardown, and providing test data.
3.  **Mock External Services**: Use `unittest.mock` or `pytest-mock` to mock external dependencies (e.g., APIs, databases) in unit tests.
4.  **Aim for High Coverage**: Strive for ≥80% overall code coverage, with higher targets for critical modules.
5.  **Write Clear and Concise Tests**: Each test should focus on a single piece of functionality and be easy to understand.
6.  **Run Tests Before Committing**: Always run relevant tests locally before pushing changes.
7.  **Update Documentation**: Ensure testing documentation is updated when test commands or strategies change.

## CI/CD Integration

Our CI/CD pipeline integrates testing at various stages to provide fast feedback and ensure code quality:

-   **Tier 1 (Speed)**: Fast tests run first for immediate feedback on PRs.
-   **Tier 2 (User Stories)**: Core functionality tests run after speed tier.
-   **Tier 3 (Performance)**: Performance checks run last (non-blocking).

For more details on CI/CD integration, refer to the [E2E Testing Guide](e2e-testing-guide.md#ci/cd-integration).

## Related Documentation

-   **[Development Guidelines](../development/)** - General development practices
-   **[Architecture Documentation](../architecture/)** - System architecture overview
-   **[Quality Assurance](../guides/quality-assurance.md)** - QA processes and standards
-   **[Contributing Guide](../../CONTRIBUTING.md)** - General guidelines for contributing to the project.

---

For questions or issues with testing, consult the relevant guide above or refer to the main [project README](../../README.md).