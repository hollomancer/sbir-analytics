# Form D Amendment-Chain Deduplication — Requirements

> **Lifecycle status:** Maintenance
> **Spec-file progress:** Not yet started
> Anchors inventory questions **F1 and F3** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `pipelines`

**Research question anchor:** F1 Form D fundraising profile and F3 disclosed Form D leverage
**Answers for:** pipeline engineers maintaining SEC private-capital inputs
**RQ complexity tier:** Descriptive / Inferential downstream; this spec normalizes filings only

---

## Done when

Form D monetary aggregates use at most one as-of amount from each auditable offering/amendment
chain, retain every source accession for lineage, and exclude unresolved amendment chains from
dollar totals rather than summing potentially cumulative filings.

---

## Background

Current shared aggregators sum `total_amount_sold` across every kept Form D offering row, including
rows marked `is_amendment`. Amendments can restate cumulative offering amounts, so original and
amended filings can be counted more than once. Filing participation remains usable, but shared
capital totals need a chain-aware source contract before supporting leverage calculations.

## Requirements

### Requirement 1 — Preserve filing lineage

**User story:** As a pipeline engineer, I want every filing retained before aggregation, so chain
resolution never destroys source evidence.

#### Acceptance Criteria

1. EACH Form D row SHALL retain issuer CIK, accession number, filing date, first-sale date,
   amendment flag, offering attributes, and reported amounts.
2. Duplicate accessions SHALL collapse only when canonical content is equivalent; conflicts SHALL
   fail or enter an explicit quarantine artifact.
3. A resolved offering series SHALL retain the ordered accessions that support it.

### Requirement 2 — Conservative chain resolution

**User story:** As a reviewer, I want amendment chains resolved by an auditable versioned rule, so
ambiguous filings cannot silently inflate or suppress capital.

#### Acceptance Criteria

1. THE resolver SHALL prefer explicit SEC linkage fields when available and document every fallback
   identity component.
2. IF a filing cannot be assigned to one offering series without ambiguity, THEN it SHALL receive
   an unresolved status and SHALL NOT enter default monetary aggregates.
3. Chain-policy version and resolution reason SHALL be present on every resolved or unresolved row.

### Requirement 3 — Chain-aware amounts and counts

**User story:** As a capital-data consumer, I want filings, offering series, and amounts reported at
their proper grains, so a filing count is not mistaken for a distinct raise count or dollar total.

#### Acceptance Criteria

1. For an auditable chain, THE as-of amount SHALL come from one deterministically selected filing,
   normally the latest valid amendment as of the declared cut, and SHALL NOT sum chain members.
2. Independent resolved offering series MAY be summed only after one representative amount per
   series is selected.
3. Outputs SHALL report filing count, resolved series count, unresolved filing/series count, and
   excluded dollars separately.
4. Existing raw-sum helpers SHALL be removed from headline monetary paths or renamed as explicitly
   filing-grain diagnostics.

## Out of scope

- Inferring undisclosed private capital or correcting self-reported SEC amounts.
- Changing SBIR↔Form D company matching.
- Treating Form D capital as caused by SBIR funding.
- Heuristically forcing every amendment into a chain to maximize coverage.

## Dependencies

- Form D XML parser with accession and amendment fields — EXISTS
- High-confidence SBIR↔Form D matching — EXISTS, UNCHANGED
- Shared agency-private-capital and bootstrap aggregators — EXISTS, RAW-SUM BEHAVIOR
