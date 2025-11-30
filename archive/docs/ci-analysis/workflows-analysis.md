# GitHub Actions Workflows Analysis

**Date:** 2025-11-29

## Summary

**Total workflows:** 14
**Deprecated (can be removed):** 5
**Active and needed:** 7
**Can be consolidated:** 2

## Workflows Status

### ✅ KEEP - Core CI/CD (7 workflows)

#### 1. `ci.yml` - Main CI Pipeline
**Status:** ✅ KEEP - Primary CI workflow
**Triggers:** PR, push to main/develop, manual
**Jobs:** 11 jobs (lint, type-check, test, container-build, performance-check, cet-tests, transition-mvp, etc.)
**Purpose:** Comprehensive CI with quality checks, tests, and performance validation
**Notes:** Well-structured, consolidated workflow. This is the backbone of CI.

#### 2. `deploy.yml` - Serverless Deployment
**Status:** ✅ KEEP - Production deployment
**Triggers:** Push to main/master, PRs
**Jobs:** 2 jobs (dagster_cloud_default_deploy, dagster_cloud_docker_deploy)
**Purpose:** Dagster Cloud deployment with OIDC authentication
**Notes:** Essential for production deployments.

#### 3. `data-refresh.yml` - Unified Data Refresh
**Status:** ✅ KEEP - Consolidated data refresh
**Triggers:** Scheduled (weekly SBIR, monthly USAspending/USPTO), manual
**Jobs:** 5 jobs (determine-source, refresh-sbir, refresh-usaspending, refresh-uspto, summary)
**Purpose:** Unified workflow for all data source refreshes
**Notes:** This is the replacement for the 3 deprecated data refresh workflows.

#### 4. `lambda-deploy.yml` - Lambda Deployment
**Status:** ✅ KEEP - AWS Lambda deployment
**Triggers:** Push to main (lambda/** paths), manual
**Jobs:** 3 jobs (detect-changes, build-layer, deploy-cdk)
**Purpose:** Deploy Lambda functions and CDK infrastructure
**Notes:** Essential for serverless AWS infrastructure.

#### 5. `nightly.yml` - Nightly Comprehensive Tests
**Status:** ✅ KEEP - Extended testing
**Triggers:** Scheduled (3 AM UTC daily), manual
**Jobs:** 6 jobs (tests, diagnose, attempt_repair, fallback_issue, markdown-lint, security-scan, secret-detection)
**Purpose:** Extended tests, security scans, auto-repair
**Notes:** Provides deeper testing and maintenance automation.

#### 6. `build-r-base.yml` - R Base Image Builder
**Status:** ✅ KEEP - Infrastructure support
**Triggers:** Scheduled (weekly Sunday 2 AM), push to main (Dockerfile.r-base changes), manual
**Jobs:** 1 job (build-and-push)
**Purpose:** Build and cache R base image with stateio for fiscal analysis
**Notes:** Needed for fiscal returns analysis. Reduces build times.

#### 7. `run-ml-jobs.yml` - ML Jobs On-Demand
**Status:** ✅ KEEP - Manual ML execution
**Triggers:** Manual only
**Jobs:** 1 job (run-ml-job)
**Purpose:** Run CET classification or fiscal returns jobs on-demand
**Notes:** Useful for manual ML pipeline execution.

### 🔄 CONSOLIDATE (2 workflows)

#### 8. `weekly.yml` - Weekly Comprehensive Tests
**Status:** 🔄 CONSOLIDATE into `nightly.yml`
**Triggers:** Scheduled (Sunday 2 AM UTC), manual
**Jobs:** 3 jobs (comprehensive-tests, real-data-validation, performance-profiling)
**Purpose:** Weekly extended testing
**Recommendation:** Merge into `nightly.yml` with a weekly schedule option. The jobs overlap significantly with nightly tests.

#### 9. `developer-experience.yml` - Developer Experience Verification
**Status:** 🔄 CONSOLIDATE into `nightly.yml` or `weekly.yml`
**Triggers:** Scheduled (nightly midnight UTC), manual
**Jobs:** 2 jobs (verify-local-workflow, verify-ml-workflow)
**Purpose:** Verify local developer setup works
**Recommendation:** Merge into `nightly.yml` as these are verification tests that fit the nightly testing pattern.

### ❌ REMOVE - Deprecated (5 workflows)

#### 10. `docker-cache.yml` - Docker Cache Builder
**Status:** ❌ REMOVE - Already deprecated
**Note:** Explicitly marked as deprecated. Functionality merged into `ci.yml` container-build-test job.
**Action:** Delete file.

#### 11. `static-analysis.yml` - Static Analysis
**Status:** ❌ REMOVE - Already deprecated
**Note:** Explicitly marked as deprecated. Functionality merged into `ci.yml` (lint, type-check jobs).
**Action:** Delete file.

#### 12. `usaspending-database-download.yml` - USAspending Download
**Status:** ❌ REMOVE - Already deprecated
**Note:** Explicitly marked as deprecated. Functionality moved to `data-refresh.yml`.
**Action:** Delete file.

#### 13. `uspto-data-refresh.yml` - USPTO Data Refresh
**Status:** ❌ REMOVE - Already deprecated
**Note:** Explicitly marked as deprecated. Functionality moved to `data-refresh.yml`.
**Action:** Delete file.

#### 14. `weekly-award-data-refresh.yml` - Weekly SBIR Awards Refresh
**Status:** ❌ REMOVE - Already deprecated
**Note:** Explicitly marked as deprecated. Functionality moved to `data-refresh.yml`.
**Action:** Delete file.

## Recommended Actions

### Immediate Actions (Remove Deprecated)

1. **Delete 5 deprecated workflows:**
   ```bash
   rm .github/workflows/docker-cache.yml
   rm .github/workflows/static-analysis.yml
   rm .github/workflows/usaspending-database-download.yml
   rm .github/workflows/uspto-data-refresh.yml
   rm .github/workflows/weekly-award-data-refresh.yml
   ```

### Consolidation Actions

2. **Merge `weekly.yml` into `nightly.yml`:**
   - Add weekly schedule option to nightly.yml
   - Move comprehensive-tests, real-data-validation, performance-profiling jobs
   - Add input parameter to control test depth (nightly vs weekly)

3. **Merge `developer-experience.yml` into `nightly.yml`:**
   - Add verify-local-workflow and verify-ml-workflow jobs to nightly
   - These fit naturally with nightly testing pattern

### Final State

After consolidation, we'll have **7 workflows:**

1. `ci.yml` - Main CI pipeline (PR, push)
2. `deploy.yml` - Dagster Cloud deployment
3. `data-refresh.yml` - Unified data refresh (SBIR, USAspending, USPTO)
4. `lambda-deploy.yml` - AWS Lambda deployment
5. `nightly.yml` - Extended nightly/weekly tests + developer experience verification
6. `build-r-base.yml` - R base image builder
7. `run-ml-jobs.yml` - On-demand ML jobs

## Benefits of Consolidation

1. **Reduced complexity:** 14 → 7 workflows (50% reduction)
2. **Easier maintenance:** Fewer files to update and monitor
3. **Better organization:** Related functionality grouped together
4. **Reduced CI minutes:** Eliminated duplicate deprecated workflows
5. **Clearer purpose:** Each workflow has a distinct, well-defined role

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

## Implementation Priority

1. **High Priority:** Remove deprecated workflows (immediate, no risk)
2. **Medium Priority:** Consolidate weekly.yml into nightly.yml (reduces redundancy)
3. **Low Priority:** Consolidate developer-experience.yml (nice to have, low impact)
