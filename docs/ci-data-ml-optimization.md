# CI Optimization for Data-Intensive and ML Workflows

**Date:** 2025-11-29
**Context:** Data refreshes are gigabytes, ML is compute-intensive but needs iterative testing

## Current State Analysis

### Data Workflows
- **data-refresh.yml**: Manual/weekly, handles GB-scale downloads (SBIR, USAspending, USPTO)
- **Status**: Already optimized (manual trigger, scheduled weekly)
- **Issue**: No CI validation of data refresh logic

### ML Workflows
- **run-ml-jobs.yml**: On-demand, 3-hour timeout
- **cet-tests in ci.yml**: Smoke tests only on PR (20 min)
- **Issue**: No iterative testing for ML changes, full pipeline only on push

### Performance Workflows
- **performance-check in ci.yml**: Runs on enrichment changes (20 min)
- **transition-mvp in ci.yml**: Runs on transition changes (15 min)

## Problems Identified

### 🔴 Critical Issues

#### 1. No CI Validation for Data Refresh Logic
**Problem:** Data refresh workflows are manual/scheduled, but code changes aren't tested in CI
**Impact:** Breaking changes to data refresh logic only discovered in production
**Risk:** High - data pipeline failures affect downstream systems

**Current:**
```yaml
# data-refresh.yml runs manually or on schedule
# No CI validation of the refresh logic itself
```

**Recommendation:** Add lightweight data refresh validation to CI
```yaml
# In ci.yml
data-refresh-validation:
  name: Validate Data Refresh Logic
  if: needs.detect-changes.outputs.data-refresh == 'true'
  steps:
    - name: Dry-run data refresh
      run: |
        # Test refresh logic without downloading GB of data
        uv run python -m src.cli.main data-refresh --dry-run --source sbir
```

#### 2. ML Changes Have No Iterative Testing
**Problem:** ML code changes only tested with full pipeline (3 hours) or smoke tests
**Impact:** Slow feedback loop for ML development
**Risk:** Medium - ML bugs caught late

**Current:**
- Smoke tests: Fast but limited coverage
- Full pipeline: Comprehensive but 3 hours

**Recommendation:** Add ML unit tests with mocked data
```yaml
# In ci.yml
ml-unit-tests:
  name: ML Unit Tests
  if: needs.detect-changes.outputs.ml == 'true'
  timeout-minutes: 10
  steps:
    - name: Run ML unit tests with mocked data
      run: |
        uv run pytest tests/unit/ml/ -v
        # Tests use small fixtures, not real data
```

#### 3. No Caching for Large Dependencies
**Problem:** ML dependencies (sentence-transformers, rpy2) reinstalled every run
**Impact:** Wastes 5-10 minutes per ML job
**Risk:** Low - just inefficient

**Recommendation:** Cache ML dependencies
```yaml
- name: Cache ML dependencies
  uses: actions/cache@v4
  with:
    path: ~/.cache/uv
    key: ml-deps-${{ runner.os }}-${{ hashFiles('pyproject.toml') }}
```

### 🟡 Medium Priority Issues

#### 4. Data Refresh Has No Size Limits in CI
**Problem:** If data refresh runs in CI, could download GBs
**Impact:** CI timeout, wasted bandwidth
**Risk:** Medium - could break CI

**Recommendation:** Add sample size limits for CI
```yaml
env:
  CI_SAMPLE_LIMIT: 1000  # Only download 1K records in CI
  SBIR_ETL__EXTRACTION__SAMPLE_LIMIT: 1000
```

#### 5. ML Jobs Run on Schedule (Wasteful)
**Problem:** `run-ml-jobs.yml` has weekly schedule but ML rarely changes
**Impact:** Wastes 3 hours of CI time weekly
**Risk:** Low - just inefficient

**Current:**
```yaml
schedule:
  - cron: '0 3 * * 1'  # Monday 3 AM UTC
```

**Recommendation:** Remove schedule, keep manual only
```yaml
on:
  workflow_dispatch:  # Manual only
```

#### 6. No Artifact Caching for ML Models
**Problem:** CET models retrained from scratch every time
**Impact:** Wastes compute, slow feedback
**Risk:** Low - just inefficient

**Recommendation:** Cache trained models
```yaml
- name: Cache CET model
  uses: actions/cache@v4
  with:
    path: data/models/cet_classifier.pkl
    key: cet-model-${{ hashFiles('src/ml/cet/**') }}
```

### 🟢 Low Priority Optimizations

#### 7. Parallel ML Test Execution
**Problem:** ML tests run sequentially
**Impact:** Slower than necessary
**Risk:** None

**Recommendation:** Use pytest-xdist for parallel execution
```yaml
- name: Run ML tests in parallel
  run: uv run pytest tests/unit/ml/ -n auto
```

#### 8. No ML Performance Benchmarks
**Problem:** No tracking of ML inference time, model size
**Impact:** Performance regressions undetected
**Risk:** Low

**Recommendation:** Add ML performance benchmarks
```yaml
- name: Benchmark ML performance
  run: |
    uv run pytest tests/benchmarks/ml/ --benchmark-only
```

## Recommended Implementation

### Phase 1: Critical Fixes (2 hours)

