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
sample data or start Dagster. The synthetic sample workflow does not
require external API credentials.

## Find the Right Place to Make a Change

| Area | Location |
|---|---|
| Reusable extraction, enrichment, validation, and models | `sbir_etl/` |
| Dagster assets, jobs, and sensors | `packages/sbir-analytics/` |
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

## Capacity and Data Provenance

This is a personal project. It is not the work product of a government agency.
See [capacity and provenance](docs/public/capacity-and-provenance.md).

When you contribute, you confirm these points:

1. You contribute in your personal capacity, or your employer permits the
   contribution. You have the right to release it under the MIT license.
2. The contribution is not work that you did as part of official government
   duties. You did not use government time, equipment, or accounts to make it.
3. The contribution uses public information only. It does not contain or rely
   on data from employment, credentials, agreements, or other non-public access.
4. If you work for a firm that holds or seeks SBIR/STTR awards, or for a firm
   that does business with an SBIR/STTR agency, you say so in the pull request.

A pull request that cannot meet these points will be closed.

Do not propose changes that rank, rate, or select firms for awards, visits,
meetings, or other official attention.

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
