# Patent Cost and Spillover Analysis — Requirements

**Target epistemic tier:** `pipelines`

> **Status:** Gated backlog — zero cost/citation/spillover analytical-layer
> implementation as of July 2026.
> Anchors inventory questions **C3a–c** in [docs/research-questions.md](../../docs/research-questions.md).
> Target benchmark: **NIH ~$1.5M marginal cost per patent** [L5]. That is the only benchmark this
> spec's outputs may be compared against.
>
> **Not benchmarks for this spec.** Myers and Lanahan AER 2022 (~3× DOE spillover, ~60%
> U.S.-retained) [L9] estimates a different quantity by a different design, and this spec's
> descriptive citation-network measure is not an estimate of it. Replicating it belongs to
> roadmap Order 7, behind a spec at the inferential tier; see
> [the replication roadmap](../../docs/research/literature-replication-roadmap.md).

**Research question anchor:** C3 — marginal cost per patent and spillover multiplier (inferential
tier). This spec delivers the **marginal-cost** half of C3 plus a separately named descriptive
citation measure. The spillover-multiplier half is not in scope here; it is roadmap Order 7.
**Answers for:** R&D policy researchers, OSTP analysts, agency R&D directors
**Complexity tier:** Inferential (Tier 3)

---

## Done when

> An analyst can state the marginal cost per linked patent. An analyst can also report a
> separately named citation-network measure. Neither result estimates the Myers-Lanahan
> spillover effect. A Myers-Lanahan replication requires its state-policy and
> technology-similarity design.
>
> As with the leverage ratio, a characterized divergence from the benchmark is a valid
> result. An unexplained match is not.

---

## Background

USAspending has no patent field. USPTO government-interest statements carry
grant/contract numbers but are not joined back to award databases. The existing USPTO
pipeline performs that join, producing a `patent_id → award_id` linkage at scale. This
spec builds two descriptive measures on that linkage: marginal knowledge-production cost
per agency and citation-network diffusion. These measures do not identify the causal
Myers-Lanahan spillover estimand.

NASEM treats patent output as a count variable. The DOE analysis in [L5] draws on [L9].
Its spillover estimate requires matching-policy variation and technology-space similarity.
Existing pipeline components support descriptive patent-cost and citation measures only.

---

## Requirements

### Requirement 1 — Marginal cost per patent by agency

**User story:** As an R&D policy researcher benchmarking federal knowledge-production
efficiency, I want the ratio of SBIR award dollars to linked patents computed per agency,
so that I can compare agencies on a cost-per-knowledge-unit basis and position the result
against NIH's published ~$1.5M figure.

#### Acceptance Criteria

1. WHEN computing marginal cost per patent, THE System SHALL divide total SBIR award
   dollars by linked-patent count for each agency, both at the aggregate level and as a
   firm-level distribution (median, 25th/75th percentile).
2. WHEN an agency has fewer than 20 linked patents in the measurement window, THE System
   SHALL suppress the per-agency figure and note the suppression reason, to prevent
   small-cell estimates from appearing alongside reliable agency figures.
3. WHEN reporting marginal cost, THE System SHALL also report the patent-award match rate
   (linked patents / total SBIR patents per agency) so that coverage gaps are visible.
4. WHEN the pipeline figure diverges from NIH's ~$1.5M benchmark, THE System SHALL
   document the time window, linkage method, and any patent-type filters used, so that
   the difference can be attributed rather than left unexplained.
5. WHEN stratifying by technology area, THE System SHALL use CET classifier output to
   emit a marginal cost figure per CET area for agencies with sufficient coverage.

---

### Requirement 2 — Citation-network diffusion extension

**User story:** As an OSTP analyst assessing patent diffusion, I want a citation-network
measure for SBIR-linked patents. I want it reported as a descriptive extension, not as the
Myers-Lanahan spillover estimand.

#### Acceptance Criteria

1. WHEN building the citation network, THE System SHALL ingest USPTO citing-patent →
   cited-patent pairs for all patents linked to SBIR awards.
2. WHEN classifying citations, THE System SHALL label each citation as one of:
   SBIR→SBIR, non-SBIR→SBIR (inbound spillover), or SBIR→non-SBIR (outbound), using
   the patent-award linkage to determine SBIR status.
3. WHEN computing citation-network diffusion, THE System SHALL calculate inbound
   non-SBIR citations per SBIR-linked patent at aggregate and agency levels.
4. WHEN reporting this measure, THE System SHALL label it `citation-network diffusion`.
   THE System SHALL NOT compare it with the Myers-Lanahan 3× or 60% estimates.
5. WHEN the citation data has a lag window (USPTO citation records typically lag
   grant date by 12–24 months), THE System SHALL document the citation-window cutoff
   used and its effect on the citation-network diffusion measure, so the figure is not
   compared naively to studies using different windows.

---

### Requirement 3 — Benchmark boundaries

**User story:** As a policy analyst, I want each result compared only with a benchmark
that estimates the same quantity. I want incompatible estimands reported separately.

#### Acceptance Criteria

1. WHEN the aggregate figures are computed, THE System SHALL produce a reconciliation
   report documenting: measurement time window, patent-award linkage method, citation
   cutoff date, and entity-resolution match rate.
2. WHEN the marginal-cost figure diverges from NIH's ~$1.5M by more than 50%, THE
   System SHALL identify at least one methodology difference (linkage coverage, award
   denominator scope, patent-type filter) that accounts for the gap.
3. THE System SHALL NOT treat citation-network differences from Myers and Lanahan [L9] as
   replication error, because this spec does not replicate that paper. Replication requires
   the authors' state-policy and technology-similarity design, which is causal inference and
   sits above this spec's `pipelines` target tier. It is roadmap Order 7 work and is **not** an
   acceptance criterion here; it needs its own spec at the inferential tier, and that spec is
   not yet ungated in [the status registry](../../specs/status.md).
4. WHEN emitting the reconciliation, THE System SHALL produce both a JSON artifact
   and a markdown summary to `reports/patent-spillover/reconciliation/`.

---

### Requirement 4 — Cross-agency and stratified extension

**User story:** As an SBIR program manager or OSTP analyst comparing knowledge-output
profiles across the portfolio, I want patent cost and citation-network diffusion broken
out by technology area, firm size, and award vintage. These descriptive cuts must remain
separate from the Myers-Lanahan estimand.

#### Acceptance Criteria

1. WHEN stratifying by CET area, THE System SHALL emit marginal cost per patent and
   citation-network diffusion for each of the 21 canonical CET areas in `config/cet/taxonomy.yaml`,
   suppressing cells with fewer than 10 linked patents.
2. WHEN stratifying by firm size, THE System SHALL use the same size buckets as the
   leverage-ratio analysis (SAM.gov employee or revenue tiers) for consistency.
3. WHEN stratifying by award vintage, THE System SHALL group by first-SBIR-award
   fiscal year and emit both metrics per cohort.
4. WHEN emitting stratified output, THE System SHALL include the linked-patent count
   and citation count per cell so that readers can assess statistical reliability.

---

## Dependencies

- Patent-award linkage (`sbir_etl/transformers/patent_transformer.py`) — EXISTS
- USPTO extraction pipeline — EXISTS
- USPTO Lambda downloads (`specs/archive/completed-features/uspto-lambda-downloads/`) — COMPLETE
- CET classifier (`packages/sbir-ml/sbir_ml/ml/models/cet_classifier.py`) — EXISTS
- Entity resolution — EXISTS
- USPTO citation data ingestion — **PRECONDITION; not yet implemented** (see design.md)
- Follow-on funding multiplier analysis (M1) — for shared entity universe
