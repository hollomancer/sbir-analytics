# CI Improvement Opportunities

**Date:** 2025-11-29
**Current State:** 11 jobs in ci.yml, ~15-30 min total runtime

## Current CI Structure

### Job Dependency Graph
```
detect-changes (5 min)
    ├─> lint (10 min) ────────┐
    ├─> type-check (10 min) ──┤
    ├─> verify-setup-script ──┤
    │                         ├─> test (15 min) ─> test-report (5 min)
    ├─> container-build ──────┤
    ├─> performance-check ────┤
    ├─> cet-tests ────────────┤
    └─> transition-mvp ───────┘
                              └─> ci-summary (5 min)
```

### Current Timing
- **Parallel phase 1:** detect-changes (5 min)
- **Parallel phase 2:** lint, type-check, verify-setup-script, container-build, performance-check, cet-tests, transition-mvp (~10-20 min)
- **Sequential phase 3:** test (15 min, waits for lint+type-check)
- **Sequential phase 4:** test-report (5 min)
- **Sequential phase 5:** ci-summary (5 min)

**Total wall time:** ~40-50 minutes (due to sequential dependencies)

## Improvement Opportunities

### 🚀 High Impact (Immediate)

#### 1. Remove Unnecessary Test Dependency on Lint/Type-Check
**Current:** `test` job waits for `lint` and `type-check` to complete
**Problem:** Adds 10 minutes to critical path
**Solution:** Remove lint/type-check from test dependencies

```yaml
test:
  needs: [detect-changes]  # Remove lint, type-check
```

**Impact:** Saves 10 minutes on every CI run
**Risk:** Low - tests can run in parallel with linting

#### 2. Optimize Container Build with Better Caching
**Current:** Container build takes 20 minutes
**Problem:** Not using GitHub Actions cache effectively
**Solution:**
- Use `docker/build-push-action@v5` with layer caching
- Cache to GitHub Container Registry or GitHub Actions cache
- Use `cache-from` and `cache-to` parameters

```yaml
- name: Build and push
  uses: docker/build-push-action@v5
  with:
    context: .
    push: false
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

**Impact:** Reduce container build from 20 min to 5-10 min
**Risk:** Low - standard Docker best practice

#### 3. Run Tests in Parallel with Matrix Strategy
**Current:** Single test job runs all tests sequentially
**Problem:** 15 minutes for all tests
**Solution:** Split tests into parallel matrix jobs

```yaml
test:
  strategy:
    matrix:
      suite: [unit-fast, unit-slow, integration, e2e]
  steps:
    - run: pytest tests/${{ matrix.suite }}
```

**Impact:** Reduce test time from 15 min to 5-8 min (parallel execution)
**Risk:** Medium - need to ensure proper test isolation

### 💡 Medium Impact

#### 4. Skip Redundant Jobs on Docs-Only Changes
**Current:** All jobs run even for docs-only PRs
**Problem:** Wastes CI minutes on documentation changes
**Solution:** Already have `docs-only` detection, use it more

```yaml
test:
  if: needs.detect-changes.outputs.docs-only != 'true'
```

**Impact:** Save ~30 min per docs-only PR
**Risk:** Low - already implemented for some jobs

#### 5. Use Composite Actions for Repeated Setup
**Current:** Each job repeats checkout + setup-python-uv
**Problem:** Duplicated steps across jobs
**Solution:** Already have composite actions, use consistently

**Impact:** Cleaner workflow, slight speed improvement
**Risk:** Low - already partially implemented

#### 6. Optimize Python/UV Caching
**Current:** Each job caches independently
**Problem:** Cache misses, slower setup
**Solution:** Use shared cache key across jobs

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/uv
    key: uv-${{ runner.os }}-${{ hashFiles('uv.lock') }}
```

**Impact:** Reduce setup time by 1-2 min per job
**Risk:** Low - standard caching practice

### 🔧 Low Impact (Nice to Have)

#### 7. Add Job Timeout Defaults
**Current:** Each job specifies timeout
**Problem:** Inconsistent, easy to forget
**Solution:** Use workflow-level defaults

```yaml
defaults:
  run:
    timeout-minutes: 15
```

**Impact:** Consistency, prevent runaway jobs
**Risk:** None

#### 8. Consolidate Artifact Uploads
**Current:** Multiple artifact uploads per job
**Problem:** Slower, more API calls
**Solution:** Upload once per job with multiple paths

**Impact:** Slight speed improvement
**Risk:** None

#### 9. Use Fail-Fast Strategy Selectively
**Current:** `cancel-in-progress: true` at workflow level
**Problem:** Good for PRs, but might want to see all failures on main
**Solution:** Conditional fail-fast

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

**Impact:** Better visibility on main branch failures
**Risk:** None

## Recommended Implementation Order

### Phase 1: Quick Wins (This Week)
1. ✅ Remove lint/type-check dependency from test job
2. ✅ Skip jobs on docs-only changes
3. ✅ Optimize Docker caching with build-push-action

**Expected savings:** 15-20 minutes per CI run

### Phase 2: Parallel Testing (Next Week)
4. Split tests into parallel matrix jobs
5. Optimize Python/UV caching

**Expected savings:** Additional 5-10 minutes per CI run

### Phase 3: Polish (Future)
6. Consolidate artifact uploads
7. Add workflow-level defaults
8. Conditional fail-fast strategy

**Expected savings:** Consistency and maintainability

## Expected Results

| Metric | Current | After Phase 1 | After Phase 2 |
|--------|---------|---------------|---------------|
| **Wall time** | 40-50 min | 25-30 min | 15-20 min |
| **CI minutes** | ~150 min | ~120 min | ~100 min |
| **Docs-only PRs** | 40-50 min | 5 min | 5 min |

## Monitoring

After implementing changes, monitor:
1. Average CI run time (target: <20 min)
2. CI minutes usage (target: <100 min per run)
3. Failure rate (ensure no increase)
4. Developer feedback (faster feedback loop)

## Additional Considerations

### Caching Strategy
- Use `actions/cache@v4` for Python dependencies
- Use `docker/build-push-action@v5` for Docker layers
- Share cache keys across jobs where possible
- Set appropriate cache retention (7 days for dev, 30 days for main)

### Test Optimization
- Run fast unit tests first (fail fast)
- Run slow integration tests in parallel
- Run e2e tests only on main/develop (not every PR)
- Use pytest markers effectively (`-m "not slow"`)

### Resource Optimization
- Use `ubuntu-latest` (currently ubuntu-24.04)
- Consider `ubuntu-latest-4-cores` for parallel test jobs
- Use `continue-on-error` for non-critical jobs
- Set appropriate timeouts to prevent runaway jobs

## Implementation Checklist

- [ ] Remove lint/type-check from test dependencies
- [ ] Add docs-only skip conditions to all jobs
- [ ] Implement Docker layer caching
- [ ] Split tests into parallel matrix
- [ ] Optimize Python/UV caching
- [ ] Consolidate artifact uploads
- [ ] Add workflow-level timeout defaults
- [ ] Implement conditional fail-fast
- [ ] Monitor CI metrics for 1 week
- [ ] Adjust based on results
