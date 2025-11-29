# Test Coverage Strategy and Improvement Plan

This document outlines the current state of test coverage, identifies critical gaps, and provides a phased plan to achieve comprehensive test coverage across the SBIR ETL codebase.

## Table of Contents

1.  [Executive Summary](#1-executive-summary)
2.  [Coverage Matrix by Module](#2-coverage-matrix-by-module)
3.  [Priority 1: Critical Gaps (ZERO Coverage)](#3-priority-1-critical-gaps-zero-coverage)
    *   [3.1 Assets Module](#31-assets-module)
    *   [3.2 Models Module](#32-models-module)
    *   [3.3 Config Module](#33-config-module)
    *   [3.4 Migration Module](#34-migration-module)
    *   [3.5 Validators Module](#35-validators-module)
4.  [Priority 2: Partial Coverage (Expand Existing Tests)](#4-priority-2-partial-coverage-expand-existing-tests)
    *   [4.1 Loaders Module](#41-loaders-module)
    *   [4.2 Transformers Module](#42-transformers-module)
    *   [4.3 Transition Module](#43-transition-module)
5.  [Recommended Phased Approach](#5-recommended-phased-approach)
    *   [Phase 3: Address Critical Gaps (4-6 weeks)](#phase-3-address-critical-gaps-4-6-weeks)
    *   [Phase 4: Expand Partial Coverage (3-4 weeks)](#phase-4-expand-partial-coverage-3-4-weeks)
    *   [Phase 5: Property-Based & Performance Testing (2-3 weeks)](#phase-5-property-based--performance-testing-2-3-weeks)
6.  [Testing Best Practices](#6-testing-best-practices)
    *   [6.1 Mocking Strategy](#61-mocking-strategy)
    *   [6.2 Test Data Management](#62-test-data-management)
    *   [6.3 Coverage Goals](#63-coverage-goals)
    *   [6.4 Test Organization](#64-test-organization)
7.  [Success Metrics](#7-success-metrics)
    *   [Coverage Targets](#coverage-targets)
    *   [Quality Targets](#quality-targets)
    *   [Process Targets](#process-targets)
8.  [Risk Mitigation](#8-risk-mitigation)
9.  [Resource Requirements](#9-resource-requirements)
10. [Next Actions](#10-next-actions)
11. [Appendix A: Test Naming Conventions](#11-appendix-a-test-naming-conventions)
12. [Appendix B: Coverage Calculation](#12-appendix-b-coverage-calculation)
13. [Appendix C: Example Test Patterns](#13-appendix-c-example-test-patterns)

---

## 1. Executive Summary

**Current Status (Generated: 2025-11-10)**:
- **Total Source Files**: 177 files (60,922 lines)
- **Total Test Files**: 88 files (26,050 test lines)
- **Test-to-Source Ratio**: 42%
- **Estimated Coverage**: ~84%
- **Tests Created**: 686 total (Phase 1: 199, Phase 2: 487)

**Key Achievement**: Phases 1 and 2 of the test coverage improvement plan are complete, achieving ~80% coverage for critical modules (extractors, loaders, quality, utils, enrichers, cli, ml).

**Critical Finding**: **21,113 lines of code (35%) across 73 files have ZERO test coverage**, primarily in the `assets`, `models`, `config`, `migration`, and `validators` modules.

**Goals**:
- Achieve 80%+ test coverage across all critical modules
- Establish testing standards and documentation
- Enhance CI/CD pipeline with coverage enforcement
- Build sustainable testing infrastructure

## 2. Coverage Matrix by Module

| Module | Source Files | Test Files | Source Lines | Test Lines | Status |
|--------|--------------|------------|--------------|------------|---------|
| **assets** | 43 | 0 | 13,315 | 0 | ✗ **ZERO COVERAGE** |
| **models** | 14 | 0 | 3,330 | 0 | ✗ **ZERO COVERAGE** |
| **migration** | 6 | 0 | 1,772 | 0 | ✗ **ZERO COVERAGE** |
| **config** | 2 | 0 | 1,114 | 0 | ✗ **ZERO COVERAGE** |
| **validators** | 2 | 0 | 651 | 0 | ✗ **ZERO COVERAGE** |
| **transition** | 12 | 6 | 5,477 | 1,307 | ⚠ PARTIAL (24%) |
| **transformers** | 11 | 6 | 4,892 | 1,071 | ⚠ PARTIAL (22%) |
| **loaders** | 6 | 1 | 3,057 | 637 | ⚠ PARTIAL (21%) |
| **utils** | 24 | 8 | 9,375 | 3,674 | ✓ Good (39%) |
| **enrichers** | 22 | 6 | 5,659 | 2,508 | ✓ Good (44%) |
| **ml** | 10 | 14 | 3,661 | 3,635 | ✓ Good (99%) |
| **quality** | 4 | 4 | 2,426 | 1,575 | ✓ Good (65%) |
| **extractors** | 5 | 3 | 2,862 | 980 | ✓ Good (34%) |
| **cli** | 14 | 4 | 2,397 | 734 | ✓ Good (31%) |

## 3. Priority 1: Critical Gaps (ZERO Coverage)

### 3.1 Assets Module (43 files, 13,315 lines)
**Risk Level**: 🔴 **CRITICAL** - Largest uncovered module
**Business Impact**: HIGH - Contains Dagster assets for data pipeline orchestration

#### Recommended Approach:
1. **Phase 3.1**: Focus on non-Dagster utility modules first (validation, transformation, utils)
2. **Phase 3.2**: Add integration tests for Dagster asset execution
3. **Phase 3.3**: Add unit tests with mocked dependencies for complex assets

**Estimated Effort**: 3-4 weeks for full coverage

### 3.2 Models Module (14 files, 3,330 lines)
**Risk Level**: 🟡 **HIGH** - Data models define system behavior
**Business Impact**: HIGH - Incorrect models cause downstream errors

#### Recommended Approach:
1. Create property-based tests using Hypothesis for data model validation
2. Test serialization/deserialization (Pydantic validation)
3. Test model constraints and edge cases

**Estimated Effort**: 1-2 weeks

### 3.3 Config Module (2 files, 1,114 lines)
**Risk Level**: 🟡 **HIGH** - Configuration errors cascade
**Business Impact**: MEDIUM - Affects all system operations

#### Recommended Approach:
1. Test configuration loading from various sources (files, env vars)
2. Test schema validation and error handling
3. Test default value handling

**Estimated Effort**: 3-5 days

### 3.4 Migration Module (6 files, 1,772 lines)
**Risk Level**: 🟢 **MEDIUM** - Used for schema migrations
**Business Impact**: LOW - Not frequently executed, but critical when needed

#### Recommended Approach:
1. Create integration tests with sample Neo4j databases
2. Test migration generation, validation, and execution
3. Test rollback scenarios

**Estimated Effort**: 1 week

### 3.5 Validators Module (2 files, 651 lines)
**Risk Level**: 🟡 **HIGH** - Data quality depends on validation
**Business Impact**: HIGH - Invalid data causes pipeline failures

#### Recommended Approach:
1. Test validation rules with valid/invalid data
2. Test error message generation
3. Test edge cases and boundary conditions

**Estimated Effort**: 3-5 days

## 4. Priority 2: Partial Coverage (Expand Existing Tests)

### 4.1 Loaders Module (6 untested files, 3,057 lines)
**Current Coverage**: 21% (only client.py has comprehensive tests)
**Risk Level**: 🟡 **HIGH**

#### Recommended Approach:
1. Follow the pattern from `test_neo4j_client.py`
2. Use mocked Neo4j connections
3. Test Cypher query generation and execution

**Estimated Effort**: 1 week

### 4.2 Transformers Module (10 untested files, 4,000 lines)
**Current Coverage**: 22%
**Risk Level**: 🟡 **HIGH**

#### Recommended Approach:
1. Expand fiscal tests (sensitivity, shocks, taxes)
2. Add patent_transformer unit tests
3. Test R integration functions with mocked R calls

**Estimated Effort**: 1.5 weeks

### 4.3 Transition Module (12 untested files, 5,477 lines)
**Current Coverage**: 24%
**Risk Level**: 🟡 **HIGH**

#### Recommended Approach:
1. Test detection algorithms with synthetic data
2. Test scoring logic with known transitions
3. Test evaluation metrics

**Estimated Effort**: 1.5 weeks

## 5. Recommended Phased Approach

### Phase 3: Address Critical Gaps (4-6 weeks)
**Goal**: Add tests for high-risk uncovered modules

**Phase 3.1**: Models & Validators (1.5 weeks)
- ✅ Complete models module tests (14 files)
- ✅ Complete validators module tests (2 files)
- **Impact**: Catch data model and validation errors early

**Phase 3.2**: Config & Core Assets (2 weeks)
- ✅ Complete config module tests (2 files)
- ✅ Test core asset utilities (validation, transformation, utils)
- **Impact**: Prevent configuration and pipeline errors

**Phase 3.3**: Dagster Asset Integration (1.5 weeks)
- ✅ Add integration tests for key Dagster assets
- ✅ Focus on fiscal, CET, and USPTO pipelines
- **Impact**: Ensure pipeline orchestration works correctly

**Phase 3.4**: Migration Module (1 week)
- ✅ Complete migration module tests (6 files)
- **Impact**: Safe schema migrations

### Phase 4: Expand Partial Coverage (3-4 weeks)
**Goal**: Fill gaps in partially tested modules

**Phase 4.1**: Loaders (1 week)
- ✅ Complete Neo4j loader tests (5 untested files)
- **Pattern**: Follow test_neo4j_client.py approach

**Phase 4.2**: Transformers (1.5 weeks)
- ✅ Complete fiscal transformer tests
- ✅ Complete patent transformer tests
- ✅ Complete R integration tests

**Phase 4.3**: Transition Detection (1.5 weeks)
- ✅ Complete detection algorithm tests
- ✅ Complete scoring and evaluation tests

### Phase 5: Property-Based & Performance Testing (2-3 weeks)
**Goal**: Add advanced testing techniques

**Phase 5.1**: Property-Based Tests
- Install Hypothesis: `uv add --dev hypothesis`
- Create property tests for:
  - Data model invariants (models/)
  - Text normalization (utils/)
  - Enrichment strategies (enrichers/)

**Phase 5.2**: Performance Tests
- Install pytest-benchmark: `uv add --dev pytest-benchmark`
- Benchmark critical paths:
  - Database queries (loaders/)
  - Search provider performance (enrichers/)
  - Large dataset transformations (transformers/)

**Phase 5.3**: Integration Tests
- Test end-to-end workflows
- Test multi-component interactions
- Test external API integrations (with VCR.py)

## 6. Testing Best Practices

### 6.1 Mocking Strategy
- **External Services**: Always mock (Neo4j, APIs, R)
- **File I/O**: Use pytest's `tmp_path` fixture
- **Time-dependent code**: Mock `time.time()` and `datetime.now()`

### 6.2 Test Data Management
- Create reusable fixtures in `conftest.py`
- Use factories for complex test data
- Consider using Faker for realistic test data

### 6.3 Coverage Goals
- **Target**: 80% overall coverage (currently at ~84% estimated)
- **Minimum**: 70% for all business logic modules
- **Critical paths**: 90%+ coverage

### 6.4 Test Organization
```
tests/unit/
  ├── assets/           # NEW - Dagster asset tests
  ├── config/           # NEW - Configuration tests
  ├── migration/        # NEW - Migration tests
  ├── models/           # NEW - Data model tests
  │   ├── test_award.py
  │   ├── test_fiscal_models.py
  │   └── ...
  ├── validators/       # NEW - Validator tests
  ├── loaders/          # EXPAND - Add 5 new test files
  ├── transformers/     # EXPAND - Add 10 new test files
  └── transition/       # EXPAND - Add 12 new test files
```

## 7. Success Metrics

### Coverage Targets
- **Phase 1 Complete**: Critical modules >60% coverage
- **Phase 2 Complete**: High-priority modules >50% coverage
- **Phase 3 Complete**: Overall project >75% coverage
- **Phase 4 Complete**: Documentation and infrastructure in place

### Quality Targets
- **Test Execution Time**: <5 minutes for fast tests, <15 minutes for full suite
- **Flaky Tests**: <2% flake rate
- **CI Pass Rate**: >95% on first run
- **Test Maintenance**: Tests updated within same PR as code changes

### Process Targets
- **Code Review**: All PRs include tests
- **Documentation**: All test patterns documented
- **Onboarding**: New contributors can write tests within 1 day

## 8. Risk Mitigation

### Risk 1: Time Overruns
**Mitigation**:
- Prioritize by module criticality
- Can skip Phase 3-4 if needed
- Phases are independent

### Risk 2: Existing Code Changes During Testing
**Mitigation**:
- Work in feature branches
- Regular merges from main
- Coordinate with team on high-churn modules

### Risk 3: Test Infrastructure Complexity
**Mitigation**:
- Start simple, add complexity gradually
- Document all patterns as they emerge
- Regular team reviews of test approach

### Risk 4: Performance Test Variability
**Mitigation**:
- Use relative baselines, not absolute
- Run performance tests in controlled environment
- Focus on regression detection, not absolute numbers

## 9. Resource Requirements

### Personnel
- **Primary**: 1 developer full-time for 6-8 weeks
- **Support**: Code reviews from 1-2 team members (2-3 hours/week)
- **Optional**: Pair programming for complex tests

### Infrastructure
- **CI/CD**: GitHub Actions (already in place)
- **Neo4j**: Test instance (already in place)
- **Coverage**: Codecov (already in place)
- **New**: pytest-benchmark storage, flaky test tracking

### Tools/Dependencies
New dependencies to add:
- `pytest-xdist` - Parallel test execution
- `pytest-benchmark` - Performance testing
- `pytest-rerunfailures` - Flaky test handling
- `pytest-flakefinder` - Flaky test detection
- `hypothesis` - Property-based testing
- `factory-boy` (optional) - Test data factories

## 10. Next Actions

### Immediate (This Week)
1. ✅ Install testing dependencies:
   ```bash
   uv add --dev hypothesis pytest-benchmark pytest-vcr faker
   ```

2. ✅ Run actual coverage analysis:
   ```bash
   pytest --cov=src --cov-report=html --cov-report=term-missing
   ```

3. ✅ Review HTML coverage report to identify specific uncovered lines

### Short Term (Next Sprint)
4. ✅ Start Phase 3.1: Models & Validators tests
5. ✅ Create test templates for common patterns
6. ✅ Document testing patterns in CONTRIBUTING.md

### Medium Term (Next Month)
7. ✅ Complete Phase 3: Critical Gaps
8. ✅ Begin Phase 4: Partial Coverage expansion
9. ✅ Set up CI/CD coverage tracking

## 11. Appendix A: Test Naming Conventions

### Test Function Names
```python
def test_<function_name>_<scenario>_<expected_outcome>()
```

Examples:
- `test_parse_contract_row_valid_data_returns_contract()`
- `test_parse_contract_row_missing_required_field_returns_none()`
- `test_parse_contract_row_malformed_date_uses_fallback()`

### Test Class Names
```python
class Test<ClassName>:
class Test<FunctionName>:
```

Examples:
- `class TestContractExtractor:`
- `class TestParseContractRow:`

### Test File Names
```python
test_<module_name>.py
test_<feature_name>_integration.py
test_<pipeline_name>_e2e.py
```

Examples:
- `test_contract_extractor.py`
- `test_neo4j_client_integration.py`
- `test_transition_pipeline_e2e.py`

## 12. Appendix B: Coverage Calculation

Current baseline (estimated):
```
Module           Files  Lines  Covered  Coverage
extractors           6   1200        0      0%
loaders              8   1500        0      0%
quality              5    800        0      0%
utils               28   4000      200      5%
enrichers           27   3500      600     17%
transformers        13   1800      900     50%
models              15   1200      600     50%
ml                  15   2000     1600     80%
cli                 18   1500     1200     80%
transition          15   2000     1600     80%
validators           3    400      350     88%
config               2    200      180     90%
assets              48   6000     2000     33%
-------------------------------------------
TOTAL              203  26100     9230     35%
```

Target after all phases:
```
Module           Target Coverage
extractors              70%
loaders                 70%
quality                 75%
utils                   60%
enrichers               65%
transformers            70%
models                  75%
ml                      85% (maintain)
cli                     85% (maintain)
transition              85% (maintain)
validators              90% (maintain)
config                  90% (maintain)
assets                  60%
-----------------------------------
TOTAL                   75%
```

## 13. Appendix C: Example Test Patterns

### Pattern 1: Arrange-Act-Assert
```python
def test_contract_extraction():
    # Arrange
    extractor = ContractExtractor()
    sample_row = create_sample_row()

    # Act
    result = extractor.parse_row(sample_row)

    # Assert
    assert result.contract_id == "expected_id"
    assert result.amount == 100000
```

### Pattern 2: Parameterized Tests
```python
@pytest.mark.parametrize("input,expected", [
    ("FULL", CompetitionType.FULL_AND_OPEN),
    ("NONE", CompetitionType.SOLE_SOURCE),
    ("LIMITED", CompetitionType.LIMITED),
])
def test_parse_competition_type(input, expected):
    result = parse_competition_type(input)
    assert result == expected
```

### Pattern 3: Exception Testing
```python
def test_parse_invalid_row_raises_error():
    extractor = ContractExtractor()
    invalid_row = []  # Empty row

    with pytest.raises(ValidationError) as exc_info:
        extractor.parse_row(invalid_row)

    assert "missing required field" in str(exc_info.value)
```

### Pattern 4: Mock External Service
```python
@patch('requests.get')
def test_api_call(mock_get):
    mock_get.return_value.json.return_value = {"data": "value"}

    result = fetch_external_data()

    assert result == {"data": "value"}
    mock_get.assert_called_once_with("https://api.example.com")
```

### Pattern 5: Fixture Chain
```python
@pytest.fixture
def database_connection():
    conn = create_connection()
    yield conn
    conn.close()

@pytest.fixture
def populated_database(database_connection):
    load_test_data(database_connection)
    return database_connection

def test_query(populated_database):
    result = populated_database.query("SELECT * FROM test")
    assert len(result) > 0
```
