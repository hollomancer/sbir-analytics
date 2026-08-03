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

## Revision 6 — Exact-key multi-supplemental reconciliation

- **Approved:** 2026-08-02.
- **Git-history anchor:** The commit that first adds Revision 6 to this file is the
  approval-record anchor; its identifier is intentionally not embedded in the content it
  hashes.
- **Reason:** Production Phase II validation stopped on exact source key
  `140D0420C0002`, which has one federal generated award and two distinct retained
  SBIR.gov supplemental rows. The earlier singular-duplicate implementation made any
  supplemental multiplicity fatal even when the federal match was unique and taxonomy
  was nonconflicting. The repository owner approved reconciling every exact-key
  supplemental into the unique federal award without selecting a supplemental row.
- **Source-rule impact:** This supersedes the one-supplemental multiplicity stop. With no
  federal match, every distinct supplemental remains its own prior. With more than one
  federal match, materialization stops. With exactly one federal match, all exact-key
  supplementals are consumed together: every authoritative federal field is preserved,
  normalized nonblank NAICS and PSC values must be unanimous across federal and
  supplemental rows, only a missing federal taxonomy value may be filled, and every
  matched supplemental is removed without row-order dependence.
- **Criteria impact:** None. No exact-UEI pair universe, inclusion clause, clause order,
  sensitivity cell, window endpoint, agency predicate, estimand, output metric, cutoff,
  source field, or diagnostic rule changed. No scorer, weight, similarity rule, or model
  is introduced.
- **Visibility at approval:** Source/provenance validation, the failed Phase II run, and a
  full exact-key reconciliation audit were visible. The audit found 4,881 one-to-one
  shared keys and 19 one-federal/two-supplemental keys, with no multiple-federal key and
  no NAICS/PSC conflict. Supplemental non-taxonomy differences, including recipient
  identifiers, were visible but do not participate in the approved exact-key rule; the
  federal record remains authoritative. No exact-UEI pair count, cumulative drop-off
  count, six-cell sensitivity result, negative-control result, or placebo result had been
  materialized or seen.

## Revision 7 — Reconciliation-text consistency correction

- **Authority:** The repository owner's 2026-08-02 approval of Revision 6; this revision
  records no new policy choice.
- **Git-history anchor:** The commit that first adds Revision 7 to this file is the
  correction-record anchor; its identifier is intentionally not embedded in the content
  it hashes.
- **Reason:** The required post-implementation quality sweep found that the approved
  multi-supplemental rule was stated in the Phase II construction section and Revision 6
  log, while a later paragraph retained the superseded one-supplemental multiplicity stop.
  The stale paragraph is replaced so the frozen design states one rule consistently.
- **Criteria and source-rule impact:** None. The text now repeats the already-approved
  Revision 6 rule: exactly one federal match may reconcile one or more exact-key
  supplementals together under unanimous NAICS/PSC validation; multiple federal matches
  or taxonomy conflicts fail closed. No inclusion clause, pair universe, threshold,
  score, model, sensitivity cell, output metric, or implementation behavior changes.
- **Visibility at correction:** Source/provenance validation, the failed Phase II run,
  the full exact-key reconciliation audit, and passing focused implementation tests were
  visible. No exact-UEI pair count, cumulative drop-off count, six-cell sensitivity
  result, negative-control result, or placebo result had been materialized or seen.

## Revision 8 — Memory-safe execution equivalence

- **Authority:** The repository owner's approval of the frozen Phase 1 criteria and
  instruction to finish extraction; this revision records no new policy choice.
- **Git-history anchor:** The commit that first adds Revision 8 to this file is the
  execution-record anchor; its identifier is intentionally not embedded in the content it
  hashes.
- **Reason:** The first full census attempt failed before pair construction because the
  in-memory prior differed from its parquet only as `NaN` versus `None`; an exact
  null-canonical comparison fixed that fail-closed guard. The next attempt and a
  full-width read-only probe were then killed during exact-UEI pair expansion. A fixed
  projection of already-required source and pair fields, plus one validated cumulative
  survivor pass for both tables, completes the identical computation within memory.
