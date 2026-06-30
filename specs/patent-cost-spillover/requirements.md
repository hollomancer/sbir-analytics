# Patent Cost and Spillover Analysis — Requirements

> **Status:** Not yet started — zero implementation code as of June 2026.
> Anchors inventory questions **C3a–c** in [docs/research-questions.md](../../docs/research-questions.md).
> Target benchmarks: NIH ~$1.5M marginal cost per patent; Myers & Lanahan AER 2022 ~3× DOE
> spillover, ~60% U.S.-retained [L9][L5].

**Research question anchor:** C3 — marginal cost per patent and spillover multiplier (inferential tier)
**Answers for:** R&D policy researchers, OSTP analysts, agency R&D directors
**Complexity tier:** Inferential (Tier 3)

---

## Done when

> An analyst can state: "NIH produces one linked patent per ~$1.5M in SBIR funding.
> Our pipeline yields [X] per $1M for NIH and [Y] for DOE, using [method]. DOE patents
> attract [Z]× non-SBIR citations — [above / below / consistent with] Myers & Lanahan's
> ~3× spillover figure. The difference is attributable to [methodology / time window /
> citation-lag window]."
>
> As with the leverage ratio, a characterized divergence from the benchmark is a valid
> result. An unexplained match is not.

---

## Background

USAspending has no patent field. USPTO government-interest statements carry
grant/contract numbers but are not joined back to award databases. The existing USPTO
pipeline performs that join, producing a `patent_id → award_id` linkage at scale. This
spec builds the analytical layer on top of that linkage: marginal knowledge-production
cost per agency, and a citation-network-based spillover multiplier that measures how far
SBIR-generated IP propagates into the broader innovation ecosystem.

NASEM treats patent output as a count variable. No NASEM study computes marginal cost
per patent across agencies or a spillover multiplier beyond the DOE analysis in [L5]
(which draws on [L9]). Both metrics are answerable now with existing pipeline components.

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

### Requirement 2 — Citation network and spillover multiplier

**User story:** As an OSTP analyst assessing the diffusion of federally funded innovation,
I want the ratio of non-SBIR citations to SBIR patents computed as a spillover multiplier,
so that I can state how many downstream inventions build on each SBIR-originated patent and
compare that figure to Myers & Lanahan's ~3× DOE finding [L9].

#### Acceptance Criteria

1. WHEN building the citation network, THE System SHALL ingest USPTO citing-patent →
   cited-patent pairs for all patents linked to SBIR awards.
2. WHEN classifying citations, THE System SHALL label each citation as one of:
   SBIR→SBIR, non-SBIR→SBIR (inbound spillover), or SBIR→non-SBIR (outbound), using
   the patent-award linkage to determine SBIR status.
3. WHEN computing the spillover multiplier, THE System SHALL calculate: inbound
   non-SBIR citations to SBIR patents / SBIR-linked patent count, at both the
   aggregate level and per agency.
4. WHEN computing the U.S.-retained fraction, THE System SHALL use USPTO assignee
   country codes to distinguish U.S.-retained from internationally assigned citations,
   targeting the ~60% U.S.-retained finding from [L9].
5. WHEN the citation data has a lag window (USPTO citation records typically lag
   grant date by 12–24 months), THE System SHALL document the citation-window cutoff
   used and its effect on the multiplier, so the figure is not compared naively to
   studies using different windows.

---

### Requirement 3 — NASEM / Myers & Lanahan reconciliation

**User story:** As a policy analyst preparing a publishable methodology note, I want
the pipeline's cost and spillover figures accompanied by a structured reconciliation
against the NIH $1.5M and DOE 3× benchmarks, so that any divergence can be attributed
to methodology rather than left as an unexplained discrepancy that would undermine
credibility.

#### Acceptance Criteria

1. WHEN the aggregate figures are computed, THE System SHALL produce a reconciliation
   report documenting: measurement time window, patent-award linkage method, citation
   cutoff date, and entity-resolution match rate.
2. WHEN the marginal-cost figure diverges from NIH's ~$1.5M by more than 50%, THE
   System SHALL identify at least one methodology difference (linkage coverage, award
   denominator scope, patent-type filter) that accounts for the gap.
3. WHEN the spillover multiplier diverges from Myers & Lanahan's ~3× by more than
   1.0×, THE System SHALL identify which methodological difference (citation window,
   SBIR patent definition, U.S./international scope) accounts for the gap.
4. WHEN emitting the reconciliation, THE System SHALL produce both a JSON artifact
   and a markdown summary to `reports/patent-spillover/reconciliation/`.

---

### Requirement 4 — Cross-agency and stratified extension

**User story:** As an SBIR program manager or OSTP analyst comparing knowledge-output
profiles across the portfolio, I want both metrics broken out by technology area, firm
size, and award vintage, so that I can identify which CET areas and investment profiles
produce the highest knowledge output per dollar and which show low spillover — suggesting
IP retention rather than diffusion into the broader ecosystem.

#### Acceptance Criteria

1. WHEN stratifying by CET area, THE System SHALL emit marginal cost per patent and
   spillover multiplier for each of the 21 canonical CET areas in `config/cet/taxonomy.yaml`,
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
