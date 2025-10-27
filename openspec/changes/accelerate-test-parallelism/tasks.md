sbir-etl/openspec/changes/accelerate-test-parallelism/tasks.md
## 1. Baseline & Design
- [ ] 1.1 Measure current pytest runtime locally (`pytest -q`) and via GitHub Actions (container workflow) to set a baseline (record per-target timing).
- [ ] 1.2 Identify tests/fixtures that rely on global state or serialize access (Neo4j, filesystem) and document required isolation fixes.
- [ ] 1.3 Evaluate parallelization approaches (pytest-xdist workers vs. Dagster asset sharding) and select the safest strategy for near-term wins.

## 2. Tooling & Configuration
- [ ] 2.1 Add `pytest-xdist` (and any helpers like `pytest-randomly`) to Poetry dependencies and export lists used in Docker builds.
- [ ] 2.2 Update `pyproject.toml` / Makefile to expose a `PYTEST_WORKERS` toggle (default `auto` in CI, opt-in locally).
- [ ] 2.3 Ensure coverage configuration (paths, `COVERAGE_FILE`, HTML output) supports parallel workers (use `.coverage.*` files + `coverage combine`).

## 3. Fixture & Infra Hardening
- [ ] 3.1 Refactor temp directories, test data copies, and Dagster contexts to avoid shared mutable state between workers.
- [ ] 3.2 Confirm Neo4j test container can serve multiple concurrent sessions; adjust health checks / retries if needed.
- [ ] 3.3 Add smoke tests that run with `-n auto` locally to catch regressions in fixture isolation.

## 4. CI Integration
- [ ] 4.1 Update `.github/workflows/container-ci.yml` (and any other GitHub Actions workflows) to pass the parallel flag/env to pytest.
- [ ] 4.2 Capture before/after timings in workflow logs and publish them in `reports/ci_timings.md` (or similar) for visibility.
- [ ] 4.3 Monitor the first few GitHub Actions runs for flakiness; fall back to serial if regressions are detected (document rollback plan).

## 5. Documentation & Enablement
- [ ] 5.1 Update `README.md` / `docs/testing.md` with instructions for running tests in parallel, troubleshooting, and overriding worker counts.
- [ ] 5.2 Add release notes summarizing the new testing strategy and expected speed improvements.
- [ ] 5.3 Define ongoing ownership for maintaining parallel test stability (assign codeowners or CI maintainers).
