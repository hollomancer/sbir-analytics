# test-execution Specification Delta

## ADDED Requirements

### Requirement: Parallel Test Execution with pytest-xdist
The system SHALL support running the Python test suite in parallel using pytest-xdist workers to reduce CI feedback latency while maintaining test isolation and coverage accuracy.

#### Scenario: Local parallel test execution
- **WHEN** a developer runs `pytest tests/ -n auto --dist=loadscope` locally
- **THEN** pytest-xdist distributes tests across available CPU cores
- **AND** each worker executes tests with function-scoped isolation (no shared state)
- **AND** all tests pass with identical results as serial execution
- **AND** coverage data is merged across workers via `coverage combine`

#### Scenario: CI parallel test execution with timing capture
- **WHEN** GitHub Actions runs the container-ci workflow with `PYTEST_WORKERS=auto`
- **THEN** the test stage passes `-n auto --dist=loadscope` to pytest
- **AND** total execution time is 2–4x faster than serial baseline (from 8–12 min to 2–4 min)
- **AND** workflow logs capture before/after timing in a structured format
- **AND** artifacts include `reports/ci_timings.md` with per-phase timing breakdown

#### Scenario: Rollback on flakiness detection
- **WHEN** parallel test runs show >5% new flakiness or intermittent failures
- **THEN** operators can set `PYTEST_WORKERS=1` to revert to serial execution
- **AND** workflow documentation includes rollback procedure and triage steps
- **AND** failed tests can be re-run serially to confirm non-flaky behavior

### Requirement: Test Fixture Isolation
The system SHALL ensure all test fixtures provide per-test isolation, preventing state leakage and cross-test contamination when tests run in parallel.

#### Scenario: Temporary directory isolation
- **WHEN** tests use pytest's `tmp_path` fixture or `tempfile.mkdtemp()`
- **THEN** each test receives a unique, non-overlapping temporary directory
- **AND** cleanup occurs automatically after test completion
- **AND** no hardcoded paths to shared directories (e.g., `/tmp/sbir-etl`) are used in tests

#### Scenario: Neo4j session and database isolation
- **WHEN** multiple test workers connect to the Neo4j test container concurrently
- **THEN** each worker uses independent Neo4j sessions or unique database namespaces
- **AND** Neo4j health checks confirm concurrent connections are supported
- **AND** connection pool configuration handles multiple concurrent opens without errors
- **AND** tests complete without connection timeouts or deadlocks

#### Scenario: Dagster context isolation
- **WHEN** tests create or reuse Dagster contexts, resources, or assets
- **THEN** each test receives a fresh, isolated Dagster context
- **AND** no module-level or class-level singletons persist across tests
- **AND** fixtures use function-scoped or request-scoped lifecycle (not session/module)

#### Scenario: Shared mutable state cleanup
- **WHEN** tests modify global state, module variables, or cached imports
- **THEN** each test cleans up modified state via pytest fixtures with `autouse=True`
- **AND** teardown runs reliably even if the test fails
- **AND** subsequent tests are unaffected by prior test side effects

### Requirement: Coverage Reporting with Parallel Execution
The system SHALL accurately merge coverage data from parallel pytest workers and generate consolidated coverage reports.

#### Scenario: Coverage data merging
- **WHEN** pytest runs with `PYTEST_WORKERS > 1` and `--cov=src`
- **THEN** coverage.py creates `.coverage.*` files (one per worker)
- **AND** after test completion, `coverage combine` merges files into a single `.coverage`
- **AND** `coverage report` and `coverage html` generate accurate consolidated output
- **AND** coverage thresholds are evaluated against the merged dataset

#### Scenario: CI artifact generation
- **WHEN** the container-ci workflow completes test execution
- **THEN** coverage HTML reports are available in the workflow artifacts
- **AND** coverage reports include all files and branches exercised by parallel workers
- **AND** coverage data persists across multiple CI runs for trend analysis

### Requirement: Parallel Test Execution Configuration
The system SHALL provide environment variable and configuration file support for controlling parallelism behavior both locally and in CI.

#### Scenario: Environment variable control
- **WHEN** a user sets `PYTEST_WORKERS=auto` before running pytest
- **THEN** pytest-xdist distributes tests across all available CPU cores
- **AND** the setting is respected in both local development and CI environments

#### Scenario: Custom worker count
- **WHEN** a user sets `PYTEST_WORKERS=2` (or any specific number)
- **THEN** pytest-xdist creates exactly that many workers
- **AND** tests are distributed across the specified number of workers

#### Scenario: Serial fallback
- **WHEN** `PYTEST_WORKERS=1` is set or the environment variable is unset locally
- **THEN** tests execute serially with no xdist workers
- **AND** behavior is identical to running pytest without xdist

### Requirement: Monitoring and Stability Assurance
The system SHALL track test parallelism stability, detect regressions, and provide operators with clear visibility into flakiness and performance improvements.

#### Scenario: Flakiness detection and alerting
- **WHEN** a test fails intermittently (passes serially, fails in parallel)
- **THEN** operators can run the test serially to confirm isolation issue
- **AND** workflow documentation lists known flaky tests with reproduction steps
- **AND** alerts are logged or documented for triage (no silent failures)

#### Scenario: Timing trend tracking
- **WHEN** parallel tests complete in CI
- **THEN** `reports/ci_timings.md` records execution time, worker count, and test count
- **AND** trend data is available for review across multiple CI runs
- **AND** operators can detect performance regressions or hardware changes

#### Scenario: Opt-in local parallelism with serial default
- **WHEN** a developer runs `make pytest` or `pytest` locally without parallelism flag
- **THEN** tests execute serially by default (backward compatible)
- **AND** developer can opt-in with `PYTEST_WORKERS=auto make pytest` or `make pytest-parallel`
- **AND** documentation clearly shows both serial and parallel invocations

### Requirement: Developer Documentation and Troubleshooting
The system SHALL provide clear, discoverable documentation for running tests in parallel, troubleshooting isolation issues, and understanding CI behavior.

#### Scenario: Local testing guidance
- **WHEN** a developer reads `docs/testing.md`
- **THEN** they find:
  - How to run tests serially (default): `pytest` or `make pytest`
  - How to run tests in parallel: `make pytest-parallel` or `pytest -n auto --dist=loadscope`
  - How to override worker count: `PYTEST_WORKERS=2 pytest -n 2`
  - Common troubleshooting steps (e.g., "test fails in parallel but not serially" → fixture isolation issue)

#### Scenario: CI behavior documentation
- **WHEN** a developer checks `README.md` Testing section
- **THEN** they see a note that CI runs tests in parallel by default
- **AND** they know where to find performance metrics and how to report flakiness
- **AND** they understand that parallel execution is the expected behavior

#### Scenario: Failure diagnosis and reproduction
- **WHEN** a developer encounters a test that fails only under parallelism
- **THEN** they can run `PYTEST_WORKERS=1 pytest -k <test_name>` to reproduce serially
- **AND** they find documented isolation patterns and examples in `docs/testing.md`
- **AND** they can file an issue with clear reproduction steps for maintainers to triage