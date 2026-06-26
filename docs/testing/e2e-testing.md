# E2E Testing

End-to-end (E2E) testing validates the entire SBIR ETL pipeline from data
ingestion through Neo4j loading, with resource monitoring tuned for constrained
development environments (e.g. an 8GB MacBook Air).

## Quick Start

### Prerequisites

1. Copy `.env.example` to `.env` and set your Neo4j credentials.
2. Ensure Docker and Docker Compose are installed and running.

### Running scenarios

```bash
make docker-e2e-minimal      # < 2 min  – quick smoke validation
make docker-e2e-standard     # 5-8 min  – full pipeline validation (default)
make docker-e2e-large        # 8-10 min – performance / larger datasets
make docker-e2e-edge-cases   # 3-5 min  – robustness, malformed data
make docker-e2e-debug        # Interactive shell in the orchestrator container
make docker-e2e-clean        # Tear down and remove volumes
```

Direct script fallback (bypasses Make/Docker wrappers):

```bash
python scripts/run_e2e_tests.py --scenario {minimal|standard|large|edge-cases}
```

## Test Scenarios

| Scenario | Duration | Memory | Data | Purpose |
|----------|----------|--------|------|---------|
| Minimal | < 2 min | ~2GB | 100 SBIR / 500 USAspending | Pre-commit checks, rapid iteration |
| Standard (default) | 5-8 min | ~4GB | 1,000 SBIR / 5,000 USAspending | Pre-merge / CI full validation |
| Large | 8-10 min | ~6GB | 10,000 SBIR / 50,000 USAspending | Performance regression detection |
| Edge cases | 3-5 min | ~3GB | Missing fields, invalid formats | Robustness and error handling |

## Architecture

The E2E CLI runs on the host and orchestrates a Docker Compose environment
containing an isolated Neo4j instance and the SBIR ETL app, writing reports and
artifacts back to the host.

```text
┌─────────────────────────────────────────────────────────────┐
│                  Development Environment                    │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │ E2E Test CLI    │    │ Test Reports & Artifacts        │ │
│  │ (run_e2e_tests) │    │ - Validation reports            │ │
│  └─────────────────┘    │ - Resource usage metrics        │ │
│           │              │ - Debug artifacts               │ │
│           ▼              └─────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │           Docker Compose E2E Environment               │ │
│  │  ┌─────────────────┐  ┌─────────────────────────────┐  │ │
│  │  │ Test Orchestrator│  │      Service Containers     │  │ │
│  │  │ - Test Runner   │  │ - Neo4j Test Instance       │  │ │
│  │  │ - Data Manager  │  │ - SBIR ETL App              │  │ │
│  │  │ - Validator     │  │                             │  │ │
│  │  │ - Monitor       │  │                             │  │ │
│  │  └─────────────────┘  └─────────────────────────────┘  │ │
│  │           │                        │                   │ │
│  │           ▼                        ▼                   │ │
│  │  ┌─────────────────────────────────────────────────────┐ │ │
│  │  │   Test Data Volumes (sample datasets, artifacts)    │ │ │
│  │  └─────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Components

**E2E Test CLI** (`scripts/run_e2e_tests.py`) — single entry point. Parses the
scenario argument, brings the Docker Compose environment up/down, aggregates
results, generates the report, and cleans up on interruption.

```python
class E2ETestCLI:
    def run_scenario(self, scenario: TestScenario) -> E2ETestResult
    def setup_environment(self) -> bool
    def cleanup_environment(self) -> None
    def generate_report(self, results: E2ETestResult) -> Path
```

**Test Data Manager** (`tests/e2e/data_manager.py`) — provides curated datasets
per scenario, generates synthetic edge-case data, isolates test data from
production, and cleans up between runs.

**Pipeline Validator** (`tests/e2e/pipeline_validator.py`) — validates each
stage output:

1. **Extraction** — record counts, schema compliance, file integrity
2. **Validation** — pass rates, data quality metrics, error handling
3. **Enrichment** — match rates (≥70%), quality metrics, performance
4. **Transformation** — business logic, data consistency, graph preparation
5. **Loading** — Neo4j node/relationship creation and query validation

**Resource Monitor** (`tests/e2e/resource_monitor.py`) — tracks memory (<8GB),
CPU, and container resource usage, surfacing optimization recommendations.

### Quality gates

```yaml
extraction:
  min_records: 1
  schema_compliance: 100%

enrichment:
  match_rate_threshold: 0.70
  performance_threshold_seconds: 300

loading:
  load_success_rate: 0.99
  relationship_integrity: 100%
