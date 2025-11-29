# File-Specific Refactoring Plan

This document provides detailed refactoring recommendations for specific test files, prioritized by impact and effort.

## 🔥 Priority 1: Large Files (>1000 LOC)

### 1. `tests/validation/test_categorization_validation.py` (1513 LOC)

**Current Structure**: Single monolithic file with multiple validation types

**Proposed Split**:
```
tests/validation/categorization/
├── __init__.py
├── test_schema_validation.py       # Schema and type validation (300 LOC)
├── test_business_rules.py          # Business logic validation (400 LOC)
├── test_data_quality.py            # Data quality checks (350 LOC)
├── test_edge_cases.py              # Edge case handling (300 LOC)
└── conftest.py                     # Shared fixtures (150 LOC)
```

**Benefits**:
- Easier to locate specific validation tests
- Faster test execution (better parallelization)
- Clearer test organization

**Effort**: 4-6 hours

---

### 2. `tests/unit/transition/detection/test_detector.py` (1085 LOC)

**Current Structure**: All detection logic in one file

**Proposed Split**:
```
tests/unit/transition/detection/
├── __init__.py
├── test_vendor_matching.py         # Vendor resolution tests (250 LOC)
├── test_timing_signals.py          # Timing proximity tests (200 LOC)
├── test_patent_signals.py          # Patent signal tests (180 LOC)
├── test_cet_signals.py             # CET alignment tests (150 LOC)
├── test_scoring_integration.py     # End-to-end scoring (200 LOC)
└── conftest.py                     # Shared fixtures (100 LOC)
```

**Key Improvements**:
- Use `DataFrameBuilder` for test data
- Use `Neo4jMocks` for database mocks
- Extract common assertion helpers

**Effort**: 6-8 hours

---

### 3. `tests/unit/assets/test_fiscal_assets.py` (1061 LOC)

**Current Structure**: All fiscal asset tests in one file

**Proposed Split**:
```
tests/unit/assets/fiscal/
├── __init__.py
├── test_enrichment_assets.py       # BEA mapping, NAICS enrichment (300 LOC)
├── test_transformation_assets.py   # ROI calculation, tax estimation (350 LOC)
├── test_loading_assets.py          # Neo4j loading (250 LOC)
├── test_asset_checks.py            # Quality gates (150 LOC)
└── conftest.py                     # Shared fixtures (100 LOC)
```

**Key Improvements**:
- Use `ConfigMocks.pipeline_config()` for configuration
- Use `DataFrameBuilder.awards()` for test data
- Consolidate duplicate setup code

**Effort**: 6-8 hours

---

### 4. `tests/unit/loaders/neo4j/test_transitions.py` (1040 LOC)

**Current Structure**: All transition loading tests in one file

**Proposed Split**:
```
tests/unit/loaders/neo4j/transitions/
├── __init__.py
├── test_award_contract_relationships.py    # Award-Contract links (300 LOC)
├── test_company_transition_profiles.py     # Company profiles (250 LOC)
├── test_signal_relationships.py            # Signal metadata (200 LOC)
├── test_batch_loading.py                   # Batch operations (200 LOC)
└── conftest.py                             # Shared fixtures (100 LOC)
```

**Key Improvements**:
- Use `Neo4jMocks` for all database mocks
- Use `DataFrameBuilder` for test data
- Extract common Cypher query assertions

**Effort**: 5-7 hours

---

### 5. `tests/unit/enrichers/test_chunked_enrichment.py` (1030 LOC)

**Current Structure**: All chunked enrichment tests in one file

**Proposed Split**:
```
tests/unit/enrichers/chunked/
├── __init__.py
├── test_sam_gov_enrichment.py      # SAM.gov API enrichment (300 LOC)
├── test_usaspending_enrichment.py  # USAspending enrichment (300 LOC)
├── test_fuzzy_matching.py          # Fuzzy name matching (250 LOC)
├── test_memory_management.py       # Spill-to-disk, chunking (150 LOC)
└── conftest.py                     # Shared fixtures (100 LOC)
```

**Key Improvements**:
- Use `EnrichmentMocks` for API clients
- Use `DataFrameBuilder` for test data
- Consolidate duplicate enrichment result validation

**Effort**: 5-7 hours

---

## 🎯 Priority 2: High-Complexity Files (500-1000 LOC)

### 6. `tests/unit/transition/features/test_vendor_crosswalk.py` (915 LOC)

**Recommendations**:
- Extract common vendor matching patterns to helper functions
- Use `DataFrameBuilder.companies()` for test data
- Consolidate duplicate assertion logic

**Estimated Savings**: 150-200 LOC
**Effort**: 3-4 hours

---

### 7. `tests/unit/transition/features/test_patent_analyzer.py` (894 LOC)

**Recommendations**:
- Use `DataFrameBuilder.patents()` for test data
- Extract patent similarity calculation helpers
- Consolidate duplicate setup code

**Estimated Savings**: 120-150 LOC
**Effort**: 3-4 hours

---

### 8. `tests/unit/enrichers/usaspending/test_client.py` (882 LOC)

**Recommendations**:
- Use `EnrichmentMocks.usaspending_client()` for mocks
- Extract common API response validation
- Consolidate duplicate error handling tests

**Estimated Savings**: 150-180 LOC
**Effort**: 3-4 hours

---

### 9. `tests/e2e/test_fiscal_stateio_pipeline.py` (869 LOC)

**Recommendations**:
- Extract common pipeline setup to fixtures
- Use `DataFrameBuilder` for test data
- Consolidate duplicate validation logic

