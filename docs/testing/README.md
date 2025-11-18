---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-01-XX
Status: active

---

# Testing Documentation

This directory contains comprehensive testing documentation for the SBIR ETL project.

## Quick Start

New to testing in this project? Start here:

- **[Quick Start Guide](quick-start.md)** - Get up and running with tests quickly
- **[Testing Environments](environments.md)** - Docker vs Neo4j Aura comparison

## Test Environment Setup

Choose your testing environment:

- **[Neo4j Aura Setup](neo4j-aura.md)** - Neo4j Aura Free testing setup (recommended)
- **[CI Aura Setup](ci-aura-setup.md)** - Configuring Neo4j Aura for CI/CD pipelines

## Testing Guides

Comprehensive guides for different types of testing:

- **[E2E Testing Guide](e2e-testing-guide.md)** - End-to-end testing comprehensive guide
- **[Validation Testing](validation-testing.md)** - Validation testing guide
- **[Categorization Testing](categorization-testing.md)** - CET categorization testing guide

## Test Coverage & Planning

Resources for improving and tracking test coverage:

- **[Coverage Gap Analysis](coverage-gap-analysis.md)** - Current test coverage analysis (Nov 2025)
- **[Coverage Improvement Plan](coverage-improvement-plan.md)** - Roadmap for improving test coverage

## Testing Best Practices

When writing tests for this project:

1. **Use appropriate fixtures** - See individual guides for domain-specific fixtures
2. **Follow naming conventions** - `test_*.py` for test files, `test_*` for test functions
3. **Leverage Neo4j Aura Free** - Recommended for both local and CI testing
4. **Run tests before committing** - `uv run pytest` to run the full suite
5. **Check coverage** - `uv run pytest --cov` to see coverage reports

## Related Documentation

- **[Development Guidelines](../development/)** - General development practices
- **[Architecture Documentation](../architecture/)** - System architecture overview
- **[Quality Assurance](../guides/quality-assurance.md)** - QA processes and standards

---

For questions or issues with testing, consult the relevant guide above or refer to the main [project README](../../README.md).
