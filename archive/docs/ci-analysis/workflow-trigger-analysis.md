# Workflow Trigger Analysis - On-Demand Candidates

## Current Trigger Summary

| Workflow | Current Triggers | Purpose | CI Minutes Impact |
|----------|-----------------|---------|-------------------|
| `ci.yml` | PR, push to main/develop, manual | Core CI pipeline | HIGH (every PR/push) |
| `deploy.yml` | Push to main, PRs | Dagster Cloud deployment | MEDIUM (every PR/push to main) |
| `data-refresh.yml` | Scheduled (weekly/monthly), manual | Data source updates | LOW (scheduled only) |
| `lambda-deploy.yml` | Push to main (lambda paths), manual | AWS Lambda deployment | LOW (path-filtered) |
| `nightly.yml` | Scheduled (nightly + weekly), manual | Extended testing | MEDIUM (daily + weekly) |
| `build-r-base.yml` | Scheduled (weekly), push to main (Dockerfile.r-base), manual | R base image | LOW (weekly + rare pushes) |
| `run-ml-jobs.yml` | Manual only | ML jobs | NONE (manual only) |

## Recommendations

### ✅ KEEP AS-IS (Core CI/CD)

#### 1. `ci.yml` - Main CI Pipeline
**Current:** PR, push to main/develop, manual
**Recommendation:** ✅ KEEP - This is core CI, must run on every PR/push
**Reason:** Fast feedback loop essential for development

#### 2. `deploy.yml` - Dagster Cloud Deployment
**Current:** Push to main, PRs
**Recommendation:** ✅ KEEP - Automatic deployment is valuable
**Reason:** Enables continuous deployment and PR preview environments

#### 3. `data-refresh.yml` - Data Source Updates
**Current:** Scheduled (weekly/monthly), manual
**Recommendation:** ✅ KEEP - Already optimal (scheduled + manual)
**Reason:** Automated data freshness is core value

### 🔄 CONSIDER CHANGING TO ON-DEMAND

#### 4. `nightly.yml` - Extended Testing
**Current:** Scheduled (nightly 3 AM + weekly Sunday 2 AM), manual
**Recommendation:** 🔄 CHANGE nightly schedule to on-demand, KEEP weekly schedule
**Reason:**
- Nightly tests duplicate much of what CI already covers
- Weekly comprehensive tests are valuable for catching regressions
- Nightly jobs (security scans, developer verification) could run weekly instead
- Saves ~30 CI minutes per day = ~900 minutes/month

**Proposed Change:**
```yaml
on:
  schedule:
    - cron: "0 2 * * 0"   # Weekly Sunday 2 AM only
  workflow_dispatch:
    inputs:
      test_level:
        description: 'Test level: "standard" or "comprehensive"'
        default: standard
```

**Impact:**
- Nightly tests still available via manual trigger
- Weekly comprehensive tests still run automatically
- Reduces CI minutes by ~30/day
- Developers can still trigger manually when needed

#### 5. `build-r-base.yml` - R Base Image Builder
**Current:** Scheduled (weekly Sunday 2 AM), push to main (Dockerfile.r-base), manual
**Recommendation:** 🔄 CHANGE to on-demand only
**Reason:**
- R dependencies rarely change
- Weekly rebuilds are wasteful
- Push trigger on Dockerfile.r-base is sufficient
- Can manually trigger when R packages need updates

**Proposed Change:**
```yaml
on:
  push:
    branches:
      - main
    paths:
      - 'Dockerfile.r-base'
      - '.github/workflows/build-r-base.yml'
  workflow_dispatch:
    inputs:
      r_version:
        description: 'R version to use (default: 4.3.2)'
        default: '4.3.2'
```

**Impact:**
- Still rebuilds automatically when Dockerfile.r-base changes
- Removes unnecessary weekly rebuilds
- Saves ~10-15 CI minutes per week = ~50-60 minutes/month

### ✅ ALREADY OPTIMAL

#### 6. `lambda-deploy.yml` - AWS Lambda Deployment
**Current:** Push to main (lambda paths), manual
**Recommendation:** ✅ KEEP - Already optimal with path filtering
**Reason:** Only runs when Lambda code changes

#### 7. `run-ml-jobs.yml` - ML Jobs
**Current:** Manual only
**Recommendation:** ✅ KEEP - Already on-demand only
**Reason:** ML jobs are expensive and should be intentional

## Summary of Recommended Changes

### Change to On-Demand:

1. **`nightly.yml`** - Remove nightly schedule, keep weekly
   - Savings: ~900 CI minutes/month
   - Risk: Low (tests still run weekly + manual)

2. **`build-r-base.yml`** - Remove weekly schedule, keep push trigger
   - Savings: ~50-60 CI minutes/month
   - Risk: Very low (R dependencies rarely change)

### Total Potential Savings:
- **~950-960 CI minutes per month**
- **~11,400-11,520 CI minutes per year**

## Implementation Priority

### High Priority (Immediate)
1. Remove weekly schedule from `build-r-base.yml`
   - Low risk, immediate savings
   - R base image rarely needs updates

### Medium Priority (After monitoring)
2. Change `nightly.yml` to weekly-only schedule
   - Monitor CI coverage for 1-2 weeks first
   - Ensure weekly tests catch issues adequately
   - Keep manual trigger for on-demand testing

## Rollback Plan

If issues arise, simply restore the schedule:
```bash
# Restore nightly schedule
git checkout HEAD~1 -- .github/workflows/nightly.yml

# Restore weekly R base build
git checkout HEAD~1 -- .github/workflows/build-r-base.yml
```

## Monitoring After Changes

After implementing changes, monitor:
1. Issue detection rate (are we catching bugs later?)
2. Developer feedback (do they miss nightly tests?)
3. CI minutes usage (confirm savings)
4. Manual trigger frequency (how often do devs need to run manually?)

If weekly tests prove insufficient, can add back nightly schedule.
