# Completion Record — award-export-semantics

**Status**: Complete. All four tasks are checked.
**Archived**: 2026-11-26

Evidence:

- `sbir_etl/models/award_export.py` defines `EXPORT_ROW_V1`,
  `AWARD_YEAR_FIELD_V1`, and the pinned source metadata model.
- The SBA annual-report study declares both definitions through the
  `award-export-source-pipeline` reader.

This spec owns no open work. The storage migration plan and the migration of
other award-export readers (issue #771) stay with the active
[`award-export-source-pipeline`](../../../award-export-source-pipeline/requirements.md)
spec. A new grain, fiscal-year basis, or award identity needs a new scope
review against `docs/research-questions.md`.
