# CI Deduplication & Further Improvement Opportunities

**Date:** 2025-11-29
**Status:** After recent optimizations (parallel tests, docs-only skip)

## Current State

**Workflows:** 8 files (93.6 KB total)
- `ci.yml` - 45 KB (largest, most complex)
- `weekly.yml` - 9.0 KB
- `lambda-deploy.yml` - 8.0 KB
- `data-refresh.yml` - 7.7 KB
- `deploy.yml` - 6.7 KB
- `nightly.yml` - 5.1 KB
- `run-ml-jobs.yml` - 4.6 KB
- `build-r-base.yml` - 3.5 KB

## Deduplication Opportunities

### 🔄 High Priority - Action Version Inconsistencies

#### 1. Standardize checkout action versions
**Current:** Mix of `@v4` and `@v6`
- 21 uses of `actions/checkout@v6`
- 2 uses of `actions/checkout@v4` (outdated)

**Fix:** Update all to `@v6`
```bash
find .github/workflows -name "*.yml" -exec sed -i '' 's/actions\/checkout@v4/actions\/checkout@v6/g' {} \;
```

**Impact:** Consistency, latest features
**Risk:** None (v6 is backward compatible)

#### 2. Standardize artifact upload versions
**Current:** Mix of `@v4` and `@v5`
- 4 uses of `actions/upload-artifact@v5`
- 1 use of `actions/upload-artifact@v4`

**Fix:** Update all to `@v5`
```bash
find .github/workflows -name "*.yml" -exec sed -i '' 's/actions\/upload-artifact@v4/actions\/upload-artifact@v5/g' {} \;
```

**Impact:** Consistency, better performance
**Risk:** None (v5 is backward compatible)

### 🔧 Medium Priority - Repeated Patterns

#### 3. Consolidate Python Setup Pattern
**Current:** 19 instances of setup-python-uv across workflows
**Pattern:**
```yaml
- name: Setup Python and UV
  uses: ./.github/actions/setup-python-uv
  with:
    python-version: ${{ env.PYTHON_VERSION }}
    install-dev-deps: "true"
    cache-venv: "true"
```

**Observation:** Already using composite action - good!
**Opportunity:** Ensure consistent parameters across all uses

**Recommendation:** Create a "standard setup" composite action that includes:
- Checkout
- Setup Python and UV with standard params
- Common environment setup

#### 4. Repeated Conditional Logic
**Current:** Same `if` conditions repeated across multiple jobs

**Pattern 1 - Docs-only skip:**
```yaml
if: |
  github.event_name == 'push' ||
  github.event_name == 'workflow_dispatch' ||
  (github.event_name == 'pull_request' && needs.detect-changes.outputs.docs-only != 'true')
```
**Used in:** lint, type-check, verify-setup-script, test, container-build-test, performance-check, cet-tests, transition-mvp

**Solution:** Use YAML anchors (not supported in GitHub Actions) OR accept duplication as necessary for clarity

**Alternative:** Use reusable workflows for common job patterns

#### 5. Repeated Timeout Values
**Current:** Many jobs use same timeouts
- 10 minutes: lint, type-check, verify-setup-script, test (per suite)
- 20 minutes: container-build-test, performance-check, cet-tests

**Solution:** Use workflow-level defaults
```yaml
defaults:
  run:
    timeout-minutes: 10
```

**Impact:** Consistency, easier maintenance
**Risk:** None (can override per-job)

### 💡 Low Priority - Workflow Consolidation

#### 6. Consider Reusable Workflows
**Current:** Each workflow is standalone
**Opportunity:** Extract common patterns into reusable workflows

**Candidates for reusable workflows:**
- Python test suite (used in ci.yml, weekly.yml, nightly.yml)
- Docker build and test (used in ci.yml, deploy.yml)
- AWS credential setup (used in multiple workflows)

**Example reusable workflow:**
```yaml
# .github/workflows/reusable-python-tests.yml
on:
  workflow_call:
    inputs:
      test-suite:
        required: true
        type: string
      python-version:
        required: false
        type: string
        default: "3.11"
```

**Impact:** Reduce duplication, easier maintenance
**Risk:** Medium (adds complexity, harder to debug)

#### 7. Consolidate Similar Jobs
**Current:** Multiple jobs with similar structure

**Example - CET tests:**
- `cet-tests` in ci.yml (smoke only on PR)
- `cet-dev-e2e` in ci.yml (full pipeline on push)
- Could be single job with matrix

