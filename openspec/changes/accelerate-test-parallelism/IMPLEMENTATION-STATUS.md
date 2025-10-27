# Implementation Status: Accelerate Test Parallelism

**Last Updated:** 2024-10-26
**Status:** Proposal approved, ready for implementation (Phase 1: Audit & Baseline)

---

## Overview

This document tracks the progress of enabling parallel test execution in the SBIR ETL project to improve CI feedback loop speed from ~8–12 minutes (serial) to ~2–4 minutes (parallel with 4–8 workers).

**Related Infrastructure:**
- Performance Regression Check pipeline: `.github/workflows/performance-regression-check.yml` (established; validates enrichment performance)
- Container CI: `.github/workflows/container-ci.yml` (current serial test runner)
- Neo4j smoke tests: `.github/workflows/neo4j-smoke.yml` (validates Neo4j integration)

---

## Current Repository State

### Test Suite
- **Count:** 29 tests across `tests/` directory
- **Execution:** Serial, via Docker Compose in `.github/workflows/container-ci.yml`
- **Duration:** Estimated 8–12 minutes (baseline to be measured in Phase 1)
- **Types:** Unit tests (mocked), integration tests (Neo4j, Dagster assets)

### Infrastructure Foundation
- **Python version:** 3.11 (via `pyproject.toml`)
- **Test framework:** pytest 8.x with `pytest-cov`, `pytest-mark` support
- **Coverage:** Coverage.py configured in `pyproject.toml`
- **Docker:** Multi-stage Dockerfile with test stage; Poetry lock file present
- **CI:** GitHub Actions with Docker Compose orchestration

### Existing Performance Tooling
- **Observability:** `src/utils/performance_monitor.py`, `src/utils/performance_alerts.py`
- **Quality baselines:** `src/utils/quality_baseline.py`
- **Regression detection:** `scripts/detect_performance_regression.py`
- **Dashboarding:** `src/utils/quality_dashboard.py` (Plotly-based)
- **Asset integration:** `src/assets/sbir_usaspending_enrichment.py` (includes performance metrics)

These components validate that the repository is ready for parallelism (strong observability + CI automation already in place).

---

## Implementation Phases

### Phase 1: Audit & Baseline (Task Section 1, 2)
**Objective:** Understand test suite structure, dependencies, and current performance.

**Key Activities:**
1. Measure current serial test runtime locally and in CI
2. Scan for global state, shared resources, and isolation issues
3. Document findings in `docs/test-isolation-audit.md`
4. Add `pytest-xdist` to dependencies (non-breaking)

**Estimated Effort:** 4–6 hours
**Success Criteria:**
- Baseline timing documented (e.g., serial: 10 min, CI container: 12 min)
- Audit report identifies 3–5 potential isolation issues
- `pytest-xdist` dependency added and tests run with `-n auto` locally (no execution failures, yet to validate isolation)

---

### Phase 2: Isolation & Hardening (Task Sections 3, 4)
**Objective:** Fix test fixtures, refactor shared state, harden Neo4j integration.

**Key Activities:**
1. Refactor temp directory fixtures for per-test isolation
2. Audit and update Dagster context fixtures
3. Validate Neo4j test container supports concurrent connections
4. Add isolation smoke tests
5. Run first parallel CI tests and monitor for flakiness

**Estimated Effort:** 8–12 hours
**Success Criteria:**
- All 29 tests pass with `pytest -n auto --dist=loadscope` locally
- Neo4j container health checks confirm concurrent session support
- First 3 CI parallel runs show <5% new flakiness or failures
- Isolation smoke tests pass

---

### Phase 3: CI Integration & Rollout (Task Sections 5, 6)
**Objective:** Enable parallelism by default in CI, document, and monitor.

**Key Activities:**
1. Update `.github/workflows/container-ci.yml` to use `PYTEST_WORKERS=auto`
2. Add timing capture and reporting
3. Create `docs/testing.md` with local and CI guidance
4. Update README, CHANGELOG, and codeowners
5. Monitor first 10 CI runs for stability

**Estimated Effort:** 4–6 hours
**Success Criteria:**
- CI runs in parallel by default; timing is 2–4x faster than baseline
- Documentation is clear and discoverable
- No regression in test stability (flakiness ≤5%)
- Owner assigned for ongoing maintenance

---

## Risks & Mitigation

| Risk | Likelihood | Mitigation |
|------|------------|-----------|
| Test isolation issues surface during parallelism | Medium | Phase 1 audit identifies most issues; Phase 2 smoke tests validate |
| Neo4j container doesn't support concurrent sessions | Low | Documented in Phase 1; if true, fallback to serial Neo4j or test database sharding |
| Coverage reporting fails with parallel workers | Low | Ensure `parallel=true` in coverage config; use `coverage combine` step |
| Flakiness increases >5% after rollout | Low–Medium | Rollback plan: disable parallelism, investigate, re-enable after fixes |
| CI runner hardware changes, affecting timing assumptions | Low | Timing targets are estimates; document actual on stable runner; adjust if needed |

---

## Dependencies & Blockers

- **None critical.** All dependencies are optional development tools.
- **Soft dependency:** Neo4j test container behavior. If concurrent sessions are not supported, test suite may need restructuring (acceptable fallback: test sharding across jobs instead of worker parallelism).

---

## Success Metrics

### Phase 1 (Audit)
- [ ] Baseline timing measured (serial, CI)
- [ ] Isolation audit complete and documented
- [ ] pytest-xdist dependency added

### Phase 2 (Isolation)
- [ ] All tests pass in parallel locally
- [ ] <5% new flakiness in CI runs
- [ ] Isolation smoke tests pass

### Phase 3 (Rollout)
- [ ] CI runs 2–4x faster than baseline
- [ ] Flakiness stable (<5%) over 10+ runs
- [ ] Documentation complete and linked from README
- [ ] Owner assigned and monitoring plan in place

---

## Timeline & Ownership

**Proposed Timeline:** 2–3 weeks (3 phases, each 1 week)

**Ownership:** To be assigned (suggest: engineer with CI/test infrastructure expertise)

**Review Gate:** Proposal must be approved before Phase 1 implementation. Phase 1 findings may require design adjustments before proceeding to Phase 2.

---

## Related Issues & PRs

- Proposal: `openspec/changes/accelerate-test-parallelism/proposal.md`
- Tasks: `openspec/changes/accelerate-test-parallelism/tasks.md`
- Performance Regression Pipeline: `.github/workflows/performance-regression-check.yml`

---

## Appendix: Useful Commands

```bash
# Local testing
pytest -v --tb=short                           # Serial baseline
PYTEST_WORKERS=auto pytest -n auto             # Parallel (after phase 2)

# CI simulation (Docker)
docker compose -f docker-compose.yml -f docker/docker-compose.test.yml up --abort-on-container-exit

# Coverage reports
coverage report --skip-empty
coverage html -d /tmp/htmlcov

# Dependency check
pip show pytest-xdist

# Neo4j health
cypher-shell -u neo4j -p password "RETURN 1"
```
