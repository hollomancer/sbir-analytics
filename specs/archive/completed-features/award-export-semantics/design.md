# Award Export Semantics — Design

## Boundary

Add a small primitives module under `sbir_etl` for source metadata and study
profiles. It owns names and validation. It does not open files or transform
award records.

The pipelines-tier reader imports these declarations. Study code selects a
profile by its versioned value and records that value in its result sidecar.

## Types

- `AwardGrain.EXPORT_ROW_V1`: one parsed record, with no collapse.
- `FiscalYearBasis.AWARD_YEAR_FIELD_V1`: strict integer parsing of `Award Year`.
- `AwardExportSourceMetadata`: the complete pinned-source description.

The metadata model uses explicit caller-supplied values. A capture command may
collect those values, but the model does not read the clock or filesystem.

## Existing contracts

`sbir_etl.analysis.contracts.SourceManifest` is an analysis-run path and digest
reference. It is too small to establish external source identity. Keep it
unchanged until its existing consumers migrate deliberately.

`sbir_etl.quality.study_manifest` owns study status and frozen-artifact rules.
The new metadata type supplies one source artifact to that contract; it does
not replace the study manifest.

## Failure behavior

Validation fails before any reader returns rows. Error messages name the field
and the rejected value. The implementation never discovers a substitute file.

## Verification

Unit tests cover every required field, deterministic serialization, invalid
digests and counts, timezone handling, and strict fiscal-year parsing.

## Consequences

This work makes source semantics inspectable. It does not make a study
validated or citable.
