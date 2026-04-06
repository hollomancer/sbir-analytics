# PR 202 Follow-up Fixes

- [x] Review previously identified issue and likely Copilot review fallout from workflow consolidation
- [x] Update code/docs that still reference deleted `run-ml-jobs.yml`
- [x] Update deployment docs to use consolidated `etl-pipeline.yml` dispatch inputs
- [x] Verify no stale workflow references remain

## Review Notes

Implemented follow-up fixes for PR #202 consolidation:
- Updated `definitions_ml.py` docstring to point to `.github/workflows/etl-pipeline.yml`.
- Updated deployment docs to use ETL Pipeline workflow, correct dispatch input names, and current schedule/env examples.
- Updated AWS Batch deployment doc to use ETL Pipeline dispatch instructions.

---

# Weekly SBIR Report DRY Re-evaluation — Phase 1

- [x] Create shared reporting helper utilities for script-level reporting concerns
- [x] Refactor `run_sbir_ingestion_checks.py` to use shared helpers
- [x] Refactor `run_neo4j_sbir_load.py` to use shared helpers
- [x] Refactor `awards_refresh_validation.py` markdown summary assembly to shared helpers
- [x] Run targeted validation checks and document results

## Review Notes

Completed Phase 1 implementation with no runtime behavior changes to pipeline semantics:
- Added shared helpers in `sbir_etl/utils/reporting/script_helpers.py` for:
  - Dagster metadata serialization
  - Markdown metric-table rendering
  - GitHub Actions output-file writing
- Updated three SBIR scripts to consume shared helpers and remove duplicated utility logic.
