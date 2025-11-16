# Test Coverage Improvement Plan
## SBIR ETL Project - Comprehensive Testing Roadmap

**Document Version**: 1.0
**Created**: 2025-11-09
**Status**: Ready for Execution
**Estimated Timeline**: 6-8 weeks

---

## Executive Summary

This plan addresses critical gaps in test coverage across the SBIR ETL codebase. Current coverage is strong in ML, CLI, and transition modules, but critical infrastructure (extractors, loaders, quality) lacks tests entirely. This plan provides a phased approach to achieve comprehensive test coverage.

**Goals**:
- Achieve 80%+ test coverage across all critical modules
- Establish testing standards and documentation
- Enhance CI/CD pipeline with coverage enforcement
- Build sustainable testing infrastructure

---

## Phase 1: Critical Gaps (Weeks 1-2)
**Priority**: 🔴 CRITICAL
**Goal**: Test core data pipeline infrastructure
**Success Criteria**: All critical modules have >60% coverage

### 1.1 Extractors Module Tests (5 days)

**Files to Test** (6 files, 0 current tests):
- `contract_extractor.py` (538 lines) - Priority 1
- `sbir.py` - Priority 1
- `usaspending.py` - Priority 2
- `uspto_extractor.py` - Priority 2
- `uspto_ai_extractor.py` - Priority 3

#### Task 1.1.1: ContractExtractor Unit Tests (2 days)
**File**: `tests/unit/extractors/test_contract_extractor.py`

**Test Coverage**:
```python
class TestContractExtractor:
    # Initialization and configuration
    - test_init_with_vendor_filters
    - test_init_without_vendor_filters
    - test_load_vendor_filters_valid
    - test_load_vendor_filters_missing

    # Type checking logic
    - test_is_contract_type_valid_contracts
    - test_is_contract_type_grants_excluded
    - test_is_contract_type_idv
    - test_is_contract_type_edge_cases

    # Competition type parsing
    - test_parse_competition_full_open
    - test_parse_competition_sole_source
    - test_parse_competition_limited
    - test_parse_competition_unknown
    - test_parse_competition_null_values

    # Vendor filtering
    - test_matches_vendor_filter_by_uei
    - test_matches_vendor_filter_by_duns
    - test_matches_vendor_filter_by_name
    - test_matches_vendor_filter_no_match
    - test_matches_vendor_filter_empty_filters

    # Row parsing
    - test_parse_contract_row_complete
    - test_parse_contract_row_missing_fields
    - test_parse_contract_row_malformed_dates
    - test_parse_contract_row_negative_amounts
    - test_parse_contract_row_parent_relationships
    - test_parse_contract_row_idv_parent
    - test_parse_contract_row_validation_error
```

**Fixtures Needed**:
```python
@pytest.fixture
def sample_vendor_filters(tmp_path):
    """Sample vendor filter JSON."""

@pytest.fixture
def sample_contract_row_full():
    """Complete 102-column contract row."""

@pytest.fixture
def sample_contract_row_minimal():
    """Minimal valid contract row."""

@pytest.fixture
def sample_contract_row_grant():
    """Grant row (should be filtered)."""
```

**Deliverables**:
- [ ] Unit test file with 20+ test cases
- [ ] Fixtures for sample data
- [ ] Edge case coverage (NULL, malformed, missing)
- [ ] ~70% coverage of contract_extractor.py

#### Task 1.1.2: ContractExtractor Integration Tests (1 day)
**File**: `tests/integration/extractors/test_contract_extraction_integration.py`

**Test Coverage**:
```python
@pytest.mark.integration
class TestContractExtractionIntegration:
    - test_stream_small_dat_gz_file
    - test_extract_from_dump_end_to_end
    - test_statistics_tracking
    - test_batch_processing
    - test_parquet_output_format
    - test_relationship_tracking
```

**Test Data Needed**:
- Create `tests/fixtures/sample_contracts.dat.gz` (100 rows)
- Include mix: contracts, grants, IDVs, malformed rows

**Deliverables**:
- [ ] Integration test file with 6+ test cases
- [ ] Sample .dat.gz fixture
- [ ] Parquet output validation
- [ ] Statistics verification

