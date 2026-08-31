# Contract Source-Field Preservation — Requirements

> **Lifecycle status:** Maintenance
> **Spec-file progress:** Not yet started
> Anchors inventory questions **B2–B3** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `pipelines`

**Research question anchor:** B2 award-to-contract transition and B3 unrecorded Phase III work
**Answers for:** pipeline engineers maintaining canonical procurement inputs
**RQ complexity tier:** Relational / Inferential downstream; this spec preserves source semantics

---

## Done when

The canonical contract artifact preserves the distinct USAspending fields required to reconstruct
research coding, awarding and funding organization scope, and award- versus transaction-level
descriptions without consulting the raw archive again.

---

## Background

The narrow award-archive projection currently keeps descriptive `research`, funding top-tier
agency, and `transaction_description`, but drops raw `research_code`, funding sub-agency, and
`prime_award_base_transaction_description`. Downstream consumers therefore cannot distinguish
Element 10Q codes from labels, implement funding-subtier scope, or tell modification text from the
base award narrative. These are source-fidelity defects, not study-specific filters.

## Requirements

### Requirement 1 — Preserve distinct source semantics

**User story:** As a pipeline engineer, I want semantically different source fields represented
separately, so downstream code cannot substitute one field for another accidentally.

#### Acceptance Criteria

1. THE canonical projection SHALL preserve raw `research_code` separately from the descriptive
   `research` label.
2. THE projection SHALL preserve awarding and funding top-tier and sub-tier agency names in
   separate fields.
3. THE projection SHALL preserve transaction description separately from the prime-award base
   transaction description.
4. Missing optional source values SHALL remain null and SHALL NOT be copied from a neighboring
   semantic field.

### Requirement 2 — Canonical schema and compatibility

**User story:** As a downstream consumer, I want stable named fields and an explicit migration,
so existing readers do not silently change meaning.

#### Acceptance Criteria

1. THE `FederalContract` model and Parquet schema SHALL expose unambiguous names for every added
   field or document an intentionally metadata-only field.
2. Existing `research`, `agency`, `sub_agency`, and `description` fields SHALL retain their current
   meaning during a documented compatibility period.
3. THE schema or extraction contract version SHALL change when the new fields are introduced.

### Requirement 3 — Source-fidelity checks

**User story:** As a reviewer, I want field-level provenance and coverage checks, so a future
archive-schema drift cannot recreate the same loss silently.

#### Acceptance Criteria

1. Archive schema verification SHALL require the added raw headers when the configured archive
   contract declares them required.
2. Checks SHALL report non-null coverage for each preserved field and bind the ordered source
   column projection to the output manifest.
3. Fixture tests SHALL prove that research code/label, agency tier, and description grain remain
   distinct after CSV→model→Parquet round-trip.

## Out of scope

- Deciding whether a contract is Phase III.
- Agency-specific inclusion filters or matching rules.
- Narrative-quality thresholds, text scoring, or imputation of missing descriptions.
- Expanding the projection to unrelated USAspending columns without a named consumer.

## Dependencies

- `AwardArchiveContractExtractor` — EXISTS
- `FederalContract` canonical model — EXISTS
- Transition contract-ingestion manifest and coverage checks — EXISTS
