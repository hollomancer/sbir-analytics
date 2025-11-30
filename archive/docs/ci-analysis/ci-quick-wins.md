# CI Quick Wins - Immediate Improvements

## Summary

**Current CI time:** 40-50 minutes
**Target CI time:** 15-20 minutes
**Potential savings:** 50-60% reduction

## 🚀 Immediate Actions (30 min implementation)

### 1. Remove Unnecessary Test Dependencies

**File:** `.github/workflows/ci.yml`

**Change:**
```yaml
# BEFORE
test:
  needs: [detect-changes, lint, type-check]

# AFTER
test:
  needs: [detect-changes]
```

**Why:** Tests don't need to wait for linting. They can run in parallel.
**Savings:** 10 minutes per run

### 2. Skip Jobs on Docs-Only Changes

**File:** `.github/workflows/ci.yml`

**Add to each job:**
```yaml
if: |
  github.event_name == 'push' ||
  github.event_name == 'workflow_dispatch' ||
  (github.event_name == 'pull_request' && needs.detect-changes.outputs.docs-only != 'true')
```

**Already applied to:** lint, type-check, verify-setup-script
**Need to add to:** container-build-test, performance-check, cet-tests, transition-mvp

**Why:** Documentation changes don't need full CI
**Savings:** 40 minutes on docs-only PRs

### 3. Optimize Docker Build Caching

**File:** `.github/workflows/ci.yml`

**Change container-build-test job:**
```yaml
- name: Build and test
  uses: docker/build-push-action@v5
  with:
    context: .
    push: false
    load: true
    tags: sbir-analytics:test
    cache-from: type=gha
    cache-to: type=gha,mode=max
    build-args: |
      BUILDKIT_INLINE_CACHE=1
```

**Why:** GitHub Actions cache is faster than rebuilding layers
**Savings:** 10-15 minutes per run

### 4. Run Tests in Parallel

**File:** `.github/workflows/ci.yml`

**Change test job to use matrix:**
```yaml
test:
  needs: [detect-changes]
  runs-on: ubuntu-latest
  timeout-minutes: 10  # Reduced from 15
  if: |
    github.event_name == 'push' ||
    github.event_name == 'workflow_dispatch' ||
    (github.event_name == 'pull_request' && needs.detect-changes.outputs.docs-only != 'true')
  strategy:
    fail-fast: false
    matrix:
      suite:
        - name: unit-fast
          path: tests/unit/
          args: '-m "not slow"'
        - name: unit-slow
          path: tests/unit/
          args: '-m "slow"'
        - name: integration
          path: tests/integration/
          args: '-m "not slow"'
  steps:
    - uses: actions/checkout@v4

    - name: Setup Python and UV
      uses: ./.github/actions/setup-python-uv
      with:
        python-version: ${{ env.PYTHON_VERSION }}
        install-dev-deps: "true"
        cache-venv: "true"

    - name: Run ${{ matrix.suite.name }} tests
      run: |
        uv run pytest ${{ matrix.suite.path }} ${{ matrix.suite.args }} \
          --cov=src --cov-report=xml --cov-report=term -v

    - name: Upload coverage
      uses: codecov/codecov-action@v4
      with:
        files: ./coverage.xml
        flags: ${{ matrix.suite.name }}
```

**Why:** Parallel execution is faster than sequential
**Savings:** 5-10 minutes per run

## Expected Results

| Change | Time Saved | Effort | Risk |
|--------|------------|--------|------|
| Remove test dependencies | 10 min | 1 min | Low |
| Skip docs-only jobs | 40 min (docs PRs) | 5 min | Low |
| Docker caching | 10-15 min | 10 min | Low |
| Parallel tests | 5-10 min | 15 min | Medium |

**Total potential savings:** 25-35 minutes per run (50-70% reduction)

## Implementation Script

```bash
# 1. Create feature branch
git checkout -b ci/quick-wins

# 2. Edit .github/workflows/ci.yml
# - Remove lint/type-check from test needs
# - Add docs-only skip to remaining jobs
# - Update container-build-test to use build-push-action with cache
# - Convert test job to matrix strategy

# 3. Test locally
act pull_request  # If you have act installed

# 4. Commit and push
git add .github/workflows/ci.yml
git commit -m "perf: optimize CI with parallel tests and better caching

- Remove unnecessary test dependencies (saves 10 min)
- Skip jobs on docs-only changes (saves 40 min on docs PRs)
- Add Docker layer caching (saves 10-15 min)
- Run tests in parallel matrix (saves 5-10 min)

Total savings: 25-35 minutes per CI run (50-70% reduction)"

git push origin ci/quick-wins

# 5. Create PR and monitor first run
```

## Monitoring After Implementation

Track these metrics for 1 week:

1. **Average CI time:** Should drop from 40-50 min to 15-20 min
2. **Docs-only PR time:** Should drop from 40-50 min to 5 min
3. **Failure rate:** Should remain stable
4. **Cache hit rate:** Should be >80% for Docker builds

## Rollback Plan

If issues arise:
```bash
git revert <commit-hash>
git push origin main
```

All changes are in a single commit for easy rollback.