#### Task 1.1.3: Other Extractor Tests (2 days)
**Files**:
- `tests/unit/extractors/test_sbir_extractor.py`
- `tests/unit/extractors/test_usaspending_extractor.py`
- `tests/unit/extractors/test_uspto_extractor.py`

**Coverage**: Similar patterns to ContractExtractor, focus on:
- Data parsing logic
- Field mapping
- Error handling
- Edge cases

**Deliverables**:
- [ ] Unit tests for SBIR extractor (10+ tests)
- [ ] Unit tests for USAspending extractor (10+ tests)
- [ ] Unit tests for USPTO extractors (15+ tests)

---

### 1.2 Loaders Module Tests (4 days)

**Files to Test** (8 files, 0 current tests):
- `neo4j/client.py` (387 lines) - Priority 1
- `neo4j/cet.py` - Priority 2
- `neo4j/patents.py` - Priority 2
- `neo4j/transitions.py` - Priority 3
- `neo4j/profiles.py` - Priority 3

#### Task 1.2.1: Neo4jClient Unit Tests with Mocks (2 days)
**File**: `tests/unit/loaders/test_neo4j_client.py`

**Test Coverage**:
```python
class TestNeo4jClient:
    # Initialization
    - test_init_creates_config
    - test_driver_lazy_initialization
    - test_close_closes_driver

    # Node operations (mocked)
    - test_upsert_node_creates_new
    - test_upsert_node_updates_existing
    - test_upsert_node_missing_key_property
    - test_upsert_node_cleanup_flag

    # Batch operations
    - test_batch_upsert_nodes_single_batch
    - test_batch_upsert_nodes_multiple_batches
    - test_batch_upsert_nodes_with_errors
    - test_batch_upsert_metrics_tracking

    # Relationship operations
    - test_create_relationship_success
    - test_create_relationship_missing_source
    - test_create_relationship_missing_target
    - test_batch_create_relationships

    # Constraints and indexes
    - test_create_constraints
    - test_create_indexes

    # Context manager
    - test_context_manager_closes_driver
```

**Mocking Strategy**:
```python
from unittest.mock import Mock, MagicMock, patch

@patch('neo4j.GraphDatabase.driver')
def test_upsert_node_creates_new(mock_driver):
    # Mock driver, session, transaction, result
    mock_session = MagicMock()
    mock_tx = MagicMock()
    mock_driver.return_value.session.return_value.__enter__.return_value = mock_session
    # ... setup mocks
```

**Deliverables**:
- [ ] Unit test file with 20+ test cases
- [ ] Full mock coverage of Neo4j driver
- [ ] Metrics tracking validation
- [ ] Error handling tests

#### Task 1.2.2: Neo4jClient Integration Tests (1 day)
**File**: `tests/integration/loaders/test_neo4j_client_integration.py`

**Test Coverage**:
```python
@pytest.mark.integration
class TestNeo4jClientIntegration:
    - test_real_connection
    - test_upsert_node_creates_in_database
    - test_upsert_node_updates_in_database
    - test_batch_upsert_large_dataset
    - test_create_relationship_in_database
    - test_transaction_rollback_on_error
    - test_constraints_prevent_duplicates
```

**Prerequisites**:
- Neo4j test instance (already used in CI)
- Database cleanup fixtures

**Deliverables**:
- [ ] Integration tests with real Neo4j (8+ tests)
- [ ] Transaction testing
- [ ] Constraint validation
- [ ] Performance baseline

#### Task 1.2.3: Specialized Loader Tests (1 day)
**Files**:
- `tests/unit/loaders/test_cet_loader.py`
- `tests/unit/loaders/test_patent_loader.py`
- `tests/integration/loaders/test_loader_integration.py`

**Coverage**: Each specialized loader
- Data transformation before loading
- Cypher query generation
- Relationship creation
- Error handling

**Deliverables**:
- [ ] Unit tests for CET loader (8+ tests)
- [ ] Unit tests for patent loader (8+ tests)
- [ ] Integration tests for loaders (5+ tests)

---

### 1.3 Quality Module Tests (3 days)

**Files to Test** (5 files, 0 current tests):
- `baseline.py` - Quality baseline metrics
- `checks.py` - Validation checks
- `dashboard.py` - Dashboard generation
- `uspto_validators.py` - USPTO validators

