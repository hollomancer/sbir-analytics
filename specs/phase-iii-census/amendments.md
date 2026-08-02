# Phase III Census Freeze and Amendment Log

This is the append-only approval record for
[`design.md`](design.md). Existing records must not be edited, removed, or reordered.
Every later change is a new numbered record stating the reason, the criteria impact, and
what result information was visible when it was approved. Git history preserves each
prior version, while the census asset verifies and records the raw-byte SHA-256 of both
files before materialization.

## Revision 0 — Initial Phase 0 freeze

- **Approved:** 2026-08-01.
- **Commit:** `989d9155c60e227ff2f921d3495e251a4246dda3`.
- **Reason:** Freeze the label-free estimand, five cumulative criteria, exact-UEI pair
  boundary, six sensitivity cells, output metrics, and control pseudo-index before Phase
  1 implementation.
- **Criteria impact:** Establishes the initial criteria and their order.
- **Visibility at approval:** No census, sample, coverage, drop-off, sensitivity,
  negative-control, or placebo count had been computed or seen.

## Revision 1 — Target-code provenance

- **Approved:** 2026-08-01.
- **Commit:** `76008c173d8b8fd712a942d86c361e410ff95bc8`.
- **Reason:** USAspending documentation establishes `research` as the authoritative FPDS
  SBIR/STTR code and does not establish a separate `sbir_phase` source field. Requiring
  `research` and treating a genuine `sbir_phase` only as supplemental evidence prevents a
  fabricated duplicate code.
- **Criteria impact:** No code set, clause, order, cell, window, predicate, or estimand
  changed; this amendment fixes field provenance for already-frozen coding clauses.
- **Visibility at approval:** Documentation and source-schema information were visible;
  no census, drop-off, sensitivity, negative-control, or placebo result had been computed
  or seen.

## Revision 2 — Federal Phase II award grain

- **Approved:** 2026-08-01.
- **Commit:** `577e6c34bf68a41a016b6ac4f495729eeecc2abf`.
- **Reason:** A pre-materialization integrity review found bare-PIID collisions and
  order-dependent transaction collapse. The approved generated-award and transaction-key
  construction makes the prior award grain deterministic and preserves signed actions.
- **Criteria impact:** No inclusion clause, order, sensitivity cell, or estimand changed;
  this amendment corrects the upstream meaning of one Phase II award.
- **Visibility at approval:** Source-key and transaction-grain integrity findings were
  visible. No census, drop-off, sensitivity, negative-control, or placebo result had been
  computed or seen.

## Revision 3 — SBIR.gov source-row grain

- **Approved:** 2026-08-01.
- **Commit:** `6d81874eaf6345abb32d116bfef40f8838a97bb4`.
- **Reason:** Full-history source inspection found exact duplicates, distinct awards that
  share partial keys, blank base identifiers, and the `NAVY38356` collision. The approved
  42-field fingerprint and deterministic surrogate preserve observable source rows without
  heuristic reconciliation.
- **Criteria impact:** No inclusion clause, order, sensitivity cell, or estimand changed;
  this amendment fixes full-history source construction and provenance.
- **Visibility at approval:** The named source collision and source-row integrity facts
  were visible. No census, drop-off, sensitivity, negative-control, or placebo result had
  been computed or seen.

## Revision 4 — Executable freeze and one-factor sensitivity diagnostic

- **Approved:** 2026-08-01.
- **Git-history anchor:** The commit that first adds Revision 4 to this file is the
  approval-record anchor; its identifier is intentionally not embedded in the content it
  hashes.
- **Reason:** An unchecked commit constant could not demonstrate that the materialized
  criteria matched the approved note. Separately, the original all-cell 3× span compared
  nested cells that can differ on two dimensions. Raw-byte digest verification makes the
  freeze executable, and seven adjacent contrasts isolate window and agency effects.
- **Criteria impact:** No inclusion clause, clause order, sensitivity cell, window
  endpoint, agency predicate, estimand, or output metric changed. The checkpoint moves to
  a post-write Dagster asset check and uses only the approved one-factor rule.
- **Visibility at approval:** Source-materialization integrity metrics and contract-source
  extraction progress were visible. No exact-UEI pair count, cumulative drop-off count,
  six-cell sensitivity result, negative-control result, or placebo result had been
  materialized or seen. The amendment was prompted by design review of the freeze and the
  nested grid, not by an outcome.

## Revision 5 — Phase 1 materialization sequencing

- **Approved:** 2026-08-02.
- **Git-history anchor:** The commit that first adds Revision 5 to this file is the
  approval-record anchor; its identifier is intentionally not embedded in the content it
  hashes.
- **Reason:** The repository owner approved materializing the frozen Phase 1 census now
  while deferring unresolved negative-control, matching, balance, control-reporting, and
  placebo questions as explicit later questions. This replaces the process pause recorded
  in the design status; it does not authorize selecting or quoting a headline cell or
  treating proxy survivors as validated Phase III.
- **Criteria impact:** None. No inclusion clause, clause order, sensitivity cell, window
  endpoint, agency predicate, estimand, output metric, source field, join, or diagnostic
  rule changed. Phase 2 and Phase 3 remain gated by their unresolved questions.
- **Visibility at approval and recording:** At owner approval, source/provenance validation
  and implementation/CI status were visible. When this approval was memorialized,
  February source-extraction progress was also visible. No exact-UEI pair count,
  cumulative drop-off count, six-cell sensitivity result, negative-control result, or
  placebo result had been materialized or seen.
