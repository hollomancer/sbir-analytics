# Contributing

Thanks for helping improve the SBIR/STTR commercialization analytics project.
This is an experimental research codebase, so a useful contribution should make
a research result more trustworthy, reproducible, or understandable without
adding unnecessary operational complexity.

## Before You Start

Read the [research questions](docs/research-questions.md) first. They are the
scope gate for features and analyses. For implementation work, also review the
[architecture overview](docs/architecture/detailed-overview.md) and any relevant
document under `docs/steering/` or `specs/`.

## Set Up a Development Environment

The supported Python versions are 3.11 and 3.12 (`requires-python >=3.11,<3.13`). From the repository root:

```bash
make install
cp .env.example .env
make setup-local
make doctor
make test-smoke
```

See the full [getting-started guide](docs/getting-started/README.md) to generate
sample data, start Dagster, or run Neo4j. The synthetic sample workflow does not
require external API credentials.

## Find the Right Place to Make a Change

| Area | Location |
|---|---|
| Reusable extraction, enrichment, validation, and models | `sbir_etl/` |
| Dagster assets, jobs, and sensors | `packages/sbir-analytics/` |
| Neo4j loaders and queries | `packages/sbir-graph/` |
| CET and transition ML or heuristics | `packages/sbir-ml/` |
| Focused operational and analysis entry points | `scripts/` |
| Architecture and methodology | `docs/` |
| Feature requirements and task tracking | `specs/` |

Archived scripts and specifications are historical context, not active
extension points. If archived behavior needs to become active again, move it to
the appropriate live directory and add focused tests and documentation.

## Develop and Verify

Keep changes surgical and use the narrowest useful test while iterating:

```bash
uv run pytest path/to/test_file.py -v
make test-smoke
make test-unit
make lint
```

Run broader integration or end-to-end suites when the change crosses service or
pipeline boundaries. Those suites may require Docker, credentials, or local
datasets; the [testing index](docs/testing/README.md) documents the requirements.

The project uses Ruff for formatting and linting and MyPy for type checking.
Install the optional local hooks with:

```bash
uv run pre-commit install
```

Do not add real credentials, private datasets, or generated research outputs to
the repository. Prefer fixtures, temporary directories, and the synthetic sample
generator for reproducible tests.

## Open a Pull Request

A typical pull request includes:

1. An explanation of the problem and why the change is in scope.
2. The research question, bug, or maintenance need it supports.
3. User or developer impact.
4. Focused tests, or an explanation why the change is documentation-only.
5. Updates to affected documentation, configuration examples, and data contracts.
6. No unrelated cleanup.

Use a draft pull request while the implementation or validation is incomplete.
Document any test that could not be run and the credentials, data, or service it
requires.
