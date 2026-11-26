# Test Execution and Scheduling

**Type**: Testing Guide

**Maintainer**: Conrad Hollomon

**Last-Reviewed**: 2026-11-26

**Status**: Active

`.github/workflows/ci.yml` is the quality and test workflow. In addition to pull
requests and pushes to `main`, it runs a weekly regression suite at 08:17 UTC each Saturday.
`.github/workflows/literature-map.yml` is a separate manual job that refreshes the
OpenAlex literature map and opens a PR when the CSV changes.

## Pull requests

Every pull request runs:

- Ruff lint and format checks, MyPy, architecture guards, repository guards, Compose validation,
  and actionlint.
- Bandit and detect-secrets.
- Four duration-balanced shards of `tests/unit/`, excluding tests marked `slow`.
- Hermetic `tests/e2e/` cases, excluding external-API and real-data tests.
- The full `tests/` tree on Python 3.11 with branch coverage and the 70% gate (`Full Tests`). It
  includes `slow`, `tests/integration`, `tests/functional`, and golden tests. It runs in parallel
  with the unit shards. There is no separate integration-test job: every test that
  `-m "integration and not slow"` selects also runs here.
  Measured cost in November 2026: 3 minutes 13 seconds for the whole job on `main`; 2 minutes
  17 seconds locally on 4 cores; the `slow` set alone took 70 seconds locally.
- A Docker build and entrypoint smoke test only when Docker build inputs change.
- The developer setup-script check only when `scripts/setup_dev.sh`, `uv.lock`, or
  `pyproject.toml` changes.

The unit shards use `tests/.test_durations` for balancing. Regenerate that file serially, over the
same selection the shards run, when timings drift or many tests are added:

```bash
rm -f tests/.test_durations
uv run pytest tests/unit/ -m "not slow and not jev_preflight" \
  -n0 -p no:cacheprovider --store-durations --durations-path tests/.test_durations
```

Delete the old file first, so entries for removed tests do not survive. The serial run took
2 minutes 31 seconds on a 4-core machine in November 2026. There is no Make target because the
`Makefile` is a SHA-frozen artifact of a study contract. The
`Test durations` workflow (`.github/workflows/test-durations.yml`) runs the same commands monthly and on
manual dispatch. It uploads the new file as the `test-durations` artifact and writes counts of
missing and stale entries to the run summary. It does not commit: download the artifact and commit it
in an ordinary PR.

To reproduce one CI group locally, use the same `pytest-split` arguments. Groups are numbered
1 through 4:

```bash
uv run pytest tests/unit/ -m "not slow and not jev_preflight" \
  --splits 4 --group 1 \
  --splitting-algorithm least_duration \
  --durations-path tests/.test_durations
```

`pytest-split` assigns tests using recorded duration; xdist may still parallelize within a group.
Do not use the retired `pytest-shard`, `--shard-id`, or zero-based shard numbering.

A new push to a pull request cancels that pull request's older run. Runs on `main` (push, schedule,
manual) are never cancelled, so every merged commit gets the full suite.

## Full and scheduled runs

Pushes to `main`, weekly scheduled runs, and `workflow_dispatch` run the full discoverable `tests/`
tree with branch coverage on both Python 3.11 and 3.12, the two versions `requires-python`
allows. Pull requests run it on 3.11 only. The combined first-party coverage report must remain
at or above 70%. The workflow excludes `requires_api` tests. Files under `tests/validation/` are
operator programs excluded from pytest discovery; executable reference tests live under
`tests/integration/` so the full suite collects them.

The fast PR shards give quick unit-test feedback. The `Full Tests` job is the merge gate for the
whole tree and for coverage.

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
Bandit, `detect-secrets scan --baseline`, `pytest tests/unit/ -m "not slow and not jev_preflight"`,
and hermetic `tests/e2e/`. It does not run actionlint, the Docker image build, or the full suite with
the 70% coverage gate, which pull requests now also run. Run `make test` for that gate. The
`Makefile` is a SHA-frozen study artifact, so `ci-local` was not extended.

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