#### Task 1.3.1: Quality Checks Unit Tests (1.5 days)
**File**: `tests/unit/quality/test_quality_checks.py`

**Test Coverage**:
```python
class TestQualityChecks:
    - test_check_completeness_passing
    - test_check_completeness_failing
    - test_check_threshold_validations
    - test_check_data_types
    - test_check_referential_integrity
    - test_check_custom_rules
    - test_check_aggregations
```

**Deliverables**:
- [ ] Unit tests for quality checks (15+ tests)
- [ ] Sample datasets for validation
- [ ] Threshold testing

#### Task 1.3.2: Baseline and Dashboard Tests (1.5 days)
**Files**:
- `tests/unit/quality/test_baseline.py`
- `tests/unit/quality/test_dashboard.py`
- `tests/unit/quality/test_uspto_validators.py`

**Coverage**:
- Baseline metric calculations
- Dashboard rendering (snapshot tests)
- USPTO-specific validation rules

**Deliverables**:
- [ ] Baseline tests (8+ tests)
- [ ] Dashboard tests with snapshots (5+ tests)
- [ ] USPTO validator tests (10+ tests)

---

## Phase 2: High Priority (Weeks 3-4)
**Priority**: ⚠️ HIGH
**Goal**: Test utility and enrichment infrastructure
**Success Criteria**: High-use utilities and enrichers have >50% coverage

### 2.1 Utils Module Tests (5 days)

**Files to Test** (28 files, 1 current test):
- **Priority 1**: `duckdb_client.py`, `metrics.py`, `text_normalization.py`
- **Priority 2**: `performance_monitor.py`, `enrichment_checkpoints.py`, `fiscal_audit_trail.py`
- **Priority 3**: `reporting/*` (9 files)

#### Task 2.1.1: Core Utility Tests (2 days)
**Files**:
- `tests/unit/utils/test_duckdb_client.py`
- `tests/unit/utils/test_metrics.py`
- `tests/unit/utils/test_text_normalization.py`

**DuckDB Client Tests**:
```python
class TestDuckDBClient:
    - test_connection_creation
    - test_query_execution
    - test_batch_insert
    - test_transaction_handling
    - test_connection_pooling
    - test_error_recovery
```

**Metrics Tests**:
```python
class TestMetrics:
    - test_counter_increment
    - test_gauge_set
    - test_histogram_record
    - test_metrics_export
    - test_metrics_reset
```

**Text Normalization Tests**:
```python
class TestTextNormalization:
    - test_normalize_whitespace
    - test_remove_special_characters
    - test_case_normalization
    - test_unicode_handling
    - test_idempotency
    - test_empty_and_null_handling
```

**Deliverables**:
- [ ] DuckDB client tests (10+ tests)
- [ ] Metrics tests (8+ tests)
- [ ] Text normalization tests (12+ tests)

#### Task 2.1.2: Performance and Checkpoint Tests (2 days)
**Files**:
- `tests/unit/utils/test_performance_monitor.py`
- `tests/unit/utils/test_enrichment_checkpoints.py`
- `tests/unit/utils/test_fiscal_audit_trail.py`

**Deliverables**:
- [ ] Performance monitor tests (10+ tests)
- [ ] Checkpoint management tests (10+ tests)
- [ ] Audit trail tests (8+ tests)

#### Task 2.1.3: Reporting Utilities Tests (1 day)
**Files**:
- `tests/unit/utils/reporting/test_analyzers.py`
- `tests/unit/utils/reporting/test_formats.py`

**Coverage**:
- All analyzer classes (patent, CET, transition, SBIR)
- All format processors (JSON, HTML, Markdown)

**Deliverables**:
- [ ] Analyzer tests (15+ tests)
- [ ] Format processor tests (10+ tests)

---

### 2.2 Enrichers Module Tests (5 days)

**Files to Test** (27 files, 2 current tests):
- **Priority 1**: `fiscal_bea_mapper.py`, `inflation_adjuster.py`, `company_enricher.py`
- **Priority 2**: `geographic_resolver.py`, `transition_detector.py`
- **Priority 3**: `naics/fiscal/strategies/*` (7 files), `search_providers/*`

#### Task 2.2.1: Core Enricher Tests (2 days)
**Files**:
- `tests/unit/enrichers/test_fiscal_bea_mapper.py`
- `tests/unit/enrichers/test_inflation_adjuster.py`
- `tests/unit/enrichers/test_company_enricher.py`

