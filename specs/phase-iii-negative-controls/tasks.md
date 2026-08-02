# Phase III Negative Controls and Placebo — Tasks

> **Status (2026-08-02):** Bounded pure mechanics implemented; empirical phases gated.
> Approval was recorded before any census, negative-control, or placebo result was
> computed or seen.

## Phase 0 — Approved data-independent foundation

- [x] 0.1 Replace the dependency scaffold with requirements, design, tasks, approval
      date, result-visibility statement, and explicit unresolved questions.
- [x] 0.2 Implement a strict exact-UEI/DUNS candidate audit with row-level match flags,
      every applicable exclusion reason, and the approved retained-control label.
- [x] 0.3 Implement the exact normalized-name reporting flag over identifier-free
      SBIR/STTR award rows without changing eligibility or claiming an upper bound.
- [x] 0.4 Implement the one seed-`20260801` prior-award-grain end-date permutation with
      fan-out propagation and fail-closed integrity checks.
- [x] 0.5 Compose one placebo permutation with both existing frozen census table helpers;
      pass the same in-memory frame to both and add no arm-specific filter, scorer,
      threshold, similarity, ML, or copied criteria.
- [x] 0.6 Add fixture-based unit tests for the approved mechanics. Arm blindness is
      enforced independently by the broader suite merged from PR #480.
- [x] 0.7 Keep the release sentinel deliberately failing and clarify that pure helper
      tests do not constitute release evidence.

## Phase 1 — Resolve source and cohort questions before coding

- [ ] 1.1 Answer and approve the SAM snapshot acquisition/provenance question.
- [ ] 1.2 Answer and approve the registered-entity candidate-frame question.
- [ ] 1.3 Answer and approve the complete SBIR/STTR history provenance/scope question.
- [ ] 1.4 Answer and approve the canonical candidate-name, primary-NAICS, state, and
      missingness questions.
- [ ] 1.5 Materialize no cohort until tasks 1.1–1.4 are recorded in the design.

## Phase 2 — Resolve and implement matching

- [ ] 2.1 Answer and approve first-contract-year and PSC-family derivations.
- [ ] 2.2 Answer and approve the matching algorithm, one-to-three availability rule,
      control reuse, and deterministic tie-breaking.
- [ ] 2.3 Answer and approve multiple-identifier, successor-entity, and parent handling.
- [ ] 2.4 Implement the smallest matcher consistent with the approved answers. Do not add
      employee count, a size proxy, or new bands.
- [ ] 2.5 Emit a row-level match audit and pseudo-index provenance artifact using the
      approved schema.

## Phase 3 — Resolve and implement balance/reporting

- [ ] 3.1 Answer and approve categorical/temporal SMD encoding, weighting, missingness,
      zero-variance handling, and the key-covariate review set.
- [ ] 3.2 Answer and approve the per-firm distribution grain and multi-index collapse.
- [ ] 3.3 Implement balance tables, the absolute `0.1` review stop, full per-firm
      distributions, overlap coefficient, and complete-criteria ratios.
- [ ] 3.4 Make the employee-count omission and its residual-confounding risk prominent in
      every methods and result artifact.

## Phase 4 — Materialization and release evidence

- [ ] 4.1 Answer and approve output paths, schemas, manifests, hash/data-cut bindings,
      artifact checks, and reviewer sign-off.
- [ ] 4.2 Materialize the real exact-identifier audit and exact-name stress-set artifact.
- [ ] 4.3 Materialize the matched-control, balance, distributional, and single-placebo
      artifacts through the shared exact-UEI builder and frozen criteria.
- [ ] 4.4 Verify that no arm-specific branch, scorer, similarity, weight, model, threshold,
      alternate seed, or post-result criterion change entered the run.
- [ ] 4.5 Replace the deliberately failing sentinel only with evidence-backed release
      tests after all required artifacts and approvals exist.

## Explicit non-tasks

- Certifying any retained entity as SBIR-negative.
- Treating the exact-name flag as a contamination estimate or upper bound.
- Employee-count proxies, size bands, or new matching covariates.
- Changes to the frozen census design/amendments, freeze constants,
  `phase_iii_candidates/assets.py`, `TransitionScorer`, or transition-detection ML.
- Computing, materializing, or quoting real results on this implementation branch.
