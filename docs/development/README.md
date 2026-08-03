---
Type: Overview
Owner: devops@project
Last-Reviewed: 2026-08-03
Status: active
---

# Development Documentation

Use this page as a router; commands and rules have one canonical owner.

## Start here

- [Getting started](../getting-started/README.md) - Installation and first local run
- [Docker development](docker.md) - Compose profiles, data, and troubleshooting
- [Testing index](../testing/index.md) - Local, Docker, E2E, and CI verification
- [Configuration reference](../configuration.md) - Load order and environment overrides

## Engineering conventions

- [Exception Handling](exception-handling.md) - Custom exception hierarchy and patterns
- [Logging Standards](logging-standards.md) - When to use logger vs console.print
- [Pre-commit and CI consistency](pre-commit-ci-consistency.md) - What runs locally and in CI

## Planning and architecture

- [Spec Workflow Guide](spec-workflow-guide.md) - Using specifications
- [Architecture overview](../architecture/detailed-overview.md) - Package and deployment boundaries
- [Steering documents](../steering/) - Durable identity, evidence, orchestration, and quality rules
- `make docs-check` - Repository hygiene guard: documentation links and anchors, stale
  paths and commands, spec-registry coverage, and references to removed `src/` modules or
  archived scripts (so a failure here is not always a documentation problem)

---

For deployment guides, see [Deployment Documentation](../deployment/README.md).
For testing guides, see the [Testing Index](../testing/index.md).