**Fiscal BEA Mapper Tests**:
```python
class TestFiscalBEAMapper:
    - test_map_naics_to_bea
    - test_map_with_missing_data
    - test_map_multiple_sectors
    - test_map_edge_cases
    - test_cache_behavior
```

**Inflation Adjuster Tests**:
```python
class TestInflationAdjuster:
    - test_adjust_to_current_year
    - test_adjust_to_specific_year
    - test_adjust_batch
    - test_missing_year_data
    - test_calculation_accuracy
    - test_edge_years
```

**Deliverables**:
- [ ] Fiscal BEA mapper tests (8+ tests)
- [ ] Inflation adjuster tests (10+ tests)
- [ ] Company enricher tests (12+ tests)

#### Task 2.2.2: NAICS Strategy Tests (2 days)
**Directory**: `tests/unit/enrichers/naics/`

**Files**:
- `test_original_data.py`
- `test_topic_code.py`
- `test_text_inference.py`
- `test_sector_fallback.py`
- `test_agency_defaults.py`
- `test_usaspending_dataframe.py`

**Each Strategy Test Suite**:
```python
class TestOriginalDataStrategy:
    - test_strategy_applies_when_conditions_met
    - test_strategy_skips_when_conditions_not_met
    - test_strategy_priority_order
    - test_strategy_data_quality
    - test_strategy_error_handling
```

**Deliverables**:
- [ ] Tests for all 6 NAICS strategies (30+ tests total)
- [ ] Strategy integration tests (5+ tests)

#### Task 2.2.3: Search Provider and Integration Tests (1 day)
**Files**:
- `tests/unit/enrichers/test_search_providers.py`
- `tests/integration/enrichers/test_enrichment_pipeline.py`

**Deliverables**:
- [ ] Search provider tests (8+ tests)
- [ ] Mock SearxNG integration
- [ ] End-to-end enrichment tests (5+ tests)

---

## Phase 3: Expand Coverage (Weeks 5-6)
**Priority**: ⚠️ MEDIUM
**Goal**: Advanced testing patterns and remaining gaps
**Success Criteria**: Project-wide coverage >75%

### 3.1 Property-Based Testing (3 days)

#### Task 3.1.1: Install and Configure Hypothesis (0.5 days)
```bash
uv add --dev hypothesis
```

**Configuration** in `pyproject.toml`:
```toml
[tool.hypothesis]
max_examples = 100
deadline = None  # For slower tests
derandomize = true  # For CI reproducibility
```

**Deliverables**:
- [ ] Hypothesis installed and configured
- [ ] Documentation on property-based testing patterns

#### Task 3.1.2: Text Processing Property Tests (1 day)
**File**: `tests/unit/utils/test_text_normalization_properties.py`

```python
from hypothesis import given, strategies as st

class TestTextNormalizationProperties:
    @given(st.text())
    def test_normalize_idempotent(self, text):
        """Normalization should be idempotent."""

    @given(st.text())
    def test_normalize_preserves_length_order(self, text):
        """Normalized text should not be longer than original."""

    @given(st.text(min_size=1))
    def test_normalize_non_empty_stays_non_empty(self, text):
        """Non-empty input should produce non-empty output."""
```

**Deliverables**:
- [ ] Property tests for text normalization (5+ properties)
- [ ] Property tests for data parsing (5+ properties)

#### Task 3.1.3: Numeric and Date Property Tests (1 day)
**Files**:
- `tests/unit/enrichers/test_inflation_properties.py`
- `tests/unit/utils/test_date_parsing_properties.py`

**Inflation Properties**:
```python
@given(st.floats(min_value=0, max_value=1e9),
       st.integers(min_value=1950, max_value=2030),
       st.integers(min_value=1950, max_value=2030))
def test_inflation_adjustment_reversible(amount, from_year, to_year):
    """Adjusting forward and backward should return to original."""

@given(st.floats(min_value=0, max_value=1e9))
def test_inflation_adjustment_positive(amount):
    """Inflation adjustment should never produce negative values."""
```

**Deliverables**:
- [ ] Property tests for inflation (5+ properties)
- [ ] Property tests for date parsing (5+ properties)
- [ ] Property tests for data models (3+ properties)

