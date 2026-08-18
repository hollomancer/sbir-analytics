# Test Execution and Scheduling

**Type**: Testing Guide

**Maintainer**: Conrad Hollomon

**Last-Reviewed**: 2026-08-03

**Status**: Active

`.github/workflows/ci.yml` is the repository's only GitHub Actions workflow. In addition to pull
requests and pushes to `main`, it runs a weekly regression suite at 08:17 UTC each Saturday.

## Pull requests

Every pull request runs:

- Ruff lint and format checks, MyPy, architecture guards, repository guards, Compose validation,
  and actionlint.
- Bandit and detect-secrets.
- Four duration-balanced shards of `tests/unit/`, excluding tests marked `slow`.
- Hermetic `tests/e2e/` cases, excluding external-API and real-data tests.
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

## Full and scheduled runs

Pushes to `main`, weekly scheduled runs, and `workflow_dispatch` run the full discoverable `tests/`
tree with a Neo4j service and branch coverage. The combined first-party coverage report must remain
at or above 70%. The workflow excludes `requires_api` tests. Files under `tests/validation/` are
operator programs excluded from pytest discovery; executable reference tests live under
`tests/integration/` so the full suite collects them.

Fast PR shards do not replace the full post-merge gate. This split keeps pull-request feedback short
while still exercising integration, functional, E2E, golden, and slow tests after merge and weekly.

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

`make ci-local` is the local analog of a pull-request run: `make lint`,
`make lint-boundaries`, Dagster definition validation, compose `config -q`,
Bandit, `detect-secrets scan --baseline`, `pytest tests/unit/ -m "not slow"`,
and hermetic `tests/e2e/`. It does not run actionlint, Neo4j integration,
the Docker image build, or the post-merge 70% coverage suite.

`make validate` (`lint` + `make test`) remains the local analog of
`test-full`: the whole `tests/` tree with `--cov-fail-under=70`.

For E2E scenario selection, use the commands in [End-to-End Testing](e2e-testing.md).

## Scheduled operational work

Production extraction, enrichment, reporting, and materialization are scheduled on the self-hosted server
through Dagster or cron. They are operational data-plane work, not GitHub Actions tests. Before
inspecting or running them, read the
[self-hosted server runbook](../deployment/self-hosted-server.md#live-instance-on-the-server-host).

The GitHub Actions schedule runs tests only. It does not access persistent server data or trigger
Dagster materializations.
