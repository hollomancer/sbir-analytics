# GitHub Actions Workflow Cleanup

## ✅ COMPLETED

**Previous state:** 14 workflows
**Current state:** 7 workflows (50% reduction)
**Date completed:** 2025-11-29

## Actions Completed

### ✅ 1. Removed Deprecated Workflows

Removed 5 deprecated workflows:
- ✅ `docker-cache.yml` → merged into `ci.yml`
- ✅ `static-analysis.yml` → merged into `ci.yml`
- ✅ `usaspending-database-download.yml` → merged into `data-refresh.yml`
- ✅ `uspto-data-refresh.yml` → merged into `data-refresh.yml`
- ✅ `weekly-award-data-refresh.yml` → merged into `data-refresh.yml`

### ✅ 2. Consolidated Weekly Tests

Merged `weekly.yml` into `nightly.yml`:
- Added weekly schedule (Sunday 2 AM UTC)
- Added `test_level` input parameter (nightly/weekly)
- Moved comprehensive-tests, real-data-validation, performance-profiling jobs
- Jobs run conditionally based on schedule or input

### ✅ 3. Consolidated Developer Experience

Merged `developer-experience.yml` into `nightly.yml`:
- Added verify-local-workflow job
- Added verify-ml-workflow job
- Runs as part of nightly testing suite

## Final Workflow Structure (7 workflows)

| Workflow | Purpose | Trigger | Jobs |
|----------|---------|---------|------|
| `ci.yml` | Main CI pipeline | PR, push to main/develop | 11 jobs (lint, test, container, performance, etc.) |
| `deploy.yml` | Dagster Cloud deployment | Push to main, PRs | 2 jobs (default deploy, docker deploy) |
| `data-refresh.yml` | Unified data refresh | Scheduled + manual | 5 jobs (SBIR, USAspending, USPTO refresh) |
| `lambda-deploy.yml` | AWS Lambda deployment | Push to main (lambda paths) | 3 jobs (detect changes, build layer, deploy CDK) |
| `nightly.yml` | Extended testing & security | Nightly 3 AM + Weekly Sunday 2 AM | 13 jobs (tests, security, developer verification, weekly comprehensive) |
| `build-r-base.yml` | R base image builder | Weekly Sunday 2 AM | 1 job (build and push R image) |
| `run-ml-jobs.yml` | On-demand ML jobs | Manual only | 1 job (CET/fiscal jobs) |

## Benefits Achieved

1. ✅ **Reduced complexity:** 14 → 7 workflows (50% reduction)
2. ✅ **Easier maintenance:** Fewer files to update and monitor
3. ✅ **Better organization:** Related functionality grouped together
4. ✅ **Reduced CI minutes:** Eliminated duplicate deprecated workflows
5. ✅ **Clearer purpose:** Each workflow has a distinct, well-defined role
6. ✅ **Unified testing:** Nightly and weekly tests in single workflow with conditional execution

## Workflow Responsibilities Matrix

| Workflow | CI/CD | Testing | Deployment | Data Refresh | Infrastructure |
|----------|-------|---------|------------|--------------|----------------|
| ci.yml | ✅ | ✅ | - | - | - |
| deploy.yml | - | - | ✅ | - | - |
| data-refresh.yml | - | - | - | ✅ | - |
| lambda-deploy.yml | - | - | ✅ | - | ✅ |
| nightly.yml | - | ✅ | - | - | - |
| build-r-base.yml | - | - | - | - | ✅ |
| run-ml-jobs.yml | - | - | - | - | - |
