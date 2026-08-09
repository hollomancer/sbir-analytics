---
Type: Overview
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-08-04
Status: active
---

# Development Documentation

Use this page to find the current development guides. Each command or rule should
be explained in one place so the instructions do not drift apart.

## Start here

- [Contributing](../../CONTRIBUTING.md) - Scope, setup, verification, and pull requests
- [Getting started](../getting-started/README.md) - Installation and first local run
- [Docker development](docker.md) - Compose profiles, data, and troubleshooting
- [Testing index](../testing/README.md) - Local, Docker, E2E, and CI verification
- [Configuration reference](../configuration.md) - Load order and environment overrides

## Engineering conventions

- [Exception Handling](exception-handling.md) - Custom exception hierarchy and patterns
- [Logging Standards](logging-standards.md) - When to use logger vs console.print
- [Pre-commit and CI consistency](pre-commit-ci-consistency.md) - What runs locally and in CI

## Planning and architecture

- [Spec Workflow Guide](spec-workflow-guide.md) - Using specifications
- [Architecture overview](../architecture/detailed-overview.md) - Package and deployment boundaries
- [Steering documents](../steering/) - Project rules for identity matching, evidence,
  pipelines, and data quality
- `make docs-check` - Check links, section links, agent-file copies, old commands,
  the spec list, and references to removed code or archived scripts. A failure may
  come from code or configuration, not only from documentation.

---

For deployment guides, see [Deployment Documentation](../deployment/README.md).
For testing guides, see the [Testing Index](../testing/README.md).
