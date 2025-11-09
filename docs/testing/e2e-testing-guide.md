# E2E Testing Guide

This guide covers the enhanced end-to-end (E2E) testing capabilities for the SBIR ETL pipeline, optimized for MacBook Air development environments.

## Overview

The E2E testing system provides comprehensive validation of the entire SBIR ETL pipeline from data ingestion through Neo4j loading, with resource monitoring and MacBook Air compatibility.

## Quick Start

### Prerequisites

1. Copy `.env.example` to `.env` and configure:

   ```bash
   cp .env.example .env
   # Edit .env with your Neo4j credentials
   ```

2. Ensure Docker and Docker Compose are installed and running

### Running E2E Tests

#### Standard E2E Tests (Recommended)

```bash
make docker-e2e-standard
```

#### Quick Smoke Tests (Fastest)

```bash
make docker-e2e-minimal
```

#### Performance Tests (Larger datasets)

```bash
make docker-e2e-large
```

#### Edge Case Tests (Robustness)

```bash
make docker-e2e-edge-cases
```

#### Interactive Debugging

```bash
make docker-e2e-debug
```

### Cleanup

```bash
make docker-e2e-clean
```

## Testing Quick Reference

```bash

## Unit tests

pytest tests/unit/ -v

## Integration tests

pytest tests/integration/ -v

## E2E scenarios (containers)

make docker-e2e-minimal      # < 2 min (MacBook Air optimized)
make docker-e2e-standard     # 5-8 min (full validation)
make docker-e2e-large        # 8-10 min (performance focus)
make docker-e2e-edge-cases   # 3-5 min (robustness cases)
make docker-e2e-debug        # Interactive debugging

## Direct script fallback

python scripts/run_e2e_tests.py --scenario minimal
python scripts/run_e2e_tests.py --scenario standard
python scripts/run_e2e_tests.py --scenario large
python scripts/run_e2e_tests.py --scenario edge-cases

## Container tests

make docker-test
```

## Coverage & Performance Targets

- **Coverage goal**: ≥80% (CI enforces via coverage reports)
- **Current snapshot**: 29+ tests across unit, integration, and E2E suites
- **E2E standard scenario**: <10 minutes end-to-end
- **Memory ceiling**: <8GB to remain MacBook Air friendly
- **Match rate quality gate**: ≥70% during enrichment validation
- **Neo4j load success rate**: ≥99% across loading assets

## Testing Strategy

- **Unit tests** – Component-level validation lives in `tests/unit/`
- **Integration tests** – Multi-component checks in `tests/integration/`
- **End-to-end tests** – Containerized scenarios under `tests/e2e/`
- **Performance tests** – Benchmarks and regression detection exercises

## CI/CD Integration

### Test Execution Strategy

The CI system optimizes runtime by separating fast tests from long-running tests and prioritizing jobs:

#### Job Priority Tiers

CI jobs are organized into three priority tiers:

1. **Tier 1 (Speed)**: Fast tests run first for immediate feedback
   - `test` job runs fast unit tests (`pytest -m fast`)
   - Completes in < 5 minutes
   - All subsequent tiers depend on this passing

2. **Tier 2 (User Stories)**: Core functionality tests run after speed tier
   - `container-build-test` - Containerized deployment validation
   - `cet-dev-e2e` - CET pipeline E2E test (key feature)
   - `transition-mvp` - Transition detection pipeline (key feature)
   - These run in parallel after Tier 1 passes

3. **Tier 3 (Performance)**: Performance checks run last (non-blocking)
   - `performance-check` - Performance regression detection
   - Uses `continue-on-error: true` to not block workflow
   - Provides metrics but doesn't prevent merges

#### Workflow-Specific Behavior

- **PR/Commit Workflows** (`on-pr.yml`, `on-commit.yml`, `on-push-main.yml`):
  - Tier 1: Fast tests run immediately
  - Tier 2: User story jobs run conditionally (based on path filters for PRs)
  - Tier 3: Performance checks run last, non-blocking

- **Nightly Builds** (`nightly.yml`):
  - Runs comprehensive test suite in parallel:
    - `test-unit`: All unit tests (fast + slow)
    - `test-integration`: Integration tests with Neo4j service
    - `test-e2e`: End-to-end tests
  - Completes in ~10-15 minutes total
  - All tests run in parallel for faster completion

- **Test Markers**:
  - `@pytest.mark.fast` - Fast unit tests (< 1 second each)
  - `@pytest.mark.slow` - Slow unit tests (ML training, heavy computation)
  - `@pytest.mark.integration` - Integration tests
  - `@pytest.mark.e2e` - End-to-end tests

### Workflow Files

- `container-ci.yml` runs the containerized suites in GitHub Actions
- `neo4j-smoke.yml` validates graph connectivity and schema expectations
- `performance-regression-check.yml` compares benchmark artifacts and alerts on drift
- Artifacts (logs, coverage, metrics) publish to `reports/` and the CI UI for inspection

