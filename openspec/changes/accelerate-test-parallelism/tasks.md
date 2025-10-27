## 1. Baseline & Audit (Current State Documentation)
- [ ] 1.1 Measure current pytest runtime locally: `pytest -v --tb=short` and record per-test timing; document baseline in `reports/test-timing-baseline.json` (include test name, duration, marker).
- [ ] 1.2 Measure CI runtime: capture `docker compose ... up` → test completion time from `.github/workflows/container-ci.yml`; compare container startup + pytest overhead vs. pure pytest time.
- [ ] 1.3 Audit test suite for global state: scan `tests/` for tests that:
  - Write to shared temp directories (e.g., `/tmp`, `reports/`, `logs/`) without per-test isolation.
  - Use hardcoded resource names (Neo4j database names, filenames, ports).
  - Assume serial execution order (e.g., `test_b` depends on side effects from `test_a`).
  - Create/destroy external resources (Neo4j containers, temporary files) without cleanup guards.
  - Use module-level or class-level mutable state (singletons, cached connections).
- [ ] 1.4 Document findings in `docs/test-isolation-audit.md` with:
  - List of tests that require isolation fixes (test name, issue, required fix).
  - Shared resources and dependencies (Neo4j, temp dirs, fixtures).
  - Estimate effort for each isolation fix (1–2 lines, moderate refactor, major redesign).

## 2. Dependency & Tooling Setup
- [ ] 2.1 Add `pytest-xdist` (latest stable, e.g., `^3.6`) to `pyproject.toml` under `[tool.poetry.group.dev.dependencies]`; verify it installs alongside `pytest ^8.0.0` without conflicts.
- [ ] 2.2 Optional: Add `pytest-randomly` to shuffle test order and expose hidden dependencies (add to dev dependencies; this helps discover isolation issues).
- [ ] 2.3 Update `Dockerfile` to include `pytest-xdist` in the Poetry install stage (verify Poetry lock file includes new packages).
- [ ] 2.4 Update `pyproject.toml` `[tool.pytest.ini_options]` to add:
  - `addopts = "-v --cov=src --cov-report=term-missing --cov-report=html:/tmp/htmlcov --dist=loadscope"` (enable loadscope strategy for xdist).
  - Document `PYTEST_WORKERS` environment variable override: `addopts = "-n ${PYTEST_WORKERS:-1}"` (default 1 locally, overridable).
- [ ] 2.5 Ensure coverage configuration supports parallel workers:
  - Verify `.coveragerc` or `pyproject.toml [tool.coverage.*]` uses `parallel = true` and `data_file = .coverage`.
  - Add post-run `coverage combine` step to merge `.coverage.*` worker files.

## 3. Fixture & Infrastructure Hardening
- [ ] 3.1 **Temp directories:** Audit `tests/` for hardcoded paths (`/tmp/...`, `reports/...`). Refactor to use pytest's `tmp_path` fixture (per-test isolation) or `tempfile.mkdtemp()` with cleanup. Update any fixtures that create `reports/`, `logs/` to use temp directories or add test-id suffixes (e.g., `reports/test_<test_id>/`).
- [ ] 3.2 **Dagster context/resource isolation:** Review `tests/conftest.py` for shared Dagster context or resources. Ensure each test gets a fresh context (not module/session-scoped unless immutable). Add fixture isolation markers if needed (e.g., `@pytest.fixture(scope="function")` instead of `scope="module"`).
- [ ] 3.3 **Neo4j test isolation:** Review `tests/conftest.py` or Neo4j fixtures for:
  - Connection pool or global client usage. If present, ensure each test gets a unique session or connection pool.
  - Database selection: confirm test database name is unique or per-test (e.g., `neo4j_test_<worker_id>` or use in-memory mode if available).
  - Health checks and retries: verify Neo4j container health check (`scripts/neo4j/health_check.sh` or inline in compose) tolerates concurrent connections; adjust timeouts/retries if needed.
  - Document Neo4j concurrency requirements in `docs/test-isolation-audit.md`.
- [ ] 3.4 **Shared mutable state:** Search `tests/` for module-level variables, class variables, or cached imports that persist across tests. Add cleanup in fixtures or use `pytest.fixture(autouse=True)` to reset state.
- [ ] 3.5 **Add smoke test for fixture isolation:** Create `tests/test_parallel_fixtures.py` with a simple test that validates temp directory isolation and Neo4j connection independence under parallelism (run with `-n auto` locally to verify).

