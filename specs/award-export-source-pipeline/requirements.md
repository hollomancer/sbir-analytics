# Award Export Source Pipeline — Requirements

> **Lifecycle status:** Maintenance
> **Spec-file progress:** Complete
> Anchors inventory question **D1** in
> [docs/research-questions.md](../../docs/research-questions.md#d1-descriptive-tier-1).

**Target epistemic tier:** `pipelines`

**Research question anchor:** D1 — award totals by state, agency, and phase
**Answers for:** pipeline engineers and SBIR program managers
**RQ complexity tier:** Descriptive

## Done when

The SBA annual-report study reads one explicitly named SBIR.gov export, checks
its sidecar before use, and produces the same analytical tables as the current
implementation. A missing, changed, or unpinned input stops before analysis.

## Background

The repository already has an exact 42-column reader in the Phase II source
materializer. The SBA study has a separate direct Pandas reader and a smaller
metadata file. This spec refactors the exact reader into a shared path and
migrates one study without changing other consumers.

## Requirements

### Requirement 1 — Exact raw reader

**User story:** As a pipeline engineer, I want one source-faithful reader, so
that consumers begin from the same physical records.

#### Acceptance Criteria

1. THE reader SHALL require the declared 42 columns in their declared order.
2. THE reader SHALL preserve source values, embedded newlines, empty strings,
   and row order without deduplication or normalization.
3. WHEN a record has the wrong field count, THE reader SHALL fail with the CSV
   record number.
4. THE implementation SHALL refactor the existing Phase II exact-reader logic.
   It SHALL not add a competing parser.

### Requirement 2 — Pin before use

**User story:** As an SBIR program manager, I want input identity checked before
calculation, so that a mutable export cannot masquerade as the declared vintage.

#### Acceptance Criteria

1. THE verified-load entry point SHALL require a source sidecar.
2. BEFORE returning rows, THE loader SHALL verify file SHA-256, byte count, raw
   row count, and ordered-schema fingerprint against the sidecar.
3. THE loader SHALL use `sbir_etl.utils.data.file_io.file_sha256` for file
   digests.
4. IF the file, sidecar, or any required field is missing, THEN THE loader SHALL
   fail without searching for another export.
5. IF any verified value differs, THEN THE loader SHALL fail and report the
   expected and observed values.

### Requirement 3 — New-capture vintage policy

**User story:** As a pipeline engineer, I want new exports stored by retrieval
date, so that later captures do not overwrite study inputs.

#### Acceptance Criteria

1. NEW captures SHALL use `data/raw/sbir/award-export/YYYY-MM-DD/`.
2. EACH new capture directory SHALL contain the export and its validated
   source sidecar.
3. CAPTURE code SHALL refuse to overwrite an existing vintage unless the bytes
   and complete sidecar are identical.
4. THIS slice SHALL not move, delete, or symlink existing data.

### Requirement 4 — SBA study migration

**User story:** As an SBIR program manager, I want the current structural
comparison to use the verified loader, so that its source contract is executable.

#### Acceptance Criteria

1. THE study SHALL declare `EXPORT_ROW_V1` and `AWARD_YEAR_FIELD_V1`.
2. THE study view SHALL apply its own jurisdiction selection. The raw reader
   SHALL not apply that policy.
3. FOR the same source bytes and definitions, THE migrated study SHALL produce
   byte-identical analytical CSV and JSON values, aside from approved portable
   provenance-field changes.
4. THE study SHALL record repo-relative source metadata references. It SHALL not
   emit host-specific absolute paths.
5. A focused guard SHALL prevent the SBA study from returning to a direct CSV
   read.

## Dependencies

- `award-export-semantics` — ACTIVE
- Existing Phase II exact source reader — EXISTS
- SBA annual-report structural-comparison study — EXISTS

## Out of scope

- Existing storage migration, symlinks, or live-host changes.
- Migration of Dagster ingestion, `SbirDuckDBExtractor`, or other scripts.
- Canonical award-ID construction and source-edition collapse.
- A generic structural-comparison framework.
- Evidence promotion or public rendering.