## Contributing to Tests

- Add new fixtures under `tests/fixtures/` or generate scenario files with helper scripts
- Extend coverage by mirroring real workflows—prefer Dagster asset entry points when possible
- Update documentation in this guide when test commands or targets change

## Test Fixtures (Task 1.4)

- Canonical scenarios live in `tests/fixtures/enrichment_scenarios.json` with a helper loader at `tests/fixtures/enrichment_scenarios.py`.
- Each fixture describes SBIR/USAspending pairs, expected match methods, and confidence thresholds. Use them in unit tests to exercise good/bad/edge cases:

  ```python
  from tests.fixtures.enrichment_scenarios import load_enrichment_scenarios

  scenarios = load_enrichment_scenarios()
  for case in scenarios["good_scenarios"]["scenarios"]:
      result = enrich_single_company(case["sbir_company"], case["usaspending_recipient"])
      assert result["confidence"] >= case["expected_confidence"]
  ```

- Scenario keys: `id`, `name`, `sbir_company`, `usaspending_recipient`, `expected_match_method`, `expected_confidence`, and `description`.

## Performance Reporting (Task 2.5)

- Reporting helpers live in `src/utils/performance_reporting.py` and read/write `reports/benchmarks/*.json`.
- Create a reporter, load benchmarks, and render Markdown/HTML artifacts:

  ```python
  from pathlib import Path
  import json
  from src.utils.performance_reporting import PerformanceReporter, PerformanceMetrics

  reporter = PerformanceReporter()
  with open("reports/benchmarks/baseline.json") as f:
      baseline = PerformanceMetrics.from_benchmark(json.load(f))
  with open("reports/benchmarks/benchmark_latest.json") as f:
      current_data = json.load(f)

  current = PerformanceMetrics.from_benchmark(current_data)
  comparison = reporter.compare_metrics(baseline, current)
  reporter.save_markdown_report(current_data, Path("reports/enrichment_benchmark.md"))
  ```

- The helper also supports historical trend analysis and GitHub-friendly Markdown for PR comments.

## Regression Detection (Task 4.2)

- CLI entry point: `scripts/detect_performance_regression.py`.
- Typical workflow:

  ```bash
  python scripts/detect_performance_regression.py \

    --sample-size 500 \
    --output-json reports/regression.json \
    --output-markdown reports/regression.md \
    --fail-on-regression
  ```

- Threshold flags control warning/failure levels; the script returns non-zero on regression when `--fail-on-regression` is supplied.
- GitHub Actions integration (`.github/workflows/performance-regression-check.yml`) runs the script and posts the Markdown summary as a PR comment.

## Test Scenarios

### Minimal Scenario

- **Duration**: < 2 minutes
- **Data**: Small sample datasets
- **Purpose**: Quick validation during development
- **Memory**: ~2GB
- **Use Case**: Pre-commit checks, rapid iteration

### Standard Scenario (Default)

- **Duration**: 5-8 minutes
- **Data**: Representative datasets
- **Purpose**: Full pipeline validation
- **Memory**: ~4GB
- **Use Case**: Pre-merge validation, CI/CD

### Large Scenario

- **Duration**: 8-10 minutes
- **Data**: Larger datasets for performance testing
- **Purpose**: Performance regression detection
- **Memory**: ~6GB
- **Use Case**: Performance benchmarking

### Edge Cases Scenario

- **Duration**: 3-5 minutes
- **Data**: Edge cases, malformed data, error conditions
- **Purpose**: Robustness and error handling validation
- **Memory**: ~3GB
- **Use Case**: Quality assurance, error handling validation

## MacBook Air Optimizations

The E2E testing system includes specific optimizations for MacBook Air development:

### Resource Limits

- **Memory**: Limited to 8GB total system usage
- **CPU**: Limited to 2 cores maximum
- **Neo4j Heap**: 1GB maximum
- **Neo4j Pagecache**: 256MB maximum

### Performance Optimizations

- Reduced Neo4j checkpoint intervals
- Disabled query logging
- Optimized connection pools
- Efficient health checks with proper timeouts

### Configuration

Set `MACBOOK_AIR_MODE=true` in your `.env` file to enable optimizations.

## Architecture

### Components

#### E2E Test Orchestrator

- Manages test execution lifecycle
- Monitors resource usage
- Validates environment health
- Generates test reports

#### Neo4j E2E Instance

- Isolated Neo4j instance for testing
- Resource-optimized configuration
- Ephemeral data (cleaned between runs)
- Enhanced health checks

#### Test Data Manager

- Provides curated test datasets
- Manages data isolation
- Handles cleanup between runs
- Supports multiple scenarios

### Docker Compose Structure

