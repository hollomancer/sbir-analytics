# Test Execution and Scheduling

**Type**: Testing Guide

**Maintainer**: Conrad Hollomon

**Last-Reviewed**: 2026-08-03

**Status**: Active

`.github/workflows/ci.yml` is the repository's only GitHub Actions workflow. It is event-driven;
there is no nightly or weekly workflow in this repository.

## Pull requests

Every pull request runs:

- Ruff lint and format checks, MyPy, architecture guards, repository guards, Compose validation,
  and actionlint.
- Bandit and detect-secrets.
- Four duration-balanced shards of `tests/unit/`, excluding tests marked `slow`.
- A Docker build and entrypoint smoke test only when Docker build inputs change.
- The developer setup-script check only when `scripts/setup_dev.sh`, `uv.lock`, or
  `pyproject.toml` changes.

The unit shards use `tests/.test_durations` for balancing. Regenerate that file serially when timings
materially drift:

```bash
uv run pytest tests/unit/ -m "not slow" --store-durations -n0
```

To reproduce one CI group locally, use the same `pytest-split` arguments. Groups are numbered
1 through 4:

```bash
uv run pytest tests/unit/ -m "not slow" \
  --splits 4 --group 1 \
  --splitting-algorithm least_duration \
  --durations-path tests/.test_durations
```

`pytest-split` assigns tests using recorded duration; xdist may still parallelize within a group.
Do not use the retired `pytest-shard`, `--shard-id`, or zero-based shard numbering.

## Pushes to `main` and manual runs

Pushes to `main` and `workflow_dispatch` run the full `tests/` tree with a Neo4j service and
coverage. The workflow excludes `requires_api` tests and documents a small number of explicit test
deselections that represent known pre-existing failures. Read the workflow before changing those
exceptions; delete a deselection when its underlying test is repaired.

Fast PR shards do not replace the full post-merge gate. This split keeps pull-request feedback short
while still exercising integration, functional, E2E, golden, slow, and validation tests on `main`.

## Local selection

Use the narrowest command that proves a change:

```bash
make test-unit
make test-integration
make test-functional
make test-transition
make test-cet
make test-fiscal
make test-modernbert
make test
```

For E2E scenario selection, use the commands in [End-to-End Testing](e2e-testing.md).

## Scheduled operational work

Production extraction, enrichment, reporting, and materialization are scheduled on the self-hosted server
through Dagster or cron. They are operational data-plane work, not GitHub Actions tests. Before
inspecting or running them, read the
[self-hosted server runbook](../deployment/self-hosted-server.md#live-instance-on-the-server-host).

If a periodic regression suite is added later, document its trigger and prerequisites here only
after the workflow or server schedule exists. Do not describe proposed schedules as current CI.