#### Task 3.1.4: Data Model Property Tests (0.5 days)
**File**: `tests/unit/models/test_model_properties.py`

```python
@given(build_federal_contract_strategy())
def test_federal_contract_serialization_roundtrip(contract):
    """Serialization should be reversible."""

@given(build_cet_assessment_strategy())
def test_cet_assessment_confidence_bounds(assessment):
    """Confidence scores should be in [0, 1]."""
```

**Deliverables**:
- [ ] Property tests for data models (5+ properties)
- [ ] Custom Hypothesis strategies for complex models

---

### 3.2 Assets Module Tests (4 days)

**Files to Test** (48 files, 5 current tests):
- Dagster assets for all pipelines
- Focus on most-used and critical assets

#### Task 3.2.1: Core Asset Tests (2 days)
**Priority Assets**:
- SBIR ingestion assets
- Contract ingestion assets
- Patent ETL assets
- CET classification assets

**Test Pattern** (using Dagster testing utilities):
```python
from dagster import build_op_context, materialize

class TestSBIRAssets:
    def test_sbir_ingestion_asset():
        """Test SBIR ingestion asset materialization."""
        context = build_op_context()
        result = sbir_ingestion(context)
        assert result is not None
        # Validate output schema, data quality

    def test_sbir_ingestion_asset_with_config():
        """Test with custom configuration."""

    def test_sbir_ingestion_asset_error_handling():
        """Test error scenarios."""
```

**Deliverables**:
- [ ] Tests for SBIR assets (10+ tests)
- [ ] Tests for contract assets (10+ tests)
- [ ] Tests for patent assets (10+ tests)
- [ ] Tests for CET assets (10+ tests)

#### Task 3.2.2: Asset Dependency and Integration Tests (2 days)
**File**: `tests/e2e/test_asset_dependencies.py`

```python
@pytest.mark.e2e
class TestAssetDependencies:
    def test_sbir_to_enrichment_pipeline():
        """Test data flows from ingestion to enrichment."""

    def test_transition_detection_pipeline():
        """Test complete transition detection pipeline."""

    def test_asset_dependency_graph():
        """Test all dependencies are resolvable."""
```

**Deliverables**:
- [ ] Asset dependency tests (8+ tests)
- [ ] Pipeline integration tests (5+ tests)
- [ ] Asset validation tests (5+ tests)

---

### 3.3 Performance Tests (3 days)

#### Task 3.3.1: Benchmark Infrastructure (1 day)
**File**: `tests/performance/conftest.py`

**Setup**:
- Install `pytest-benchmark`
- Configure benchmark storage
- Set up performance baselines

```python
@pytest.fixture
def benchmark_config():
    """Standard benchmark configuration."""
    return {
        "min_rounds": 5,
        "max_time": 1.0,
        "warmup": True,
    }
```

**Deliverables**:
- [ ] pytest-benchmark installed
- [ ] Benchmark configuration
- [ ] Baseline results stored

#### Task 3.3.2: Critical Path Benchmarks (1 day)
**File**: `tests/performance/test_critical_paths.py`

```python
@pytest.mark.slow
class TestCriticalPathPerformance:
    def test_contract_extraction_performance(benchmark):
        """Benchmark contract extraction speed."""
        benchmark(extract_contracts, sample_data)

    def test_cet_classification_performance(benchmark):
        """Benchmark CET classification speed."""

    def test_neo4j_batch_load_performance(benchmark):
        """Benchmark Neo4j loading speed."""
```

**Deliverables**:
- [ ] Extraction benchmarks (3+ tests)
- [ ] Classification benchmarks (3+ tests)
- [ ] Loading benchmarks (3+ tests)

#### Task 3.3.3: Memory and Resource Tests (1 day)
**File**: `tests/performance/test_resource_usage.py`

```python
@pytest.mark.slow
def test_contract_extractor_memory_usage():
    """Test memory stays bounded during streaming."""
    import psutil
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    # Run extraction
    final_memory = process.memory_info().rss
    assert (final_memory - initial_memory) < 500_000_000  # <500MB
```

**Deliverables**:
- [ ] Memory profiling tests (5+ tests)
- [ ] Resource leak detection (3+ tests)
- [ ] Performance regression detection

