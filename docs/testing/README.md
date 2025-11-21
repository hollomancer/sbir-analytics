---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-11-21
Status: active

---

# Testing Documentation

This directory hosts the complete testing playbook for SBIR ETL. The [Testing Index](index.md) is the authoritative reference for commands and workflows—update it whenever test instructions change so other docs can simply link there.

## Getting Started

- Read the [Testing Index](index.md) for local, Docker, CI, and performance commands.
- Need graph connectivity guidance? See [Neo4j Testing Environments](neo4j-testing-environments-guide.md).
- Running a full flow? Use the [E2E Testing Guide](e2e-testing-guide.md) for scenarios and CI integration.

## Supporting References

- [Test Coverage Strategy](test-coverage-strategy.md)
- [Categorization Testing](categorization-testing.md)
- [Validation Testing](validation-testing.md)
- [CLI Testing Guide](../cli/TESTING.md)

## Best Practices Snapshot

1. Follow pytest naming conventions (`test_<unit>_<scenario>()`).
2. Prefer fixtures over ad-hoc setup/teardown.
3. Mock external services for unit tests; reserve real API calls for integration/e2e.
4. Keep overall coverage ≥80% (higher for loaders and enrichers).
5. Update the index + relevant guide whenever you add new targets, markers, or workflows.

For additional context, review [Quality Assurance](../guides/quality-assurance.md) and the main [project README](../../README.md).
