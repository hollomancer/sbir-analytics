# E2E Testing Architecture

## Overview

The End-to-End (E2E) testing architecture provides comprehensive validation of the SBIR ETL pipeline from data ingestion through Neo4j loading. The system is designed to run efficiently on MacBook Air development environments while providing thorough validation of all pipeline stages.

## Architecture Components

### High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                MacBook Air Development Environment          │
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
│  │  │              Test Data Volumes                      │ │ │
│  │  │ - Sample Datasets  - Test Artifacts                │ │ │
│  │  └─────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. E2E Test CLI (`scripts/run_e2e_tests.py`)

**Purpose**: Single entry point for running E2E tests with different scenarios

### Responsibilities

- Parse command-line arguments for test scenarios
- Orchestrate Docker Compose environment startup/teardown
- Aggregate and display test results
- Handle cleanup on interruption
- Generate comprehensive test reports

### Interface

```python
class E2ETestCLI:
    def run_scenario(self, scenario: TestScenario) -> E2ETestResult
    def setup_environment(self) -> bool
    def cleanup_environment(self) -> None
    def generate_report(self, results: E2ETestResult) -> Path
```

### 2. Test Data Manager (`tests/e2e/data_manager.py`)

**Purpose**: Manage test datasets and data lifecycle

### Responsibilities

- Provide curated test datasets for different scenarios
- Generate synthetic data for edge case testing
- Ensure data isolation from production systems
- Clean up test artifacts between runs
- Validate data integrity and schema compliance

### Test Scenarios

- **MINIMAL**: 100 SBIR records, 500 USAspending records
- **STANDARD**: 1,000 SBIR records, 5,000 USAspending records
- **LARGE**: 10,000 SBIR records, 50,000 USAspending records
- **EDGE_CASES**: Datasets with missing fields, invalid formats

### 3. Pipeline Validator (`tests/e2e/pipeline_validator.py`)

**Purpose**: Comprehensive validation of pipeline outputs at each stage

### Validation Stages

1. **Extraction Validation**: Record counts, schema compliance, file integrity
2. **Validation Stage**: Pass rates, data quality metrics, error handling
3. **Enrichment Validation**: Match rates (≥70%), quality metrics, performance
4. **Transformation Validation**: Business logic, data consistency, graph preparation
5. **Loading Validation**: Neo4j node/relationship creation, query validation

### Quality Gates

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

### 4. Resource Monitor (`tests/e2e/resource_monitor.py`)

**Purpose**: Track resource usage and ensure MacBook Air compatibility

### Monitoring Capabilities

- Memory usage tracking (< 8GB limit)
- CPU utilization monitoring
- Docker container resource usage
- Performance metrics collection
- Resource optimization recommendations

### MacBook Air Optimizations

- Neo4j heap limited to 1GB
- Pagecache limited to 256MB
- Parallel processing with thread limits
- Efficient garbage collection settings

## Docker Compose Configuration

### E2E Test Environment (`docker/docker-compose.e2e.yml`)

```yaml
services:
  e2e-orchestrator:
    build:
      context: .
      dockerfile: docker/Dockerfile.e2e
    environment:

      - ENVIRONMENT=e2e-test
      - NEO4J_URI=bolt://neo4j-e2e:7687
      - E2E_MEMORY_LIMIT_GB=8.0

    depends_on:
      neo4j-e2e:
        condition: service_healthy
    volumes:

      - ./tests/fixtures:/app/test-data:ro
      - e2e-artifacts:/app/artifacts

  neo4j-e2e:
    image: neo4j:5.20.0
    environment:

      - NEO4J_AUTH=neo4j/e2e-password
      - NEO4J_PLUGINS=["apoc"]
      - NEO4J_dbms_memory_heap_initial__size=512m
      - NEO4J_dbms_memory_heap_max__size=1g
      - NEO4J_dbms_memory_pagecache_size=256m

    volumes:

      - e2e-neo4j-data:/data

    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p e2e-password 'RETURN 1'"]
      interval: 10s
      timeout: 5s
      retries: 12
```

## Test Execution Flow

### 1. Environment Setup

1. Parse CLI arguments and validate scenario
2. Check system resources (memory, disk space)
3. Start Docker Compose E2E environment
4. Wait for service health checks to pass
5. Initialize test data for selected scenario

### 2. Pipeline Execution

1. Execute extraction stage with test data
2. Validate extraction outputs and metrics
3. Execute validation stage with quality checks
4. Execute enrichment stage with performance monitoring
5. Execute transformation stage with business logic validation
6. Execute loading stage with Neo4j validation

### 3. Validation and Reporting

1. Validate each stage output against expected criteria
2. Check resource usage against MacBook Air limits
3. Verify Neo4j graph structure and relationships
4. Generate comprehensive test report
5. Clean up test artifacts (optional)

## Error Handling Strategy

### Error Categories

1. **Environment Setup Errors**
   - Docker service startup failures
   - Network connectivity issues
   - Resource constraint violations

2. **Pipeline Execution Errors**
   - Data processing failures
   - Database connection issues
   - Memory/resource exhaustion

3. **Validation Errors**
   - Schema validation failures
   - Quality threshold violations
   - Graph structure inconsistencies

### Recovery Mechanisms

- **Retry Logic**: Automatic retry for transient failures
- **Graceful Degradation**: Continue with partial testing when possible
- **Resource Management**: Automatic cleanup and resource release
- **Detailed Logging**: Comprehensive error context for debugging

## Performance Considerations

### MacBook Air Constraints

- **Memory**: 8GB total system memory limit
- **CPU**: Efficient use of available cores
- **Storage**: Minimize disk I/O and temporary files
- **Network**: Optimize container communication

### Optimization Strategies

- **Streaming Processing**: Process data in chunks to minimize memory usage
- **Lazy Loading**: Load data on-demand rather than preloading
- **Efficient Cleanup**: Remove temporary artifacts promptly
- **Resource Monitoring**: Continuous tracking with alerts

## Integration Points

### CI/CD Integration

- GitHub Actions workflow for automated E2E testing
- Artifact collection for failed tests
- Performance regression detection
- Resource usage reporting

### Development Workflow

- Pre-commit hooks for minimal scenario testing
- IDE integration for quick validation
- Debug mode for detailed troubleshooting
- Continuous monitoring during development

## Quality Assurance

### Test Coverage

- All five ETL pipeline stages validated
- Multiple data scenarios (minimal, standard, large, edge-cases)
- Resource constraint validation
- Error handling and recovery testing

### Validation Criteria

- **Functional**: All pipeline stages execute successfully
- **Performance**: Execution time < 10 minutes for standard scenario
- **Resource**: Memory usage < 8GB, efficient CPU utilization
- **Quality**: Data quality gates pass, Neo4j graph integrity maintained

## Future Enhancements

### Planned Improvements

- Visual test reporting dashboard
- Performance trend analysis
- Automated test data generation
- Cloud environment testing support
- Integration with existing CI/CD performance regression checks

### Scalability Considerations

- Support for different hardware configurations
- Configurable resource limits and timeouts
- Modular test scenario composition
- Distributed testing capabilities
