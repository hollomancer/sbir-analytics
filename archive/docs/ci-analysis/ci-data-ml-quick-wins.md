# CI Data/ML Quick Wins

## Summary

**Problem:** Data refreshes are GB-scale (manual/weekly), ML is compute-intensive (3 hours), but both need iterative testing in CI.

**Solution:** Add lightweight validation without downloading/processing full datasets.

## Quick Wins (30 min implementation)

### 1. Remove ML Weekly Schedule (Saves 3 hours/week)

**File:** `.github/workflows/run-ml-jobs.yml`

**Change:**
```yaml
# BEFORE
on:
  workflow_dispatch:
    ...
  schedule:
    - cron: '0 3 * * 1'  # Monday 3 AM UTC

# AFTER
on:
  workflow_dispatch:
    ...
  # Remove schedule - ML rarely changes, manual trigger is sufficient
```

**Savings:** 12 hours/month (3 hours × 4 weeks)

### 2. Add Sample Size Limits for CI

**File:** `.github/workflows/ci.yml`

**Add to env section:**
```yaml
env:
  PYTHON_VERSION: "3.11"
  # ... existing vars ...

  # CI sample limits (prevent GB downloads)
  CI_SAMPLE_LIMIT: 1000
  SBIR_ETL__EXTRACTION__SAMPLE_LIMIT: 1000
  SBIR_ETL__EXTRACTION__SBIR__USE_S3_FIRST: "false"
  SBIR_ETL__EXTRACTION__SAM_GOV__USE_S3_FIRST: "false"
```

**Benefit:** Prevents accidental GB downloads in CI

### 3. Add ML Dependency Caching

**File:** `.github/workflows/run-ml-jobs.yml`

**Add before "Install ML dependencies" step:**
```yaml
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

**Savings:** 5-10 min per ML job run

## Medium Priority (1 hour implementation)

### 4. Add Data Refresh Validation Job

**File:** `.github/workflows/ci.yml`

**Add new job:**
```yaml
data-refresh-validation:
  name: Validate Data Refresh Logic
  needs: [detect-changes]
  if: |
    needs.detect-changes.outputs.docs-only != 'true' &&
    github.event_name == 'push'
  runs-on: ubuntu-latest
  timeout-minutes: 10
  steps:
    - uses: actions/checkout@v6

    - name: Setup Python and UV
      uses: ./.github/actions/setup-python-uv
      with:
        python-version: ${{ env.PYTHON_VERSION }}
        install-dev-deps: "true"
        cache-venv: "true"

    - name: Validate data refresh logic
      env:
        CI_MODE: "true"
        SBIR_ETL__EXTRACTION__SAMPLE_LIMIT: 100
      run: |
        # Test that data refresh code works without downloading GBs
        uv run pytest tests/unit/extractors/ -v -k "sbir or usaspending"
```

**Benefit:** Catch data refresh bugs in CI without GB downloads

### 5. Add ML Unit Tests Job

**File:** `.github/workflows/ci.yml`

**Add new job:**
```yaml
ml-unit-tests:
  name: ML Unit Tests
  needs: [detect-changes]
  if: |
    needs.detect-changes.outputs.docs-only != 'true' &&
    needs.detect-changes.outputs.cet == 'true'
  runs-on: ubuntu-latest
  timeout-minutes: 15
  steps:
    - uses: actions/checkout@v6

    - name: Setup Python and UV
      uses: ./.github/actions/setup-python-uv
      with:
        python-version: ${{ env.PYTHON_VERSION }}
        install-dev-deps: "true"
        cache-venv: "true"

    - name: Run ML unit tests
      run: |
        # Fast tests with mocked data
        uv run pytest tests/unit/ml/ -v --maxfail=3
```

**Benefit:** Fast feedback for ML changes (15 min vs 3 hours)

## Expected Results

| Change | Time Saved | Effort | Risk |
|--------|------------|--------|------|
| Remove ML schedule | 12 hours/month | 1 min | None |
| Add sample limits | Prevents issues | 2 min | None |
| Cache ML deps | 5-10 min/run | 5 min | None |
| Data refresh validation | Catch bugs early | 20 min | Low |
| ML unit tests | Fast feedback | 30 min | Low |

**Total savings:** ~12-15 hours/month
**Total implementation:** ~1 hour

## Implementation Script

```bash
# 1. Remove ML schedule
sed -i '' '/schedule:/,/cron:/d' .github/workflows/run-ml-jobs.yml

# 2. Add sample limits to ci.yml env section
# (Manual edit - add to env: section)

# 3. Add ML caching to run-ml-jobs.yml
# (Manual edit - add cache step)

# 4. Commit changes
git add .github/workflows/
git commit -m "perf: optimize CI for data/ML workflows

- Remove ML weekly schedule (saves 12 hours/month)
- Add sample size limits to prevent GB downloads in CI
- Add ML dependency caching (saves 5-10 min/run)
- Add data refresh validation job
- Add ML unit tests job

Total savings: ~12-15 hours/month"
```

## Monitoring

After implementation:
1. **ML schedule removed**: Verify no weekly runs
2. **Sample limits working**: Check CI doesn't download GBs
3. **Cache hit rate**: Should be >80% for ML deps
4. **Validation jobs**: Should complete in <15 min

## Next Steps

1. Implement quick wins (30 min)
2. Monitor for 1 week
3. Implement medium priority if needed
4. Consider advanced optimizations (model caching, benchmarks)
