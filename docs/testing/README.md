# Testing Documentation

This directory contains comprehensive testing documentation for the SBIR ETL pipeline.

## Testing Guides

### [End-to-End Testing Guide](e2e-testing-guide.md)
Comprehensive guide for running E2E tests on local development environments, particularly MacBook Air systems. Covers test scenarios, validation checkpoints, troubleshooting, and integration with CI/CD.

**Key Topics:**
- Test scenarios (minimal, standard, large, edge-cases)
- MacBook Air resource optimization
- Docker Compose E2E environment
- Validation and reporting
- Performance optimization

## Architecture Documentation

### [E2E Testing Architecture](../architecture/e2e-testing-architecture.md)
Technical architecture documentation for the E2E testing system, including component design, data flow, and integration points.

## Related Documentation

### Testing Strategy
- **Unit Tests**: Component-level testing in `tests/unit/`
- **Integration Tests**: Multi-component testing in `tests/integration/`
- **E2E Tests**: Full pipeline testing in `tests/e2e/`
- **Performance Tests**: Benchmarking and regression detection

### CI/CD Integration
- **Container CI**: Docker-based testing workflow
- **Performance Regression**: Automated benchmark comparison
- **Neo4j Integration**: Database connectivity and schema validation

### Development Workflow
- **Pre-commit Testing**: Quick validation before commits
- **Local Development**: Iterative testing during development
- **Deployment Validation**: Comprehensive testing before deployment

## Quick Reference

### Running Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests  
pytest tests/integration/ -v

# E2E tests (various scenarios)
python scripts/run_e2e_tests.py --scenario minimal     # < 2 min
python scripts/run_e2e_tests.py --scenario standard    # 5-8 min
python scripts/run_e2e_tests.py --scenario large       # 8-10 min
python scripts/run_e2e_tests.py --scenario edge-cases  # 3-5 min

# Container tests
make docker-test
```

### Test Coverage
- **Target**: ≥80% code coverage
- **Current**: 29+ tests across all categories
- **CI Enforcement**: Coverage reports generated automatically

### Performance Targets
- **E2E Standard Scenario**: < 10 minutes execution
- **Memory Usage**: < 8GB for MacBook Air compatibility
- **Match Rate**: ≥70% for enrichment quality gates
- **Load Success**: ≥99% for Neo4j operations

## Contributing to Tests

### Adding New Tests
1. Follow existing test patterns and naming conventions
2. Ensure proper test isolation and cleanup
3. Add appropriate test markers for categorization
4. Update documentation for new test scenarios

### Test Data Management
- Use existing fixtures in `tests/fixtures/`
- Create synthetic data for edge cases
- Ensure data isolation from production systems
- Document test data requirements and sources

### Performance Considerations
- Design tests for MacBook Air resource constraints
- Use appropriate test data sizes for scenarios
- Monitor resource usage during test development
- Optimize for fast feedback cycles