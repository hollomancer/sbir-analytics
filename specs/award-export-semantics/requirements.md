# Award Export Semantics — Requirements

> **Lifecycle status:** Active
> **Spec-file progress:** Ready for implementation
> Anchors inventory question **D1** in
> [docs/research-questions.md](../../docs/research-questions.md#d1-descriptive-tier-1).

**Target epistemic tier:** `primitives`

**Research question anchor:** D1 — award totals by state, agency, and phase
**Answers for:** pipeline engineers and SBIR program managers
**RQ complexity tier:** Descriptive

## Done when

An analyst can name the source row grain and fiscal-year field used by the SBA
annual-report comparison. Code can load and validate the same declarations
without copying strings or inventing award identity.

## Background

The repository reads the SBIR.gov award export through several paths. Those
paths make different choices about row collapse, fiscal-year fields, and
provenance. The first public study needs small, versioned declarations before
one reader can be promoted.

## Requirements

### Requirement 1 — Source-faithful grain

**User story:** As a pipeline engineer, I want a versioned raw-row grain, so
that a study cannot silently inherit a deduplication rule from another loader.

#### Acceptance Criteria

1. THE primitive SHALL define `EXPORT_ROW_V1` as one physical data record after
   CSV parsing and before deduplication, canonical-ID construction, or grouping.
2. THE primitive SHALL state that `EXPORT_ROW_V1` is not an award identity.
3. THE primitive SHALL not define an unused contract-and-phase grain.

### Requirement 2 — Study-required fiscal-year basis

**User story:** As an SBIR program manager, I want the fiscal-year basis named,
so that reported counts have one inspectable time convention.

#### Acceptance Criteria

1. THE primitive SHALL define `AWARD_YEAR_FIELD_V1` as the integer value of the
   export's `Award Year` field.
2. WHEN a nonblank `Award Year` value is not an integer, THE primitive SHALL
   fail with the row location and value.
3. THE primitive SHALL not fall back to proposal, notification, or end dates.
4. THE primitive SHALL not encode empirical comparison findings in its
   documentation.

### Requirement 3 — Pinned source metadata

**User story:** As a pipeline engineer, I want one validated metadata model, so
that source identity is checked before analysis begins.

#### Acceptance Criteria

1. THE model SHALL require source URL, retrieval time, SHA-256, byte count, row
   count, ordered-schema fingerprint, retrieval tool and version, operator or
   automation identity, and access or license note.
2. THE model SHALL allow an upstream publication or export date to be absent
   only when the metadata records that the upstream date is unknown.
3. THE model SHALL reject an invalid digest, negative size, negative row count,
   or timezone-free retrieval time.
4. THE model SHALL serialize deterministically. It SHALL not add an implicit
   current time.

## Dependencies

- `sbir_etl.utils.data.file_io.file_sha256` — EXISTS
- Exact SBIR.gov ordered schema in the Phase II source materializer — EXISTS
- `award-export-source-pipeline` — consumes this contract

## Out of scope

- Moving or symlinking existing source files.
- Defining a canonical award identity.
- Migrating readers other than the SBA annual-report study.
- Study comparison bands, verdicts, or public claim language.
