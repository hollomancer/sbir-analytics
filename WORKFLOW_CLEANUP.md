# GitHub Actions Workflow Cleanup

## Executive Summary

**Current state:** 14 workflows
**Recommended state:** 7 workflows (50% reduction)

## Quick Actions

### 1. Remove Deprecated Workflows (Immediate)

Run the cleanup script:
```bash
./scripts/cleanup-workflows.sh
```

This removes 5 deprecated workflows that have been consolidated:
- `docker-cache.yml` → merged into `ci.yml`
- `static-analysis.yml` → merged into `ci.yml`
- `usaspending-database-download.yml` → merged into `data-refresh.yml`
- `uspto-data-refresh.yml` → merged into `data-refresh.yml`
- `weekly-award-data-refresh.yml` → merged into `data-refresh.yml`

### 2. Optional Consolidations

**Consolidate `weekly.yml` into `nightly.yml`:**
- Benefit: Single comprehensive testing workflow
- Effort: Medium (requires merging jobs and schedules)

**Consolidate `developer-experience.yml` into `nightly.yml`:**
- Benefit: Unified verification testing
- Effort: Low (simple job addition)

## Final Workflow Structure

After cleanup, 7 workflows remain:

| Workflow | Purpose | Trigger |
|----------|---------|---------|
| `ci.yml` | Main CI pipeline | PR, push to main/develop |
| `deploy.yml` | Dagster Cloud deployment | Push to main, PRs |
| `data-refresh.yml` | Unified data refresh | Scheduled + manual |
| `lambda-deploy.yml` | AWS Lambda deployment | Push to main (lambda paths) |
| `nightly.yml` | Extended testing & security | Nightly 3 AM UTC |
| `build-r-base.yml` | R base image builder | Weekly Sunday 2 AM |
| `run-ml-jobs.yml` | On-demand ML jobs | Manual only |

## Detailed Analysis

See `docs/workflows-analysis.md` for complete analysis including:
- Job-level breakdown of each workflow
- Consolidation recommendations
- Benefits and implementation priority

## Implementation

1. **Immediate (no risk):** Remove deprecated workflows
   ```bash
   ./scripts/cleanup-workflows.sh
   git add .github/workflows/
   git commit -m "chore: remove deprecated GitHub Actions workflows"
   ```

2. **Optional (medium effort):** Consolidate weekly.yml
3. **Optional (low effort):** Consolidate developer-experience.yml
