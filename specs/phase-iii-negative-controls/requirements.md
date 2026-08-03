# Phase III Negative Controls and Placebo — Requirements

> **Status (2026-08-02):** The bounded, data-independent methods are approved and
> implemented. Matching, balance, reporting, artifact materialization, and release remain
> gated on the questions in [`design.md`](design.md). No census, control, or placebo result
> had been computed or seen when these requirements were approved.

**Research-question anchors:** B2 and B3 in
[`docs/research-questions.md`](../../docs/research-questions.md)

## Done when

The study is done only when an analyst can compare the frozen Phase III census proxy for
SBIR firms with a pre-registered matched-control arm and the single fixed placebo, while
showing exact-identifier exclusions, the normalized-name stress set, covariate balance,
and full per-firm distributions. The comparison must use the same pair builder and census
criteria in every arm. It must prominently state that employee count was unavailable and
omitted, and it must describe retained controls as **“no observed exact-identifier
SBIR/STTR match,”** never as certified SBIR-negative.

No such result or artifact exists yet. The deliberately failing release sentinel remains
closed until all release evidence exists.

## Requirements

### Requirement 1 — Exact-identifier eligibility audit

1. The control-candidate audit **SHALL** compare strict normalized UEI and DUNS values
   against the complete available SBIR/STTR award history supplied to the audit.
2. A candidate with an observed exact UEI match, exact DUNS match, or both **SHALL** fail
   the screen. Every failed row **SHALL** record each applicable exclusion reason.
3. A retained candidate **SHALL** be labeled exactly **“no observed exact-identifier
   SBIR/STTR match.”** The label **SHALL NOT** be shortened to “non-SBIR,”
   “SBIR-negative,” or any equivalent certification.
4. The audit **SHALL** use the existing strict `normalize_uei` and `normalize_duns`
   functions. Missing or malformed values do not match; they also do not establish that
   the entity never received an award.
5. The pure audit helper **SHALL NOT** claim that its input history is complete. A future
   materialization must verify and record the history snapshot's provenance and
   completeness before calling it.

### Requirement 2 — Identifier-free exact-name stress set

1. The reporting stress flag **SHALL** consider only SBIR/STTR history rows for which
   neither UEI nor DUNS yields a usable strict normalized identifier.
2. Candidate and award-recipient names **SHALL** use the existing deterministic company-
   name normalizer. Only equality of the resulting nonblank normalized names is a match.
3. The name flag **SHALL NOT** change exact-identifier eligibility, matching inclusion,
   census criteria, weights, or thresholds.
4. The flagged set **SHALL** be reported as a worst-case stress set. It **SHALL NOT** be
   called a contamination estimate or upper bound: exact names do not cover aliases,
   rebrandings, acquisitions, spelling changes, or other identity variation, and exact
   normalization can also create false positives.

### Requirement 3 — Matching and the employee-count limitation

1. A future approved matcher **SHALL** select one through three controls using primary
   NAICS, state, year of first federal contract, and PSC family.
2. Employee count **SHALL BE OMITTED**. No employee proxy, size band, revenue band, or new
   band boundary may be introduced under this spec.
3. Every eventual result and methods artifact **SHALL** prominently state that omitting
   firm size is a major known threat to balance because size may relate to both SBIR/STTR
   participation and contracting outcomes.
4. Matching **SHALL NOT** be implemented until the candidate frame, PSC-family
   derivation, reuse, tie-breaking, and missing-covariate questions in the design are
   resolved before results are viewed.

### Requirement 4 — Balance and distributional reporting

1. A future balance artifact **SHALL** report standardized mean differences for every
   matched covariate and stop for review when an approved key-covariate encoding exceeds
   the pre-registered absolute `0.1` limit.
2. The encoding of categorical and temporal covariates **SHALL** be resolved before the
   balance calculation is implemented.
3. Arm results **SHALL** include the full per-firm distribution of criteria-met counts,
   the overlap coefficient, and the ratio of firms clearing the complete criteria set.
4. The per-firm grain and the treatment of multiple pseudo-index rows **SHALL** be
   resolved before those distributions are implemented.

### Requirement 5 — Arm-blind census evaluation

1. SBIR, control, and placebo pair frames **SHALL** be evaluated with the existing
   `apply_core_clauses`, `build_dropoff_ladder`, and `build_sensitivity_grid` helpers and
   their frozen criteria.
2. Pair construction for SBIR and future pseudo-index control rows **SHALL** reuse the
   existing normalized exact-UEI `build_uei_pairs` boundary.
3. No filter function may accept or inspect an arm, cohort, treatment, control, or placebo
   label. There **SHALL NOT** be an `if is_control:` inclusion path.
4. No scorer, similarity, model, weight, rank, or threshold may affect inclusion.

### Requirement 6 — One fixed placebo

1. There **SHALL** be one pre-registered placebo using seed `20260801`.
2. `prior_period_of_performance_end` **SHALL** be permuted once at unique
   `prior_award_id` grain, not independently at pair-row grain.
3. The shuffled date assigned to a prior award **SHALL** propagate to every fan-out pair
   row for that award.
4. The permutation **SHALL** preserve the award-grain marginal multiset of dates, row
   count, pair order, and every non-date column.
5. Conflicting dates within a prior award, blank prior-award identifiers, or unparsable
   nonblank dates **SHALL** fail before permutation.
6. The placebo frame **SHALL** run through the identical frozen census helper without
   selecting a favorable seed or changing a criterion after comparison.
7. One evaluation call **SHALL** permute once and pass that same in-memory pair frame to
   both the drop-off ladder and sensitivity grid; the two tables may not be based on
   separate permutations.

### Requirement 7 — Release gate

1. The sentinel in
   `tests/unit/phase_iii_negative_controls/test_release_gate.py` **SHALL** remain a
   deliberate failure until real, provenance-backed negative-control and placebo
   artifacts exist and their pre-registered checks pass.
2. The sentinel **SHALL NOT** be removed, skipped, xfailed, or weakened to make CI green.
3. Pure helper tests do not close the gate and are not empirical evidence.
4. No production census, negative-control, or placebo count may be quoted from this
   implementation branch.

## Prohibited scope

- No modification to `phase_iii_candidates/assets.py`, `TransitionScorer`, or any file
  under `packages/sbir-ml/sbir_ml/transition/detection/`.
- No modification to the frozen census design, amendment log, criteria, constants,
  weights, or thresholds.
- No Dagster asset, new configuration tree, generic matching framework, or dependency.
- No name similarity, fuzzy matching, alias expansion, embedding, model, or classifier.
- No silent answer to any question listed in the design.