**Impact:** Simpler workflow, fewer jobs
**Risk:** Low (already using matrix in other jobs)

### 📊 Metrics & Monitoring

#### 8. Add Workflow Timing Metrics
**Current:** No centralized timing metrics
**Opportunity:** Track job durations over time

**Solution:** Add timing step to ci-summary
```yaml
- name: Record workflow metrics
  run: |
    echo "workflow_duration=${{ github.event.workflow_run.duration }}" >> metrics.txt
    # Upload to monitoring system
```

**Impact:** Better visibility into CI performance
**Risk:** None

#### 9. Consolidate Artifact Retention
**Current:** Inconsistent retention days
- Some use `${{ env.DEFAULT_RETENTION_DAYS }}` (7 days)
- Some use `${{ env.CET_ARTIFACT_RETENTION_DAYS }}` (14 days)
- Some hardcode values

**Solution:** Standardize retention policy
```yaml
env:
  DEFAULT_RETENTION_DAYS: 7
  IMPORTANT_RETENTION_DAYS: 14  # For coverage, benchmarks
  LONG_RETENTION_DAYS: 30       # For releases
```

**Impact:** Consistency, cost optimization
**Risk:** None

## Implementation Priority

### Phase 1: Quick Fixes (15 min)
1. ✅ Standardize checkout to @v6
2. ✅ Standardize upload-artifact to @v5
3. ✅ Add workflow-level timeout defaults

### Phase 2: Pattern Improvements (1 hour)
4. Audit and standardize setup-python-uv parameters
5. Consolidate artifact retention policy
6. Add workflow timing metrics

### Phase 3: Structural Changes (2-4 hours)
7. Extract reusable workflows for common patterns
8. Consolidate similar jobs with matrix strategies
9. Document workflow architecture

## Recommended Actions (Immediate)

### 1. Version Standardization Script
```bash
#!/bin/bash
# Standardize action versions across all workflows

cd .github/workflows

# Update checkout to v6
sed -i '' 's/actions\/checkout@v4/actions\/checkout@v6/g' *.yml

# Update upload-artifact to v5
sed -i '' 's/actions\/upload-artifact@v4/actions\/upload-artifact@v5/g' *.yml

# Update download-artifact to v6
sed -i '' 's/actions\/download-artifact@v4/actions\/download-artifact@v6/g' *.yml

# Update setup-python to v6
sed -i '' 's/actions\/setup-python@v5/actions\/setup-python@v6/g' *.yml

# Update setup-node to v6
sed -i '' 's/actions\/setup-node@v4/actions\/setup-node@v6/g' *.yml

echo "✅ Action versions standardized"
```

### 2. Add Workflow Defaults to ci.yml
```yaml
defaults:
  run:
    shell: bash
    timeout-minutes: 10  # Default for most jobs

jobs:
  # Jobs inherit default timeout unless overridden
  long-running-job:
    timeout-minutes: 30  # Override default
```

### 3. Standardize Artifact Retention
```yaml
env:
  # Artifact retention policy
  DEFAULT_RETENTION_DAYS: 7      # Standard artifacts
  COVERAGE_RETENTION_DAYS: 14    # Coverage reports
  BENCHMARK_RETENTION_DAYS: 30   # Performance baselines
```

## Expected Benefits

| Change | Time Saved | Maintenance Benefit | Risk |
|--------|------------|---------------------|------|
| Version standardization | 0 min | High (consistency) | None |
| Workflow defaults | 0 min | Medium (less duplication) | None |
| Artifact retention policy | 0 min | Medium (cost optimization) | None |
| Reusable workflows | 0 min | High (DRY principle) | Medium |
| Timing metrics | 0 min | High (visibility) | None |

**Total implementation time:** 15 min (Phase 1) to 4 hours (all phases)
**Maintenance benefit:** High (easier to update, more consistent)

## Monitoring After Changes

Track these metrics:
1. **Workflow consistency:** All actions use latest versions
2. **Artifact storage:** Reduced storage costs with consistent retention
3. **Maintenance time:** Time to update workflows decreases
4. **CI reliability:** Fewer version-related issues

## Notes

- Recent optimizations already achieved 50-60% time reduction
- Focus now is on maintainability and consistency
- Avoid over-engineering - some duplication is acceptable for clarity
- Reusable workflows add complexity - use sparingly
