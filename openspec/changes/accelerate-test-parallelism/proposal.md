## Why
- Container-based CI currently runs the entire Python test suite serially, blocking feedback on Neo4j/Docker fixes and slowing developer iteration.
- The project now has mature performance monitoring, alerting, and regression detection infrastructure (`src/utils/performance_*.py`, CI workflows with benchmark tracking).
- Test suite is IO-bound (mocked Dagster assets, pandas operations, Neo4j integration tests) and would benefit significantly from worker parallelism.
- Parallelizing pytest can recover 2–4 minutes per run and surface flakiness earlier, enabling faster validation of the new performance-gated pipeline.

## What Changes
- **Audit & isolation:** Identify and document test fixtures, global state, and external service dependencies (Neo4j, temp directories, shared singletons) that require isolation fixes for safe concurrent execution.
- **Tooling upgrade:** Add `pytest-xdist` and helpers (`pytest-randomly` optional) to Poetry dependencies and Docker build exports; ensure coverage config supports parallel workers (`.coverage.*` files + `coverage combine`).
- **Configuration:** Update `pyproject.toml` and Makefile to expose a `PYTEST_WORKERS` toggle (default `auto` in CI, opt-in locally); document override mechanisms.
- **Fixture hardening:** Refactor temp directories, test data copies, and Dagster contexts to avoid shared mutable state; ensure Neo4j test container health checks and retry logic support concurrent client sessions.
- **CI integration:** Update `.github/workflows/container-ci.yml` to pass parallelism flag to pytest; capture before/after timings; monitor for flakiness and document rollback procedure.
- **Documentation:** Add `docs/testing.md` guidance for running tests in parallel, troubleshooting, and overriding worker counts; update README with expected speed improvements.

## Impact
- Affects: GitHub Actions workflows (`container-ci.yml`), `pyproject.toml`, Makefile, test fixtures, Docker image dependencies.
- Breaking: None (parallelism is opt-in by default locally; enabled in CI after validation).
- Requires coordination: Data/infra engineers must confirm Neo4j test containers tolerate multiple concurrent client sessions.
- No external API or schema changes; effort limited to CI/test infrastructure.
- Synergizes with existing performance-regression-check pipeline: faster feedback loop validates performance gates more reliably.