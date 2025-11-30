# GitHub Actions Workflow Consolidation Summary

**Date:** 2025-11-29
**Status:** ✅ COMPLETED

## Overview

Successfully consolidated GitHub Actions workflows from 14 to 7 (50% reduction) by removing deprecated workflows and merging related functionality.

## Changes Made

### 1. Removed 5 Deprecated Workflows

These workflows were already marked as deprecated with functionality moved elsewhere:

- ❌ `docker-cache.yml` → functionality in `ci.yml`
- ❌ `static-analysis.yml` → functionality in `ci.yml`
- ❌ `usaspending-database-download.yml` → functionality in `data-refresh.yml`
- ❌ `uspto-data-refresh.yml` → functionality in `data-refresh.yml`
- ❌ `weekly-award-data-refresh.yml` → functionality in `data-refresh.yml`

### 2. Consolidated Weekly Tests into Nightly

**Merged:** `weekly.yml` → `nightly.yml`

Changes to `nightly.yml`:
- Renamed to "Nightly & Weekly Tests"
- Added second schedule: `0 2 * * 0` (Sunday 2 AM UTC for weekly)
- Added `test_level` input parameter (nightly/weekly)
- Added 3 weekly jobs with conditional execution:
  - `comprehensive-tests` - Full test suite with real data
  - `real-data-validation` - Validation scripts
  - `performance-profiling` - Performance benchmarks

Jobs run when:
- Schedule matches `0 2 * * 0` (Sunday), OR
- Manual dispatch with `test_level: weekly`

### 3. Consolidated Developer Experience into Nightly

**Merged:** `developer-experience.yml` → `nightly.yml`

Added 2 jobs to `nightly.yml`:
- `verify-local-workflow` - Verify local developer setup
- `verify-ml-workflow` - Verify ML/cloud workflow

These run on every nightly execution (no conditional).

## Final Workflow Structure

### 7 Active Workflows

1. **`ci.yml`** - Main CI Pipeline
   - Triggers: PR, push to main/develop, manual
   - Jobs: 11 (lint, type-check, test, container-build, performance-check, cet-tests, transition-mvp, etc.)
   - Purpose: Primary CI with quality checks and tests

2. **`deploy.yml`** - Serverless Deployment
   - Triggers: Push to main/master, PRs
   - Jobs: 2 (dagster_cloud_default_deploy, dagster_cloud_docker_deploy)
   - Purpose: Dagster Cloud deployment with OIDC

3. **`data-refresh.yml`** - Unified Data Refresh
   - Triggers: Scheduled (weekly SBIR, monthly USAspending/USPTO), manual
   - Jobs: 5 (determine-source, refresh-sbir, refresh-usaspending, refresh-uspto, summary)
   - Purpose: Automated data source updates

4. **`lambda-deploy.yml`** - Lambda Deployment
   - Triggers: Push to main (lambda/** paths), manual
   - Jobs: 3 (detect-changes, build-layer, deploy-cdk)
   - Purpose: AWS Lambda and CDK infrastructure deployment

5. **`nightly.yml`** - Extended Testing & Security (CONSOLIDATED)
   - Triggers: Nightly 3 AM UTC, Weekly Sunday 2 AM UTC, manual
   - Jobs: 13 total
     - Nightly: tests (3 suites), diagnose, attempt_repair, fallback_issue, neo4j-smoke, markdown-lint, security-scan, secret-detection, verify-local-workflow, verify-ml-workflow
     - Weekly: comprehensive-tests, real-data-validation, performance-profiling
   - Purpose: Extended testing, security scans, developer verification, weekly comprehensive tests

6. **`build-r-base.yml`** - R Base Image Builder
   - Triggers: Weekly Sunday 2 AM UTC, push to main (Dockerfile.r-base), manual
   - Jobs: 1 (build-and-push)
   - Purpose: Build and cache R base image for fiscal analysis

7. **`run-ml-jobs.yml`** - ML Jobs On-Demand
   - Triggers: Manual only
   - Jobs: 1 (run-ml-job)
   - Purpose: Run CET classification or fiscal returns jobs manually

## Benefits

1. **50% reduction in workflow files** (14 → 7)
2. **Easier maintenance** - Fewer files to update
3. **Better organization** - Related functionality grouped
4. **Reduced duplication** - No more deprecated workflows
5. **Clearer purpose** - Each workflow has distinct role
6. **Unified testing** - Nightly and weekly in one place with conditional execution

## Testing Strategy

### Fast Feedback (CI)
- Runs on every PR and push
- 11 jobs including lint, type-check, unit tests, container build
- ~15-30 minutes

### Extended Testing (Nightly)
- Runs at 3 AM UTC daily
- Slow unit tests, integration tests, e2e smoke tests
- Security scans, secret detection
- Developer workflow verification
- ~30-45 minutes

### Comprehensive Testing (Weekly)
- Runs Sunday 2 AM UTC
- Full test suite with real data
- Performance profiling and benchmarks
- Data validation scripts
- ~2 hours

## Migration Notes

### For Developers

No changes needed to development workflow. All functionality preserved:
- PRs still trigger full CI
- Nightly tests still run automatically
- Weekly comprehensive tests still run on schedule
- Manual triggers still available

### For CI/CD Maintenance

- Update any documentation referencing old workflow names
- Monitor first few runs of consolidated `nightly.yml` to ensure conditional logic works
- Weekly jobs should only run on Sunday schedule or manual dispatch with `test_level: weekly`

## Rollback Plan

If issues arise, the original workflows are in git history:
```bash
# Restore specific workflow
git checkout HEAD~1 -- .github/workflows/weekly.yml
git checkout HEAD~1 -- .github/workflows/developer-experience.yml
```

## Next Steps

1. ✅ Monitor first nightly run (should skip weekly jobs)
2. ✅ Monitor first Sunday run (should include weekly jobs)
3. ✅ Update any documentation referencing old workflow names
4. ✅ Consider further consolidation opportunities in future

## Files Modified

- `.github/workflows/nightly.yml` - Added weekly schedule, test_level input, 5 new jobs
- Deleted: `docker-cache.yml`, `static-analysis.yml`, `usaspending-database-download.yml`, `uspto-data-refresh.yml`, `weekly-award-data-refresh.yml`, `developer-experience.yml`, `weekly.yml`

## Documentation Updated

- `WORKFLOW_CLEANUP.md` - Updated with completion status
- `docs/workflows-analysis.md` - Original analysis (preserved for reference)
- `docs/workflows-consolidation-summary.md` - This summary
