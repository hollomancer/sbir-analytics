# Supplier-Share Census Freeze And Amendment Log

This is the append-only approval record for [`design.md`](design.md). Existing records must not
be edited, removed, or reordered. Every later change is a new numbered record stating the reason,
criteria impact, and result information visible when approved. The exploratory producer verifies
the raw-byte SHA-256 of this file and the design before reading analytical inputs.

## Revision 0 - Initial Exploratory Freeze

- **Approved:** 2026-08-21.
- **Git-history anchor:** The commit that first adds Revision 0 is the approval anchor; its
  identifier is intentionally not embedded in content that the producer hashes.
- **Frozen design SHA-256:**
  `d1edbcbdb66edc8a655cc21e75b42504e4c8293f95891af812d8fe6a735b6a19`.
- **Reason:** Freeze the neutral estimand, M&A-denominator reconciliation, identity policy,
  ordered persistence and venture clauses, typed-absence precedence, complete 18-cell grid,
  central descriptive cell, stratifications, output grain, and validation gates before producer
  implementation or a supplier-share result.
- **Criteria impact:** Establishes Revision 0. `T in {8, 10, 12}` years, `N in {4, 6, 10}`
  awards, and minimum observation window in `{12, 15}` years. Central cell is `(10, 6, 15)`.
- **Visibility at approval:** The materialized SBIR.gov source schema, 219,497 award-row count,
  34,460 exact nonblank source-company-label count, 34,143 `PRELOAD_V1` envelope count, and
  presence of a 45,355-row FY2026 prime-contract materialization were visible as source/identity
  feasibility facts. Historical aggregate M&A-study facts (including its approximately 34,460
  denominator and 15-year median time to signal) were already documented in the repository.
  No persistent-no-venture matrix, supplier-cell firm share, supplier-cell dollar share,
  stratified matrix, concentration statistic, placebo statistic, or validation agreement had
  been computed or seen. The required local Form D and M&A signal artifacts were known to be
  absent.

## Revision 1 - Denominator-Wide Dollar Deciles

- **Approved:** 2026-08-21.
- **Reason:** Resolve an output-contract ambiguity before publication. The requested
  cumulative-dollar-decile stratification must appear in the normalized summary, and "top decile
  of firms" means the highest cumulative-dollar decile of the full mature denominator rather
  than a separate within-supplier ranking.
- **Criteria impact:** None. The denominator, identity policy, persistence and venture clauses,
  typed-absence precedence, grid, and central cell are unchanged. Within each maturity window,
  all eligible firms are sorted by descending cumulative SBIR/STTR dollars with `firm_id` as the
  deterministic tie break and assigned row-count deciles `D01` through `D10`. The concentration
  statistic is supplier-cell dollars contributed by `D01` divided by all supplier-cell dollars.
  This supersedes Revision 0 design language that could be read as selecting the first
  `ceil(n/10)` firms after reranking only the supplier cell.
- **Visibility at approval:** One blocked exploratory run had reconciled 34,460 source labels to
  34,143 envelopes and found 20,049 firms mature under the central 15-year gate. Required Form D
  and M&A inputs were absent, so zero mature firms were venture-measurable. Every supplier firm
  share, supplier dollar share, decile matrix, concentration statistic, and placebo statistic was
  suppressed; no supplier-cell result was visible.

## Revision 2 - Freeze-File Whitespace Normalization

- **Approved:** 2026-08-21.
- **Current design SHA-256:**
  `c14dea2a147e46b740cc46925d7a89709a45c6aedc84c5a3324e3e75528e769f`.
- **Reason:** Remove trailing Markdown spaces and one extra terminal blank line before the initial
  approval commit so repository whitespace checks pass. No words, clauses, parameters, ordering,
  or output requirements changed.
- **Criteria impact:** None. Revision 1 remains the operative analytical amendment.
- **Visibility at approval:** Same blocked run described in Revision 1. All supplier shares,
  dollar-decile matrices, concentration statistics, and placebo statistics remained suppressed.

## Revision 3 - Multi-Agency Negative-Control Blocks

- **Approved:** 2026-08-21.
- **Reason:** Freeze the agency assignment for the required blocked-permutation diagnostic before
  any supplier-share result is available. Firms can receive awards from multiple agency groups,
  so a dollar-selected primary agency would make the diagnostic block depend on the outcome.
