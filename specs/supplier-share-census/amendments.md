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