---

## Phase 4: Infrastructure & Polish (Week 7-8)
**Priority**: 🔵 INFRASTRUCTURE
**Goal**: Sustainable testing practices
**Success Criteria**: Testing infrastructure supports long-term maintenance

### 4.1 Test Documentation (3 days)

#### Task 4.1.1: Main Testing Guide (1 day)
**File**: `tests/README.md`

**Contents**:
```markdown
# Testing Guide

## Overview
- Testing philosophy
- Test structure (unit/integration/e2e)
- Running tests
- Writing new tests

## Quick Start
```bash
# Run all tests
uv run pytest

# Run fast tests only
uv run pytest -m fast

# Run with coverage
uv run pytest --cov=src --cov-report=html
```

## Test Categories
### Unit Tests
- Location: tests/unit/
- Speed: <1s each
- Marker: @pytest.mark.fast
...

## Writing Tests
### Test Naming Conventions
### Using Fixtures
### Mocking External Services
### Property-Based Testing

## CI/CD
### On Commit
### On Pull Request
### Coverage Requirements
```

**Deliverables**:
- [ ] `tests/README.md` (comprehensive guide)
- [ ] Examples for each test type
- [ ] Troubleshooting guide

#### Task 4.1.2: Module-Specific Documentation (1 day)
**Files**:
- `tests/unit/extractors/README.md`
- `tests/unit/loaders/README.md`
- `tests/integration/README.md`
- `tests/e2e/README.md`

**Each file includes**:
- Module-specific testing patterns
- Test data management
- Common pitfalls
- Example tests

**Deliverables**:
- [ ] Documentation for each test directory
- [ ] Test data documentation
- [ ] Fixture documentation updates

#### Task 4.1.3: Contributing Guide Updates (1 day)
**File**: `CONTRIBUTING.md` (update testing section)

**Add**:
- Testing requirements for PRs
- How to run relevant tests
- Coverage expectations
- Review process

**Deliverables**:
- [ ] Updated CONTRIBUTING.md
- [ ] PR template with testing checklist
- [ ] Testing best practices document

---

### 4.2 Test Data Management (2 days)

#### Task 4.2.1: Test Data Factory Setup (1 day)
**Install**: `factory-boy` or custom factories

**File**: `tests/factories/__init__.py`

```python
class FederalContractFactory:
    """Factory for creating test FederalContract instances."""

    @staticmethod
    def create(contract_id=None, **kwargs):
        defaults = {
            "contract_id": contract_id or f"TEST_{uuid.uuid4()}",
            "agency": "Department of Defense",
            "vendor_name": "Test Company Inc",
            # ...
        }
        defaults.update(kwargs)
        return FederalContract(**defaults)

    @staticmethod
    def create_batch(n=10, **kwargs):
        return [FederalContractFactory.create(**kwargs) for _ in range(n)]
```

**Deliverables**:
- [ ] Factory classes for all major models (8+ factories)
- [ ] Factory documentation
- [ ] Migration guide for existing tests

#### Task 4.2.2: Centralize and Version Test Data (1 day)
**Structure**:
```
tests/fixtures/
├── contracts/
│   ├── sample_100_rows.dat.gz
│   ├── malformed_data.dat.gz
│   └── README.md
├── patents/
│   ├── sample_patents.json
│   └── README.md
├── sbir/
│   ├── sbir_sample.csv (existing)
│   └── README.md
└── enrichment/
    ├── enrichment_scenarios.json (existing)
    └── README.md
```

**Deliverables**:
- [ ] Organized fixture directory
- [ ] README for each fixture set
- [ ] Version tracking for test data
- [ ] Data generation scripts

---

### 4.3 CI/CD Enhancements (3 days)

#### Task 4.3.1: Coverage Requirements (1 day)
**File**: `.github/workflows/on-pr.yml` (update)

**Add**:
```yaml
- name: Check coverage threshold
  run: |
    uv run pytest --cov=src --cov-fail-under=75 --cov-report=term-missing

- name: Coverage comment
  uses: py-cov-action/python-coverage-comment-action@v3
  with:
    GITHUB_TOKEN: ${{ github.token }}
    MINIMUM_GREEN: 80
    MINIMUM_ORANGE: 60
```

