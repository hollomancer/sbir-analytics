# End-to-End Testing Guide

This guide explains how to run comprehensive end-to-end (E2E) tests for the SBIR ETL pipeline on local development environments, particularly MacBook Air systems.

## Overview

The E2E testing framework provides comprehensive validation of the entire SBIR ETL pipeline from data ingestion through Neo4j loading. It's designed to run efficiently on MacBook Air development environments with resource constraints (8GB memory, limited CPU).

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ with Poetry
- At least 8GB available memory
- `.env` file configured (copy from `.env.example`)

### Running E2E Tests

```bash
# Quick smoke test (< 2 minutes)
python scripts/run_e2e_tests.py --scenario minimal

# Standard comprehensive test (5-8 minutes)
python scripts/run_e2e_tests.py --scenario standard

# Performance test with larger datasets (8-10 minutes)
python scripts/run_e2e_tests.py --scenario large

# Edge case and robustness testing (3-5 minutes)
python scripts/run_e2e_tests.py --scenario edge-cases
```

## Test Scenarios

### Minimal Scenario
- **Duration**: < 2 minutes
- **Memory Usage**: < 2GB
- **Data Size**: 100 SBIR records, 500 USAspending records
- **Purpose**: Quick validation during development
- **Validation**: Basic pipeline execution, minimal graph validation

### Standard Scenario
- **Duration**: 5-8 minutes
- **Memory Usage**: < 6GB
- **Data Size**: 1,000 SBIR records, 5,000 USAspending records, sample USPTO data
- **Purpose**: Pre-commit validation, comprehensive testing
- **Validation**: Full pipeline validation, comprehensive graph checks

### Large Scenario
- **Duration**: 8-10 minutes
- **Memory Usage**: < 8GB
- **Data Size**: 10,000 SBIR records, 50,000 USAspending records
- **Purpose**: Performance regression testing
- **Validation**: Performance metrics, resource usage validation

### Edge Cases Scenario
- **Duration**: 3-5 minutes
- **Memory Usage**: < 4GB
- **Data Size**: Datasets with missing fields, invalid formats, edge cases
- **Purpose**: Robustness testing
- **Validation**: Error handling, data quality validation

## Test Components

### Test Data Manager
- Provides curated test datasets for different scenarios
- Ensures data isolation from production systems
- Automatically cleans up test artifacts
- Generates synthetic data for edge case testing

### Pipeline Validator
- Validates data flow through all ETL stages (Extract, Validate, Enrich, Transform, Load)
- Checks Neo4j graph structure and relationships
- Verifies performance metrics and thresholds
- Generates detailed validation reports

### Resource Monitor
- Tracks memory and CPU usage during test execution
- Ensures MacBook Air compatibility (< 8GB memory limit)
- Provides resource usage alerts and recommendations
- Includes resource metrics in test reports

## Test Environment

### Docker Compose Configuration
The E2E tests use a dedicated Docker Compose configuration optimized for local development:

```yaml
# docker/docker-compose.e2e.yml (created by implementation)
services:
  e2e-orchestrator:
    # Test orchestration container
  neo4j-e2e:
    # Ephemeral Neo4j instance for testing
    # Memory limited to 1GB heap, 256MB pagecache
```

### Environment Variables
```bash
# Required in .env file
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
ENVIRONMENT=e2e-test

# Optional E2E-specific settings
E2E_MEMORY_LIMIT_GB=8.0
E2E_TIMEOUT_MINUTES=10
E2E_CLEANUP_ON_FAILURE=true
```

## Validation Checkpoints

### Stage 1: Data Extraction
- File reading success
- Record count verification
- Schema compliance
- Performance metrics

### Stage 2: Data Validation
- Schema validation pass rates
- Data quality metrics
- Error handling validation

### Stage 3: Data Enrichment
- Match rate thresholds (≥ 70%)
- Enrichment quality metrics
- Performance benchmarks
- Memory usage validation

### Stage 4: Data Transformation
- Business logic validation
- Data consistency checks
- Graph preparation validation

### Stage 5: Neo4j Loading
- Node creation verification
- Relationship establishment
- Graph query validation
- Load success rates

## Test Reports

E2E tests generate comprehensive reports including:

### Test Summary Report
```json
{
  "overall_success": true,
  "total_duration_seconds": 420.5,
  "scenario": "standard",
  "resource_metrics": {
    "peak_memory_mb": 5120,
    "avg_cpu_percent": 45.2
  },
  "stage_results": [...]
}
```

### Validation Report
- Record counts at each stage
- Data quality metrics
- Performance benchmarks
- Error details and recommendations

### Resource Usage Report
- Memory usage over time
- CPU utilization patterns
- MacBook Air compatibility assessment
- Resource optimization recommendations

## Troubleshooting

### Common Issues

#### Memory Limit Exceeded
```bash
# Reduce test scenario size
python scripts/run_e2e_tests.py --scenario minimal

# Check available memory
free -h  # Linux
vm_stat | grep free  # macOS
```

#### Neo4j Connection Failures
```bash
# Check Neo4j container status
docker compose -f docker/docker-compose.e2e.yml ps

# View Neo4j logs
docker compose -f docker/docker-compose.e2e.yml logs neo4j-e2e
```

#### Test Data Issues
```bash
# Clean up test artifacts
python scripts/run_e2e_tests.py --cleanup-only

# Regenerate test data
python scripts/run_e2e_tests.py --regenerate-data
```

### Debug Mode
```bash
# Run with verbose logging and artifact preservation
python scripts/run_e2e_tests.py --scenario standard --debug --preserve-artifacts
```

## Integration with CI/CD

### GitHub Actions Integration
The E2E tests can be integrated into CI/CD workflows:

```yaml
# .github/workflows/e2e-tests.yml
- name: Run E2E Tests
  run: |
    python scripts/run_e2e_tests.py --scenario standard --ci-mode
    
- name: Upload Test Artifacts
  uses: actions/upload-artifact@v3
  if: failure()
  with:
    name: e2e-test-artifacts
    path: reports/e2e/
```

### Local Development Workflow
1. Make code changes
2. Run minimal E2E test for quick validation
3. Run standard E2E test before committing
4. CI runs comprehensive E2E tests on PR

## Performance Optimization

### MacBook Air Specific Optimizations
- Neo4j heap limited to 1GB
- Parallel processing with thread limits
- Efficient data structures and streaming
- Garbage collection monitoring
- Docker resource constraints

### Test Data Optimization
- Compressed test datasets
- Lazy data loading
- Efficient cleanup strategies
- Minimal artifact generation

## Best Practices

### Development Workflow
1. Start with minimal scenario for rapid iteration
2. Use standard scenario for comprehensive validation
3. Run large scenario for performance testing
4. Use edge-cases scenario for robustness validation

### Test Data Management
- Keep test datasets small but representative
- Use synthetic data for edge cases
- Ensure data isolation from production
- Clean up artifacts regularly

### Resource Management
- Monitor memory usage during development
- Use appropriate test scenarios for available resources
- Clean up Docker containers and volumes regularly
- Optimize test data sizes based on system capabilities

## Related Documentation

- [Container Development Guide](../deployment/containerization.md)
- [Testing Strategy](../architecture/testing-strategy.md)
- [Performance Benchmarks](../performance/enrichment-benchmarks.md)
- [Neo4j Schema Documentation](../schemas/patent-neo4j-schema.md)