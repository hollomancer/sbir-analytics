# Quantifying dark Phase III: 3-source capture-recapture (multiple-systems estimation)

Status: **spec — not built.** Turns the 2-source lower bound (~949) into a defensible point estimate + CI.

## What this resolves

The dark Phase III count (contracts that are genuinely SBIR Phase III but carry neither the FPDS code nor a
"SBIR PHASE III" description) cannot be reached by a classifier — at ~1% prevalence that needs ~0.95 AUC,
unreachable by text, and DoD's descriptions are empty anyway (`eval-validity.md`: median 43 chars; a dense
model does *worse* on that boilerplate, 0.659 vs 0.714). **Capture-recapture sidesteps the wall entirely**:
it never classifies a contract; it infers the total from the overlap of incomplete high-precision *lists* —
the method a census uses to estimate its own undercount and epidemiology uses for hidden populations.

**Already computed (2-source, Lincoln-Petersen/Chapman):** code (6,351) × description (962), overlap 821 →
total ≈ 7,441, **dark ≈ 949 [95% CI 767–1,130]**. But two-source *assumes the signals are independent*, and
they are positively correlated (a CO who codes SR3 also writes "SBIR PHASE III"), which inflates the overlap
and **underestimates** the total — so **949 is a lower bound, not an estimate.** A third list breaks this: it
lets a log-linear model *estimate* the dependence instead of assuming it away.

## The three capture lists

| # | Signal | Source | Have? | Precision |
|---|---|---|---|---|
| 1 | **CODE** — FPDS element-10Q SR3/ST3 | `m0a_coded_dod` (6,351, award-grain) | ✅ | high |
| 2 | **DESCRIPTION** — "SBIR PHASE III" text | `m0a_desc_phase3_dod` (962) | ✅ | high (exact phrase) |
| 3 | **AUTHORITY** — sole-source under SBIR statute | FPDS competition fields + J&A text | ⚠️ build | needs validation |

**Third signal = the sole-source/authority list, and it must be STRUCTURAL, not text** — the dense-model
result proves DoD text is uninformative, so a retrieval-threshold list would be weak *and* correlated with
list 2. Phase III contracts are typically awarded other-than-full-and-open citing SBIR/STTR statutory
authority (15 U.S.C. §638). Build it from USAspending/FPDS `other_than_full_and_open_competition_code` /
`extent_competed` / `reason_not_competed`, cross-checked against the J&A notice text already pulled from the
GSA archive (the sole-source J&As cite "Phase III" + SBIR authority). It is **independent of both the 10Q
code and the description text** — the property MSE needs.

- **Feasibility gate (do first):** confirm FPDS exposes an SBIR/STTR-specific non-competed reason code and
  measure its precision (does it flag non-SBIR sole-source too?). If the structured code is not SBIR-specific,
  fall back to J&A-text authority (lower coverage, higher precision). If neither yields a clean high-precision
  list, MSE stays 2-source (report 949 as a bound only).

## Method

1. **Link the three lists at award grain** via `sbir_etl.utils.award_identity.award_key_series` (#449) — the
   compound key, NOT bare PIID ([[fpds-piid-not-a-key]]). Linkage error (same contract counted twice across
   lists) is the single biggest threat; a mislinked pair fabricates a phantom "caught by one" unit.
2. **Build the 2³−1 = 7 observed capture cells** (which lists caught each contract; the 000 cell is the dark
   unknown).
3. **Fit log-linear Poisson models** to the 7 cells (statsmodels GLM, or hand-rolled IPF). Main effects =
   per-list capture rates; pairwise interactions = list dependence. The 3-way interaction is unidentifiable
   (would saturate) — that residual assumption is stated, not hidden. Predict the 000 cell → dark count.
4. **Model selection + sensitivity:** fit the independence model and each 2-way-interaction model; report the
   **range** across plausible models by AIC/BIC, not a single point.
5. **Chao (1987) lower-bound estimator** alongside — heterogeneity-robust, gives a defensible floor whatever
   the dependence structure. Report `[Chao lower bound, log-linear point estimate, CI]`.
6. **CIs** via the log-linear asymptotic covariance or a nonparametric bootstrap over contracts.

## Assumptions & failure modes (the honest core)

- **Closed population** — fix a FY window (FY2016–2025, the archive/coding coverage). Contracts are units.
- **List precision** — every list must flag *only* true Phase IIIs; false positives inflate. Code/description
  are clean; the authority list is the one to validate (see gate).
- **Heterogeneity** — big obvious Phase IIIs get all three signals, small ones none; this positive dependence
  biases toward underestimate. Chao mitigates; stratifying by agency/size/year helps.
- **Reachability** — MSE estimates Phase III *reachable by these three capture processes*. A truly trace-less
  follow-on remains invisible; the structural authority signal is chosen precisely to extend reach past text.
- **3-way dependence** unidentifiable with 3 lists — the one assumption that survives; a 4th list (e.g. the
  thresholded retrieval ranker, or cross-agency TechPort) would relax it further.

## Validation — the gold-standard tie-in

The blind hand-adjudication (`~/Documents/phase3_adjudication_*`) is the external check: (a) it measures each
list's **precision** (are flagged contracts really Phase III?), and (b) adjudicating a random sample of
**un-flagged** DoD contracts directly estimates the false-negative rate → an *independent* read on the dark
cell to cross-check the MSE extrapolation. If the direct sample and the MSE disagree, the model assumptions
are wrong and we learn which.

## Deliverables

- `scripts/phase3_benchmark/build_authority_list.py` — construct + precision-validate list 3 (the real work).
- `scripts/phase3_benchmark/phase3_mse.py` — pure cores: `capture_cells`, `loglinear_estimate`,
  `chao_lower_bound`, `bootstrap_ci`; + unit tests on synthetic data with a KNOWN N (recover it).
- `specs/phase3-match-benchmark/mse-findings.md` — estimate, model-sensitivity range, assumptions, validation.

## Scope boundaries

- **IN:** DoD, FY-windowed, award-grain, 3 signals, log-linear + Chao, sensitivity range, CI, adjudication check.
- **OUT:** cross-agency (separate universe — could be a parallel MSE), a universe-wide classifier (base-rate
  wall), the detection ranker as a *counter* (it enters only as an optional high-precision 4th list).

## Effort & gates

- **Gate 1:** the feasibility check on signal 3 (SBIR-specific non-competed code + its precision). Cheap; do first.
- **Gate 2:** adjudication precision on the three lists before publishing any point estimate.
- Log-linear fitting is small (statsmodels/scipy); the authority-list construction + validation is the effort.

## Relation to PRs

Extends the undercount work here on #454 (`undercount-award-grain.md`: 141 described-not-coded is exactly the
desc-only capture cell). The detection ranker (#455) can later join as a 4th list. This is the rigorous
version of the "~1,000 dark" figure that has floated as an unmodeled guess.