#### 1. Add Data Refresh Validation
```yaml
# .github/workflows/ci.yml
data-refresh-validation:
  name: Validate Data Refresh Logic
  needs: [detect-changes]
  if: |
    needs.detect-changes.outputs.docs-only != 'true' &&
    (needs.detect-changes.outputs.data-refresh == 'true' ||
     github.event_name == 'push')
  runs-on: ubuntu-latest
  timeout-minutes: 10
  steps:
    - uses: actions/checkout@v6

    - name: Setup Python and UV
      uses: ./.github/actions/setup-python-uv
      with:
        python-version: "3.11"
        install-dev-deps: "true"
        cache-venv: "true"

    - name: Validate data refresh logic (dry-run)
      env:
        CI_MODE: "true"
        SBIR_ETL__EXTRACTION__SAMPLE_LIMIT: 100
      run: |
        # Test refresh logic without downloading full datasets
        uv run python -m src.extractors.sbir_extractor --validate-only
        uv run python -m src.extractors.usaspending --validate-only
```

#### 2. Add ML Unit Tests
```yaml
# .github/workflows/ci.yml
ml-unit-tests:
  name: ML Unit Tests
  needs: [detect-changes]
  if: |
    needs.detect-changes.outputs.docs-only != 'true' &&
    needs.detect-changes.outputs.ml == 'true'
  runs-on: ubuntu-latest
  timeout-minutes: 15
  steps:
    - uses: actions/checkout@v6

    - name: Setup Python and UV
      uses: ./.github/actions/setup-python-uv
      with:
        python-version: "3.11"
        install-dev-deps: "true"
        cache-venv: "true"

    - name: Install ML dependencies
      run: |
        uv pip install sentence-transformers rpy2

    - name: Run ML unit tests with fixtures
      run: |
        uv run pytest tests/unit/ml/ -v --maxfail=3
```

#### 3. Remove ML Weekly Schedule
```yaml
# .github/workflows/run-ml-jobs.yml
on:
  workflow_dispatch:  # Manual only, remove schedule
```

### Phase 2: Efficiency Improvements (1 hour)

#### 4. Add ML Dependency Caching
```yaml
# .github/workflows/run-ml-jobs.yml
- name: Cache ML dependencies
  uses: actions/cache@v4
  with:
    path: |
      ~/.cache/uv
      ~/.cache/huggingface
    key: ml-${{ runner.os }}-${{ hashFiles('pyproject.toml', 'uv.lock') }}
    restore-keys: |
      ml-${{ runner.os }}-
```

#### 5. Add Sample Size Limits
```yaml
# .github/workflows/ci.yml (env section)
env:
  CI_SAMPLE_LIMIT: 1000
  SBIR_ETL__EXTRACTION__SAMPLE_LIMIT: 1000
  SBIR_ETL__EXTRACTION__SBIR__USE_S3_FIRST: "false"
```

### Phase 3: Advanced Optimizations (Future)

#### 6. Cache Trained Models
```yaml
- name: Cache CET model
  uses: actions/cache@v4
  with:
    path: data/models/
    key: cet-model-${{ hashFiles('src/ml/cet/**', 'config/cet/**') }}
```

#### 7. Add ML Performance Benchmarks
```yaml
- name: Benchmark ML performance
  run: |
    uv run pytest tests/benchmarks/ml/ \
      --benchmark-only \
      --benchmark-json=ml-benchmarks.json
```

## Expected Impact

### Before Optimizations
- **Data refresh changes**: No CI validation (risky)
- **ML changes**: 20 min smoke tests OR 3 hour full pipeline
- **ML weekly schedule**: 3 hours wasted weekly
- **ML dependency install**: 5-10 min every run

### After Phase 1
- **Data refresh changes**: 10 min validation (safe)
- **ML changes**: 15 min unit tests (fast feedback)
- **ML weekly schedule**: Removed (saves 3 hours/week)
- **Total savings**: ~12 hours/month

### After Phase 2
- **ML dependency install**: 1-2 min (cached)
- **Sample size limits**: Prevents accidental GB downloads
- **Total additional savings**: ~2 hours/month

## Implementation Checklist

### Phase 1 (Critical)
- [ ] Add data-refresh-validation job to ci.yml
- [ ] Add ml-unit-tests job to ci.yml
- [ ] Remove schedule from run-ml-jobs.yml
- [ ] Add detect-changes patterns for data-refresh and ml

### Phase 2 (Efficiency)
- [ ] Add ML dependency caching
- [ ] Add sample size limits to CI env
- [ ] Update data refresh to respect CI_MODE

### Phase 3 (Advanced)
- [ ] Add model caching
- [ ] Add ML performance benchmarks
- [ ] Add parallel ML test execution

## Monitoring

After implementation, track:
1. **Data refresh validation time**: Target <10 min
2. **ML unit test time**: Target <15 min
3. **ML dependency cache hit rate**: Target >80%
4. **CI minutes saved**: Target ~12 hours/month

## Risk Mitigation

### Data Refresh Validation
- **Risk**: Validation doesn't catch all issues
- **Mitigation**: Keep manual testing before production deployment

### ML Unit Tests
- **Risk**: Mocked data doesn't match real data
- **Mitigation**: Keep smoke tests and full pipeline on push

### Removing ML Schedule
- **Risk**: ML regressions not caught
- **Mitigation**: Run full ML pipeline before releases
