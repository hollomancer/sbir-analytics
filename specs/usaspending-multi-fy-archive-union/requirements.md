# USAspending Multi-FY Contract Archive Union — Requirements

> **Lifecycle status:** Maintenance
> **Spec-file progress:** Not yet started
> Anchors inventory questions **B2–B3** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `pipelines`

**Research question anchor:** B2 award-to-contract transition and B3 Phase II→III latency
**Answers for:** pipeline engineers maintaining transition inputs
**RQ complexity tier:** Relational / Inferential downstream; this spec only moves source data

---

## Done when

Given an explicit set of federal fiscal years, the transition source layer deterministically
materializes the union of the latest USAspending `Contracts_Full` revision for every requested
year, binds every archive to the output manifest, and refuses incomplete or conflicting cuts.

---

## Background

`find_latest_local_contract_archive` currently returns one archive by its global update date.
When FY2025 and FY2026 archives coexist, the transition asset therefore reads only one fiscal
partition; a later download can silently replace rather than extend the materialized time span.
Multi-year transition and latency consumers need an explicit, reproducible fiscal partition set.

## Requirements

### Requirement 1 — Explicit archive-set resolution

**User story:** As a pipeline engineer, I want archive discovery to resolve one declared revision
per requested fiscal year, so that a rerun cannot silently change the temporal population.

#### Acceptance Criteria

1. WHEN fiscal years are requested, THE System SHALL select the latest valid archive revision
   independently within each requested year.
2. IF any requested year is absent or has an unparseable archive name, THEN THE System SHALL fail
   before extraction and identify the missing or invalid partition.
3. THE System SHALL return archives in deterministic fiscal-year and filename order.

### Requirement 2 — Transaction-faithful union

**User story:** As a transition consumer, I want all requested fiscal partitions assembled at the
canonical transaction grain, so that counts and first-event dates use the complete declared cut.

#### Acceptance Criteria

1. THE System SHALL extract every selected archive through the same schema-verified projection.
2. WHEN a transaction identifier occurs in more than one partition, THE System SHALL deduplicate
   byte-equivalent records and fail closed on conflicting records.
3. THE System SHALL expose per-year scanned, matched, and emitted row counts in quality checks.

### Requirement 3 — Set-level provenance

**User story:** As a reviewer, I want the output bound to every selected archive, so that the
declared multi-year cut can be independently reproduced.

#### Acceptance Criteria

1. THE adjacent checks manifest SHALL record fiscal year, filename, size, SHA-256, and source
   revision date for every selected archive.
2. Cache reuse SHALL require the ordered archive-set fingerprint, vendor-frame fingerprint, and
   extractor contract version to match.
3. A one-year request SHALL remain supported as a one-element archive set.

## Out of scope

- Downloading every historical USAspending partition automatically.
- Agency- or study-specific filtering beyond the existing vendor frame.
- Transition matching, classification, or statistical estimation.

## Dependencies

- `AwardArchiveContractExtractor` — EXISTS
- `raw_contracts` transition asset and source-provenance checks — EXISTS
- Local USAspending annual contract archives — OPERATOR-PROVIDED