```yaml
services:
  neo4j-e2e:          # Optimized Neo4j for testing
  e2e-orchestrator:   # Test execution and monitoring
  duckdb-e2e:         # Optional data processing service
```

## Environment Variables

### Required Variables

```bash
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
ENVIRONMENT=e2e-test
```

### E2E-Specific Variables

```bash

## Test scenario selection

E2E_TEST_SCENARIO=standard

## Test timeout (seconds)

E2E_TEST_TIMEOUT=600

## MacBook Air optimizations

MACBOOK_AIR_MODE=true
MEMORY_LIMIT_GB=8
CPU_LIMIT=2.0

## E2E Neo4j ports (avoid conflicts)

NEO4J_E2E_HTTP_PORT=7475
NEO4J_E2E_BOLT_PORT=7688
```

## Health Checks

The E2E system includes comprehensive health checks:

### Environment Health

- ✅ Required environment variables
- ✅ Python dependencies
- ✅ Test data availability
- ✅ Resource constraints
- ✅ Neo4j connectivity

### Service Health

- ✅ Neo4j database connectivity
- ✅ Container resource limits
- ✅ Network connectivity
- ✅ Volume mounts

## Test Artifacts

### Generated Artifacts

- **Test Reports**: `/app/reports/` - JUnit XML, HTML reports
- **Coverage Reports**: `/app/artifacts/htmlcov/` - Code coverage analysis
- **Logs**: `/app/artifacts/logs/` - Detailed execution logs
- **Performance Metrics**: `/app/artifacts/metrics/` - Resource usage data

### Accessing Artifacts

```bash

## View artifacts in running container

docker compose -f docker-compose.yml -f docker/docker-compose.e2e.yml exec e2e-orchestrator ls -la /app/artifacts

## Copy artifacts to host

docker compose -f docker-compose.yml -f docker/docker-compose.e2e.yml cp e2e-orchestrator:/app/artifacts ./e2e-artifacts
```

## Troubleshooting

### Common Issues

#### Neo4j Connection Timeout

```bash

## Check Neo4j health

docker compose -f docker-compose.yml -f docker/docker-compose.e2e.yml exec neo4j-e2e cypher-shell -u neo4j -p your-password "RETURN 1"
```

###Memory Issues on MacBook Air

```bash

## Check current memory usage

docker stats

## Reduce memory limits in .env

MEMORY_LIMIT_GB=6
```

###Test Timeouts

```bash

## Increase timeout for slower systems

E2E_TEST_TIMEOUT=900 make docker-e2e-standard
```

###Port Conflicts

```bash

## Use different ports in .env

NEO4J_E2E_HTTP_PORT=7476
NEO4J_E2E_BOLT_PORT=7689
```

### Debug Mode

For interactive debugging:

```bash
make docker-e2e-debug

## This opens a shell in the orchestrator container

```

### Logs and Monitoring

```bash

## View orchestrator logs

docker compose -f docker-compose.yml -f docker/docker-compose.e2e.yml logs e2e-orchestrator

## View Neo4j logs

docker compose -f docker-compose.yml -f docker/docker-compose.e2e.yml logs neo4j-e2e

## Monitor resource usage

docker stats
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
- name: Run E2E Tests

  run: |
    cp .env.example .env
    echo "NEO4J_PASSWORD=ci-password" >> .env
    make docker-e2e-standard
```

### Local Development Workflow

```bash

## 1. Quick validation during development

make docker-e2e-minimal

## 2. Full validation before commit

make docker-e2e-standard

## 3. Performance check before merge

make docker-e2e-large

## 4. Cleanup

make docker-e2e-clean
```

## Performance Benchmarks

### MacBook Air M1 (8GB RAM)

- **Minimal**: ~90 seconds
- **Standard**: ~6 minutes
- **Large**: ~9 minutes
- **Edge Cases**: ~4 minutes

### MacBook Air Intel (8GB RAM)

- **Minimal**: ~120 seconds
- **Standard**: ~8 minutes
- **Large**: ~12 minutes
- **Edge Cases**: ~5 minutes

## Best Practices

### Development Workflow

1. Use `minimal` scenario for rapid iteration
2. Run `standard` scenario before commits
3. Use `large` scenario for performance validation
4. Run `edge-cases` scenario for robustness testing

### Resource Management

1. Enable MacBook Air mode for resource optimization
2. Monitor memory usage during tests
3. Clean up volumes regularly
4. Use appropriate timeouts for your system

### Debugging

1. Use interactive debug mode for investigation
2. Check health checks first when tests fail
3. Review artifacts for detailed analysis
4. Monitor resource usage for performance issues

## Future Enhancements

- [ ] Parallel test execution
- [ ] Test result visualization
- [ ] Performance regression detection
- [ ] Automated resource optimization
- [ ] Integration with external monitoring