**Configuration** in `pyproject.toml`:
```toml
[tool.coverage.run]
omit = [
    "*/tests/*",
    "*/conftest.py",
    "*/__init__.py",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

**Deliverables**:
- [ ] Coverage threshold enforcement (75%)
- [ ] PR coverage comments
- [ ] Coverage trend tracking
- [ ] Exclude patterns configured

#### Task 4.3.2: Parallel Test Execution (1 day)
**Install**: `pytest-xdist`

```bash
uv add --dev pytest-xdist
```

**Update CI**:
```yaml
- name: Run tests in parallel
  run: |
    uv run pytest -n auto -m "not slow" --dist loadgroup
```

**Configuration**:
```toml
[tool.pytest.ini_options]
# Distribute tests by markers to keep integration tests together
addopts = "-v --cov=src --cov-report=term-missing -n auto"
```

**Deliverables**:
- [ ] pytest-xdist installed and configured
- [ ] CI updated to run tests in parallel
- [ ] Test execution time reduced by 40-60%

#### Task 4.3.3: Flaky Test Detection (1 day)
**Install**: `pytest-rerunfailures` and `pytest-flakefinder`

```bash
uv add --dev pytest-rerunfailures pytest-flakefinder
```

**Configuration**:
```toml
[tool.pytest.ini_options]
# Automatically rerun flaky tests
addopts = "--reruns 3 --reruns-delay 1"
```

**Add CI job** (`.github/workflows/detect-flaky-tests.yml`):
```yaml
name: Detect Flaky Tests
on:
  schedule:
    - cron: '0 2 * * *'  # Nightly

jobs:
  flaky-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests 10 times
        run: |
          uv run pytest --flake-finder --flake-runs=10
      - name: Report flaky tests
        if: failure()
        uses: actions/github-script@v6
        # Create issue if flaky tests found
```

**Deliverables**:
- [ ] Flaky test detection installed
- [ ] Nightly flaky test detection
- [ ] Automatic issue creation for flaky tests
- [ ] Rerun configuration for known flaky tests

---

## Quick Wins (Can be done anytime)

### Quick Win 1: Smoke Tests (2 hours)
Add basic import tests for all untested modules:

**File**: `tests/smoke/test_imports.py`
```python
def test_extractors_import():
    """Smoke test: all extractors can be imported."""
    from src.extractors.contract_extractor import ContractExtractor
    from src.extractors.sbir import SBIRExtractor
    # ... all extractors
    assert True  # If we get here, imports work

def test_loaders_import():
    """Smoke test: all loaders can be imported."""
    # ...
```

### Quick Win 2: Run Coverage Report (30 minutes)
```bash
uv run pytest --cov=src --cov-report=html --cov-report=term-missing
open htmlcov/index.html
```
Save report as baseline and identify lowest-hanging fruit.

### Quick Win 3: Add Test Template (1 hour)
**File**: `tests/TEMPLATE.py`
```python
"""
Template for writing new tests.

Copy this file and rename to test_<module>.py
"""

import pytest

pytestmark = pytest.mark.fast  # or integration, slow, e2e


@pytest.fixture
def sample_data():
    """Fixture providing test data."""
    return {"key": "value"}


class TestModuleName:
    """Tests for ModuleName."""

    def test_basic_functionality(self, sample_data):
        """Test basic functionality."""
        # Arrange
        # Act
        # Assert
        assert True
```

### Quick Win 4: Test-on-Bug-Fix Policy (Documentation)
Add to `CONTRIBUTING.md`:
> When fixing a bug, always add a test that:
> 1. Fails before the fix
> 2. Passes after the fix
> 3. Prevents regression

---

## Success Metrics

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

---

## Risk Mitigation

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

---

## Resource Requirements

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

---

## Next Steps

1. **Review this plan** with the team
2. **Create tracking board** (GitHub Projects or similar)
3. **Set up feature branch**: `feature/comprehensive-test-coverage`
4. **Begin Phase 1, Task 1.1.1**: ContractExtractor unit tests
5. **Schedule weekly reviews** to track progress and adjust

---

## Appendix A: Test Naming Conventions

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

---

## Appendix B: Coverage Calculation

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

---

## Appendix C: Example Test Patterns

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

---

**End of Test Coverage Improvement Plan**
