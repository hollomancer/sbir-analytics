## Why
- Container-based CI currently runs the entire Python test suite serially, so even lightweight unit tests wait behind heavier Dagster integration tests.
- Most tests are IO-bound (mocked Dagster assets, pandas operations) and would benefit from worker parallelism, but the project has never evaluated xdist or split-test strategies.
- Slower feedback is blocking recent Neo4j/Docker fixes; parallelizing pytest could recover minutes per run and highlight flakiness earlier.

## What Changes
- Benchmark the existing test matrix locally and in GitHub Actions to establish the current runtime envelope (per target, per workflow step).
- Prototype parallel execution using `pytest-xdist` (e.g., `-n auto` with loadscope) and document required isolation fixes (temp dirs, coverage config, shared fixtures).
- Update project config (pyproject options, Docker image dependencies, Make/CI helpers) to support opt-in parallel runs locally and enable it by default in GitHub Actions once stable.
- Add guidance/tests to ensure Dagster asset execution and external services (Neo4j) remain healthy under concurrent test runs; gate merges on the faster pipeline.

## Impact
- Affects GitHub Actions workflow files, Docker image dependencies, `pyproject.toml`, Makefile helpers, and test fixtures that assume serial order.
- Requires coordination with data/infra engineers so Neo4j containers can tolerate multiple concurrent client sessions.
- No external API or schema changes; effort is limited to build/test infrastructure.
