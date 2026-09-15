# Supplier-Share Census Requirements

**Research question anchor:** F2, supplier-track share of the SBIR/STTR portfolio
**Target epistemic tier:** exploratory
**Status:** Active
**Out of scope:** causal claims; loans or instrument fit; supply-chain embeddedness;
  public per-firm naming; new M&A discovery; new fuzzy identity matching

## Purpose

Estimate the share of cumulative SBIR/STTR award dollars and firms associated with
**sustained federal performers**: awardees with an observed federal-persistence signal and no
observed venture signal. This is a descriptive 2x2 classification, not a claim about firm
intent, dependence, commercialization quality, or program effects.

The neutral definition must appear before either interpretation. The same result may be read
as durable mission-supplier capacity or, pejoratively, as a "mills share." Neither reading is
encoded in the classifier.

## Reuse And Lifecycle Constraints

1. The producer SHALL consume the materialized SBIR.gov award history and
   `CanonicalMergePolicy.PRELOAD_V1`; it SHALL NOT add a fuzzy matcher.
2. The producer SHALL consume the existing Form D high-confidence tier and existing M&A
   high-plus-medium tiers without changing their thresholds.
3. The producer MAY consume an already materialized Phase III/FPDS prime-contract artifact.
   It SHALL NOT add a Dagster asset or run a new external-data ingestion path.
4. The Deferred `ma-discovery-integration` spec SHALL remain deferred. The Gated
   `phase-iii-hand-label-validation` spec SHALL not be implemented by this work.
5. Every generated artifact SHALL be labeled exploratory, non-citable, and
   `validation_status`-gated.

## Deterministic Classification

1. The denominator SHALL include every nonblank company label in the current materialized
   SBIR.gov history and collapse all labels through `PRELOAD_V1`. The readout SHALL reconcile
   source labels to canonical firm envelopes.
2. Federal persistence SHALL be true when any frozen criterion fires: award tenure at least
   `T`, total observed awards at least `N`, or positive net observed prime obligations after an
   explicit Phase II completion date. The output SHALL record each criterion separately.
3. Venture presence SHALL be true when any frozen signal fires: at least one existing
   high-confidence Form D match, an existing high- or medium-confidence M&A hit, or an optional
   supplied IPO registration-statement hit.
4. No required venture-channel coverage SHALL NOT be interpreted as no signal. Every firm SHALL
   carry a typed absence reason distinguishing `no_filing_found`, `not_searchable`, and
   `window_censored`.
5. The producer SHALL evaluate the complete grid `T in {8, 10, 12}`, `N in {4, 6, 10}`, and
   minimum observation window in `{12, 15}` years. The central descriptive cell SHALL be
   `T=10`, `N=6`, `window=15`.
6. The headline denominator SHALL include only first-award cohorts with at least the configured
   minimum observation window. Classification uses all history observed by the declared data
   cut; the window is a maturity gate, not a follow-up truncation.
7. The producer SHALL publish all four measurable 2x2 cells plus indeterminate venture cells.
   It SHALL suppress the supplier-share headline when required venture channels are not
   searchable.

## Outputs

1. A pseudonymous firm-by-grid Parquet SHALL be authoritative and include
   `validation_status`, `citable=false`, criteria-fired fields, typed absence, award counts,
   cumulative award dollars, agency-dollar shares, and source coverage status.
2. One normalized summary CSV SHALL contain the matrix overall and by agency, first-award year,
   award-count stratum, and denominator-wide cumulative-dollar decile, plus the supplier-cell
   top-decile concentration measure.
3. One figure SHALL show supplier-cell cumulative-dollar share by first-award cohort, the central
   grid cell, the full `T/N` sensitivity envelope, and the 12- and 15-year maturity cutoffs.
4. One Markdown readout SHALL state the estimand, exact criteria, source/identity coverage,
   sensitivity results, validation status, limitations, naming table, and dual-reading caution.
5. A private, deterministic, stratified sample of approximately 50 named firms SHALL be emitted
   only when all four cells are measurable. Public outputs SHALL contain pseudonymous IDs only.

## Validation Gates

No result is citable until all of the following are complete and reviewed:

1. A roughly 50-firm cell-stratified public-web adjudication reports cell-level agreement.
2. A separately supplied anchor list confirms known venture graduates and known multi-decade
   federal R&D performers land in their expected cells.
3. A fixed-seed, agency/cohort-blocked venture-label permutation and classifier arm-blindness
   audit are reviewed. These diagnostics are falsification checks, not causal controls.

## Acceptance Criteria

1. Re-running against byte-identical inputs produces byte-equivalent tabular classifications
   after Parquet metadata differences are ignored and identical CSV/readout content.
2. All 18 grid cells reconcile firm counts and award dollars across the four measurable and two
   indeterminate matrix cells.
3. Agency, cohort, and award-count stratifications reconcile to their declared denominators.
4. Missing Form D or M&A inputs yield indeterminate venture status and a suppressed headline,
   never a valid-looking zero.
5. `make docs-check`, the epistemic-tier guard, and a full producer run complete successfully.