- **Criteria impact:** None. The descriptive denominator, both classification axes, grid, central
  cell, and reported estimands are unchanged. The diagnostic permutes venture labels within
  `agency-membership signature x five-year first-award cohort`, where the signature is the ordered
  `+`-joined set of agency groups with at least one observed award (`DoD`, `HHS`, `NSF`, `other`).
  Award dollars and matrix outcomes do not determine the block.
- **Visibility at approval:** The complete Form D artifact was available, but the local EFTS/M&A
  rebuild and supplier-share census were still incomplete. No supplier-cell firm share, dollar
  share, matrix, concentration statistic, or placebo statistic had been computed from complete
  venture inputs.

## Revision 4 - Typed Required-Channel Noncoverage Bounds

- **Approved:** 2026-09-10.
- **Post-result status:** This is an explicitly post-result exploratory reporting amendment. It
  was approved after the results listed below were visible and must not be described as
  preregistered or confirmatory.
- **Reason:** Required SEC filing documents can remain unavailable after deterministic retries.
  Preserve the frozen point-headline suppression while reporting the finite-population range in
  which those typed unknowns alone can move the observed sustained-federal-performer share.
- **Criteria impact:** None. The denominator, identity policy, persistence and venture clauses,
  typed-absence precedence, complete 18-cell grid, central cell, and validation gates are
  unchanged. For every mature frozen grid/stratum total, report a supplemental deterministic
  partial-identification interval. Its denominator is every mature firm in the stratum, or the
  corresponding observed SBIR/STTR dollars. Its lower numerator is the
  `persistent_no_venture` cell. Its upper numerator adds the
  `persistent_unknown_venture` cell, whose members have no known positive venture signal. Report
  firm and dollar endpoints, interval widths, and the upper-endpoint mover count and dollars.
  Point supplier-share fields remain null and `headline_available=false` whenever required
  coverage is incomplete. Matrix rows carry null bound fields. No imputation, probability model,
  confidence-interval language, concentration bound, or placebo bound is authorized. The private
  validation sample remains withheld unless the existing complete-measurability gate passes.
- **Interpretive limit:** The interval bounds only typed required-channel noncoverage under the
  frozen observed-record classifier. It does not bound false negatives in apparently searched
  sources, identity error, non-Reg-D capital, prime/sub-tier undercoverage, commercialization,
  dependence, supply-chain embeddedness, or physical chokepoints. All outputs remain exploratory,
  non-citable, and validation-gated.
- **Visibility at approval:** The PR description had already reported a central interval of
  23.69%-23.80% of firms and 64.66%-64.84% of dollars over 20,049 mature firms, with 124
  unresolved firms, 22 persistent upper-endpoint movers carrying $105.0M, and central cells of
  11,584 `not_persistent_no_venture`, 48 `not_persistent_unknown_venture`, 2,179
  `not_persistent_venture`, 4,750 `persistent_no_venture`, 22
  `persistent_unknown_venture`, and 1,466 `persistent_venture`. The visible agency firm/dollar
  intervals were DoD 34.67%-34.86% / 68.19%-68.36%, HHS 26.24%-26.39% / 56.81%-57.02%, NSF
  35.52%-35.65% / 50.27%-50.49%, and Other 36.84%-37.01% / 67.89%-68.06%. Across the 18 grid
  cells, the visible ranges were 16.73%-31.40% of firms and 59.09%-67.63% of dollars; the visible
  central top-decile concentration range was 79.50%-79.62%. A visible mechanical Form D tier
  sensitivity moved the central known-supplier share from 23.69% to 24.10% of firms and 64.66%
  to 65.63% of dollars. A later fail-closed repair run had 17,477 of 20,049 mature firms
  measurable and central cells of 11,107
  `not_persistent_no_venture`, 525 `not_persistent_unknown_venture`, 2,179
  `not_persistent_venture`, 4,469 `persistent_no_venture`, 303
  `persistent_unknown_venture`, and 1,466 `persistent_venture`. The mechanically implied Revision
  4 interval from that repaired but not freshly refined run was 22.2904%-23.8017% of firms and
  60.6113%-64.8420% of dollars. The current M&A artifact had 3,198 direction-sensitive events,
  zero typed-complete refinement records, 2,049 legacy-invalid verdicts, and 1,149 absent
  verdicts. The repaired EFTS roster retained 132 document-incomplete labels. These visible facts
  are disclosed so Revision 4 cannot be mistaken for a pre-result choice.