## 4. CI Integration & Testing
- [ ] 4.1 **Local parallel testing:** Update Makefile with a new target:
  ```makefile
  pytest-parallel:
    PYTEST_WORKERS=auto pytest -n auto --dist=loadscope --tb=short
  ```
  Test locally on the repo (`make pytest-parallel`) and document expected speedup (estimate from baseline).
- [ ] 4.2 **Coverage merge:** Add Makefile target to combine coverage files:
  ```makefile
  coverage-combine:
    coverage combine
    coverage report --skip-empty
    coverage html -d /tmp/htmlcov
  ```
- [ ] 4.3 **Update `.github/workflows/container-ci.yml`:**
  - Modify the "Start test compose and run pytest" step to export `PYTEST_WORKERS=auto` and add `-n auto --dist=loadscope` flags to pytest command.
  - Add a step before `docker compose down` to capture timing: run `pytest --co -q | wc -l` to count tests, measure total time, and log to a summary file (e.g., `reports/ci_timings.md`).
  - Add post-test step to run `coverage combine` if `PYTEST_WORKERS` > 1.
  - Capture logs/artifacts for first 2–3 runs to monitor for new flakiness or failures.
- [ ] 4.4 **Validate first parallel CI run:** Merge change into a feature branch, open a draft PR, and verify:
  - All tests pass with `PYTEST_WORKERS=auto`.
  - No new test failures (if failures appear, they may indicate isolation issues; document and return to step 3).
  - Timing is faster (compare to baseline from step 1.2).
  - Artifacts and logs are clean (no resource conflicts or connection timeouts).
  - If regressions detected, revert to serial mode (`PYTEST_WORKERS=1`) and triage.

## 5. Documentation & Rollout
- [ ] 5.1 **Create `docs/testing.md`:** Document:
  - Running tests locally: `pytest` (serial, default), `make pytest-parallel` (parallel, auto-workers).
  - Overriding worker count: `PYTEST_WORKERS=2 pytest -n 2 --dist=loadscope`.
  - Troubleshooting: common isolation issues, how to debug with serial mode (`PYTEST_WORKERS=1`), how to report flakiness.
  - CI behavior: note that CI runs with `PYTEST_WORKERS=auto` by default; flakiness should be reported immediately.
  - Neo4j considerations: confirm test database isolation, connection pool behavior, health check expectations.
- [ ] 5.2 **Update `README.md` Testing section:**
  - Add quick reference: "Run tests in parallel with `make pytest-parallel` (expected 2–4x speedup)."
  - Link to `docs/testing.md` for detailed guidance.
  - Note that test parallelism is enabled in CI by default; local use is optional.
- [ ] 5.3 **Create release notes / CHANGELOG entry:**
  - Title: "Test Suite Parallelization with pytest-xdist"
  - Highlight: Faster feedback loop (2–4x speedup in CI), improved developer experience.
  - Note any breaking changes (none expected) or migration steps (none required).
  - Link to `docs/testing.md` for details.
- [ ] 5.4 **Define ownership:** Assign a codeowner (or team) for maintaining parallel test stability. Add entry to `CODEOWNERS` or project governance doc (e.g., "CI/Test Infrastructure: @<github-handle>").
- [ ] 5.5 **Monitor & iterate:** After merge to main:
  - Monitor first 5–10 CI runs for unexpected flakiness or timeouts.
  - Collect timing data and compare to baseline (goal: 2–4x speedup).
  - If flakiness >5%, document root cause and triage fixes (e.g., isolation issue, fixture timing, external service).
  - Schedule a 1-week checkpoint to review metrics and adjust worker count or parallelism strategy if needed.

## 6. Optional Enhancements (Post-MVP)
- [ ] 6.1 **CI job toggles:** Add optional GitHub Actions input to disable parallelism for troubleshooting (e.g., run with `PYTEST_WORKERS=1` on manual trigger).
- [ ] 6.2 **Flakiness detection:** Integrate with test summary tooling (e.g., GitHub's native flakiness reporting or third-party service) to track test stability over time.
- [ ] 6.3 **Distributed test sharding:** If test suite grows beyond 100+ tests, consider test sharding across multiple GitHub Actions jobs (e.g., job1 tests `tests/unit/`, job2 tests `tests/integration/`) in addition to xdist worker parallelism.
- [ ] 6.4 **Performance dashboard:** Hook into existing performance monitoring (`src/utils/performance_*.py`) to track test suite performance trends (similar to enrichment pipeline monitoring).