- **Criteria and pair-universe impact:** None. The shared builder still performs the same
  normalized nonblank exact-UEI inner join at prior-award × target-transaction grain and
  retains its default full schema for the weighted path. The census receives every frozen
  required pair field. No inclusion clause, clause order, predicate, agency/window cell,
  metric, cutoff, score, model, or estimand changes.
- **Visibility at recording:** The validated Phase II parquet and two failed census run
  records were visible; neither failed run wrote a census artifact. A final read-only
  production-equivalent probe computed both in-memory audit tables and asserted only that
  each had its pre-specified six rows. No metric value was printed, inspected, quoted, or
  selected, and no census parquet existed when this revision was recorded. No
  negative-control or placebo result existed.

## Revision 9 — First-contract business-size matching covariate

- **Approved:** 2026-08-03.
- **Git-history anchor:** The commit that first adds Revision 9 to this file is the
  approval-record anchor; its identifier is intentionally not embedded in the content it
  hashes.
- **Reason:** Public SAM entity data does not provide the proposed employee-count measure,
  while FPDS/USAspending records the contracting officer's NAICS-specific small-business
  determination on federal contracts. The repository owner approved using that public,
  government-defined classification at the firm's first federal contract instead of
  inventing employee-band cutoffs or treating procurement volume as firm size.
- **Matching-rule impact:** Replace `employee-count band` with the binary
  `first-contract business-size class`. Both arms use the complete February contract
  history and the same normalized-UEI, earliest-action-date, `business_categories`
  derivation. Missing or conflicting classifications are reported exclusions and are
  never imputed. Primary NAICS, state, first federal contract year, PSC family, the 1–3
  control ratio, balance reporting, and the common filter path are unchanged.
- **Criteria impact:** None. No census universe, inclusion clause, clause order,
  sensitivity cell, window endpoint, agency predicate, estimand, output metric, score,
  model, or cutoff changes. Phase 1 artifacts are not rerun or reinterpreted by this
  matching-only amendment.
- **Visibility at approval:** The complete Phase 1 cumulative ladder and six-cell
  sensitivity artifacts had been materialized with verified provenance, and the
  one-factor sensitivity asset check had passed. No control candidate frame, eligibility
  result, matched set, balance statistic, negative-control criteria distribution,
  overlap coefficient, full-criteria ratio, or placebo result had been computed or seen.

## Revision 10 — Exact award-key recovery without the SBA Company Registry

- **Approved:** 2026-08-03.
- **Git-history anchor:** The commit that first adds Revision 10 to this file is the
  approval-record anchor; its identifier is intentionally not embedded in the content it
  hashes.
- **Reason:** The SBA Company Registry is unavailable. A read-only feasibility audit found
  that every SBIR.gov row lacking a valid UEI or DUNS retains `contract` or
  `agency_tracking_number`, permitting recovery from exact official award records. The
  repository owner approved revising the plan to use exact award-key adapters and to
  proceed under a fail-closed eligibility protocol.
- **Eligibility-rule impact:** Missing awardee identifiers may be enriched only from an
  exact, source-specific official award-key match whose records agree on one recipient
  identity. Names never create an identity link. Confirmed SBIR firms and candidates that
  collide with unresolved award rows are excluded; only candidates with no resolved
  identifier intersection and no unresolved exact name/address collision are eligible as
  `eligible_screened_negative`. A coverage audit remains a pre-outcome stop gate.
- **Criteria and matching impact:** None. No census pair universe, inclusion clause,
  clause order, sensitivity cell, window endpoint, agency predicate, estimand, output
  metric, matching covariate, score, model, or numeric cutoff changes. The protocol does
  not create a second Phase II-to-contract pair join.
- **Visibility at approval:** Phase 1 audit tables and their passed one-factor check were
  visible. Source-only feasibility counts for missing identifiers and available award-key
  fields were visible. No SAM control frame, eligibility classification, recovered
  identifier table, matched set, balance statistic, negative-control distribution,
  overlap coefficient, full-criteria ratio, or placebo result had been computed or seen.
