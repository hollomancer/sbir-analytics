# EDGAR Type-Specific Event Dates — Requirements

> **Lifecycle status:** Maintenance
> **Spec-file progress:** Not yet started
> Anchors inventory questions **F1–F2** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `pipelines`

**Research question anchor:** F1 M&A exit timing and F2 SBIR↔M&A event coverage
**Answers for:** pipeline engineers maintaining SEC-derived capital-event inputs
**RQ complexity tier:** Descriptive / Relational downstream; this spec preserves event records

---

## Done when

EDGAR inbound-mention enrichment persists each retained filing hit with its own accession, form,
filer, filing date, and mention type, and every profile-level "latest" date is derived for a named
type rather than paired with an all-time union of unrelated types.

---

## Background

The enricher already creates dated `EdgarMAEvent` objects, but profile serialization deduplicates
to the latest event per filer, stores only the union of `mention_types`, and stores one latest date
across every type. Downstream data can therefore say that a profile has an acquisition-related type
and a recent mention, but cannot establish that the acquisition-related mention itself was recent.

## Requirements

### Requirement 1 — Preserve event-grain records

**User story:** As a pipeline engineer, I want each retained EDGAR hit persisted at filing grain,
so aggregation cannot destroy the relationship between event type and date.

#### Acceptance Criteria

1. EACH event record SHALL preserve target company key, filer CIK/name, accession number, form,
   filing date, mention type, and existing classification metadata.
2. Deduplication SHALL use a documented filing/event identity and SHALL NOT discard older distinct
   accessions merely because the filer is the same.
3. Conflicting records with the same canonical event identity SHALL fail or be quarantined with an
   explicit conflict reason.

### Requirement 2 — Type-specific summaries

**User story:** As a downstream consumer, I want dates summarized within event type, so an unrelated
later filing cannot make an older acquisition signal appear recent.

#### Acceptance Criteria

1. Profile summaries SHALL expose latest dates by mention type or derive them from the event table.
2. A generic latest-any-mention date SHALL be named accordingly and SHALL NOT serve as an
   acquisition-event date.
3. Counts, filers, and dates for a type SHALL be computed from the same filtered event rows.

### Requirement 3 — Lineage and migration

**User story:** As a reviewer, I want profile summaries traceable to filings, so every reported date
can be audited against the source event.

#### Acceptance Criteria

1. Event outputs SHALL be provenance-bound to the query cut and retain accession identifiers.
2. Profile outputs SHALL record the event-output fingerprint used for aggregation.
3. Legacy profiles lacking type-specific dates SHALL be treated as incapable of dated type claims,
   not backfilled from `latest_mention_date`.

## Out of scope

- Validating that a classified mention represents a completed acquisition.
- Changing mention-type classification rules or confidence thresholds.
- Adding a new search backend or continuous EDGAR orchestration.
- Computing M&A rates, causal effects, or citable findings.

## Dependencies

- `EdgarMAEvent` filing-grain model — EXISTS
- EDGAR inbound-mention search and classification — EXISTS
- Company-level EDGAR profile output — EXISTS, LOSSY SUMMARY