```

## Docker Compose Configuration

The E2E environment is defined in the **root `docker-compose.yml` under the `ci`
profile** — there is no separate `docker-compose.e2e.yml`. It runs two services:

- **`neo4j`** — an ephemeral Neo4j instance (apoc plugin, healthcheck-gated).
- **`app`** — the test container. Its `ci`-profile command runs
  `scripts/e2e_health_check.py` and then
  `scripts/run_e2e_tests.py --scenario $E2E_TEST_SCENARIO`.

Bring it up with the Make targets (each wraps `docker compose --profile ci up
--build --abort-on-container-exit neo4j app`):

```bash
make docker-e2e            # full suite (profile: ci)
make docker-e2e-minimal    # minimal / fast scenario
make docker-e2e-standard   # standard scenario
make docker-e2e-clean      # tear down
```

## Resource Optimizations

For constrained machines, set `MACBOOK_AIR_MODE=true` in `.env`. This applies:

- Memory limited to 8GB total; CPU limited to 2 cores
- Neo4j heap ≤1GB, pagecache ≤256MB
- Reduced Neo4j checkpoint intervals, disabled query logging, optimized
  connection pools and health-check timeouts

## Environment Variables

```bash
# Required
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
ENVIRONMENT=e2e-test

# E2E-specific
E2E_TEST_SCENARIO=standard
E2E_TEST_TIMEOUT=600
MACBOOK_AIR_MODE=true
MEMORY_LIMIT_GB=8
CPU_LIMIT=2.0

# E2E Neo4j ports (avoid conflicts with a local Neo4j)
NEO4J_E2E_HTTP_PORT=7475
NEO4J_E2E_BOLT_PORT=7688
```

## Test Artifacts

Generated under the orchestrator container:

- **Test reports**: `/app/reports/` — JUnit XML, HTML reports
- **Coverage**: `/app/artifacts/htmlcov/`
- **Logs**: `/app/artifacts/logs/`
- **Performance metrics**: `/app/artifacts/metrics/`

Copy artifacts to the host:

```bash
docker compose --profile ci cp app:/app/artifacts ./e2e-artifacts
```

## Test Fixtures

Canonical enrichment scenarios live in `tests/fixtures/enrichment_scenarios.json`
with a loader at `tests/fixtures/enrichment_scenarios.py`. Each fixture describes
SBIR/USAspending pairs, expected match methods, and confidence thresholds:

```python
from tests.fixtures.enrichment_scenarios import load_enrichment_scenarios

scenarios = load_enrichment_scenarios()
for case in scenarios["good_scenarios"]["scenarios"]:
    result = enrich_single_company(case["sbir_company"], case["usaspending_recipient"])
    assert result["confidence"] >= case["expected_confidence"]
```

Scenario keys: `id`, `name`, `sbir_company`, `usaspending_recipient`,
`expected_match_method`, `expected_confidence`, `description`.

## Performance Regression Detection

The regression CLI lives at `scripts/performance/detect_performance_regression.py`:

```bash
python scripts/performance/detect_performance_regression.py \
  --sample-size 500 \
  --output-json reports/regression.json \
  --output-markdown reports/regression.md \
  --fail-on-regression
```

Threshold flags control warning/failure levels; the script returns non-zero on
regression when `--fail-on-regression` is supplied. In CI it runs as the
`performance-check` job in `.github/workflows/ci.yml`, which publishes regression
artifacts and posts a summary as a PR comment.

## CI Integration

E2E and related checks run from `.github/workflows/ci.yml`:

- `e2e-docker` — runs the containerized E2E Docker checks
- `container-build-test` — validates the containerized deployment build
- `transition-mvp` — exercises the transition detection pipeline
- `performance-check` — runs regression detection (non-blocking via
  `continue-on-error`)

The scheduled `neo4j-smoke` job (in `.github/workflows/weekly.yml`) checks graph
connectivity and schema expectations. Artifacts (logs, coverage, metrics)
publish to `reports/` and the CI UI.

A minimal workflow step looks like:

```yaml
- name: Run E2E Tests
  run: |
    cp .env.example .env
    echo "NEO4J_PASSWORD=ci-password" >> .env
    make docker-e2e-standard
```

## Troubleshooting

**Neo4j connection timeout** — check the instance is healthy:

```bash
docker compose --profile ci exec neo4j cypher-shell -u neo4j -p your-password "RETURN 1"
```

**Memory pressure** — inspect usage with `docker stats` and lower
`MEMORY_LIMIT_GB` in `.env`.

**Test timeouts** — raise the timeout: `E2E_TEST_TIMEOUT=900 make docker-e2e-standard`.

**Port conflicts** — set different `NEO4J_E2E_HTTP_PORT` / `NEO4J_E2E_BOLT_PORT`
in `.env`.

**Inspect logs**:

```bash
docker compose --profile ci logs app
docker compose --profile ci logs neo4j
```

## Related Documentation

- [Testing Index](index.md) — commands, markers, and overall strategy
- [Neo4j Testing Environments](neo4j-testing-environments-guide.md) — graph testing setup
- [CI Sharding Setup](ci-sharding-setup.md) — parallel test execution