**Estimated Savings**: 120-150 LOC
**Effort**: 4-5 hours

---

### 10. `tests/unit/transition/evaluation/test_evaluator.py` (861 LOC)

**Recommendations**:
- Use `DataFrameBuilder` for test data
- Extract common evaluation metric calculations
- Consolidate duplicate threshold testing

**Estimated Savings**: 100-130 LOC
**Effort**: 3-4 hours

---

## 🔧 Priority 3: Moderate Refactoring (300-500 LOC)

### Files with High Mock Usage

These files have 20+ `Mock()` usages and would benefit from mock factories:

1. `tests/unit/models/test_award.py` (845 LOC, 35 mocks)
2. `tests/unit/config/test_schemas.py` (795 LOC, 28 mocks)
3. `tests/unit/enrichers/test_search_providers.py` (786 LOC, 42 mocks)
4. `tests/unit/transformers/test_patent_transformer.py` (758 LOC, 25 mocks)
5. `tests/unit/utils/test_statistical_reporter.py` (734 LOC, 18 mocks)

**Recommendations for Each**:
- Replace inline `Mock()` with appropriate factory from `tests/mocks/`
- Extract common mock configurations to fixtures
- Use `DataFrameBuilder` where applicable

**Estimated Savings per File**: 50-80 LOC
**Effort per File**: 2-3 hours

---

## 📊 Refactoring Impact Summary

### By Priority

| Priority | Files | Total LOC | Est. Savings | Effort (hours) |
|----------|-------|-----------|--------------|----------------|
| P1 (>1000 LOC) | 5 | 5,689 | 800-1,000 | 26-36 |
| P2 (500-1000 LOC) | 5 | 4,401 | 640-810 | 16-21 |
| P3 (300-500 LOC) | 5 | 3,918 | 250-400 | 10-15 |
| **Total** | **15** | **14,008** | **1,690-2,210** | **52-72** |

### Expected Outcomes

**Quantitative**:
- Reduce test code by ~12-16% (1,690-2,210 lines)
- Improve test organization (15 files → 40+ focused files)
- Reduce average file size from 934 LOC to ~350 LOC

**Qualitative**:
- Easier test navigation and maintenance
- Better test parallelization
- Clearer test intent and organization
- Reduced cognitive load for developers

---

## 🚀 Implementation Strategy

### Week 1: Foundation
- Create mock factories (`tests/mocks/`)
- Extend DataFrame builders (`tests/factories.py`)
- Document new patterns

### Week 2-3: Priority 1 Files
- Refactor 5 largest files (>1000 LOC)
- Migrate to new patterns
- Update documentation

### Week 4: Priority 2 Files
- Refactor 5 high-complexity files (500-1000 LOC)
- Continue pattern migration
- Add missing test coverage

### Week 5: Priority 3 Files + Cleanup
- Refactor remaining high-impact files
- Standardize naming conventions
- Final documentation updates

---

## 📋 File-by-File Checklist

Use this checklist when refactoring each file:

### Pre-Refactoring
- [ ] Read through entire file to understand test coverage
- [ ] Identify duplicate patterns (mocks, data creation, assertions)
- [ ] Note any missing test coverage
- [ ] Check for test interdependencies

### During Refactoring
- [ ] Replace inline mocks with factory methods
- [ ] Replace inline DataFrames with builders
- [ ] Extract common setup to fixtures
- [ ] Extract common assertions to helpers
- [ ] Split large files into focused modules
- [ ] Update imports and references

### Post-Refactoring
- [ ] Run all tests to ensure no regressions
- [ ] Check test coverage (should remain ≥85%)
- [ ] Update test documentation
- [ ] Review with team member
- [ ] Update this checklist with lessons learned

---

## 🎓 Lessons Learned Template

After refactoring each file, document lessons learned:

```markdown
### File: tests/unit/transition/detection/test_detector.py

**Date**: YYYY-MM-DD
**Refactored By**: [Name]

**Before**:
- 1085 LOC in single file
- 45 inline Mock() creations
- 30 inline DataFrame creations
- Difficult to locate specific tests

**After**:
- Split into 6 focused files (~180 LOC each)
- All mocks use factories
- All DataFrames use builders
- Clear test organization

**Challenges**:
- Some tests had hidden interdependencies
- Mock configurations were inconsistent
- Test data had subtle variations

**Solutions**:
- Added explicit test isolation
- Standardized mock configurations
- Documented test data variations

**Time Spent**: 7 hours
**Lines Saved**: 185 LOC
**Tests Added**: 3 (for previously missing coverage)
```

---

## 🔍 Code Review Checklist

When reviewing refactored test files:

### Structure
- [ ] File is <800 LOC
- [ ] Tests are logically grouped
- [ ] Clear separation of concerns
- [ ] Appropriate use of fixtures

### Patterns
- [ ] Uses mock factories instead of inline mocks
- [ ] Uses DataFrame builders instead of inline creation
- [ ] Follows naming conventions
- [ ] Has clear docstrings

### Quality
- [ ] All tests pass
- [ ] Coverage maintained or improved
- [ ] No test interdependencies
- [ ] Clear assertion messages

### Documentation
- [ ] File has module docstring
- [ ] Complex tests have docstrings
- [ ] Fixtures are documented
- [ ] Edge cases are explained

---

## 📚 Related Documents

- `TEST_IMPROVEMENT_ANALYSIS.md` - Overall analysis and strategy
- `REFACTORING_GUIDE.md` - Implementation guide with code examples
- `tests/README.md` - Test organization guidelines
- `CONTRIBUTING.md` - Code quality standards
