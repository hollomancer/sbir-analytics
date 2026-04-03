# PR #202 Review (Resolved Follow-ups)

## Previously Identified Issue

### Stale workflow pointer in ML definitions docstring
- **Issue:** `packages/sbir-analytics/sbir_analytics/definitions_ml.py` referenced deleted workflow `.github/workflows/run-ml-jobs.yml`.
- **Fix applied:** Updated reference to consolidated `.github/workflows/etl-pipeline.yml` workflow_dispatch entrypoint.

## Additional Follow-ups Implemented
- Updated `docs/deployment/github-actions-ml.md` to use consolidated ETL workflow name, input keys (`job`, `environment`), schedule example (`0 10 * * 1`), and current environment variable examples.
- Updated `docs/deployment/aws-batch-analysis-jobs.md` to reference running fiscal analysis from **ETL Pipeline** workflow dispatch.

## Status
- Follow-up issues identified during PR #202 review are now addressed in this branch.
