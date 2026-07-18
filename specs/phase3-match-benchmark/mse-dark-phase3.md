# Quantifying dark Phase III: 3-source capture-recapture (multiple-systems estimation)

Status: **provisional research annex** (ported to #458 after its snapshot; not reproduced through the
hardened pipeline). Per #458's decision record, the ~949 is the **Chapman/independence scenario**, not an
identified bound — report alongside `capture_sensitivity.py` list-odds-ratio and text-false-positive
sensitivity. The stratification results below sharpen that scenario (each valid refinement raises it) and the
sibling enumeration converts part of it into direct observation; all values await re-run through the #458
estimator discipline. Feasibility gate: no clean structured 3rd FPDS signal; MSE stays 2-source.

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

- **Feasibility gate — RUN 2026-07-17, result: no clean structured FPDS signal.** On 100 known DoD
  "SBIR PHASE III" contracts (USAspending): `Type of Set Aside` is **None/`SBA` (generic "Small Business
  Set-Aside — Total")** — *not* SBIR-specific, so it flags the entire small-business sole-source universe
  (terrible precision). `extent_competed` is mixed (D "full & open after exclusion", F "competed under SAP")
  with **no SBIR-specific non-competed reason**; `other_than_full_and_open` is unpopulated. The only
  SBIR-Phase-III-specific FPDS field is the 10Q code itself (= list 1). **There is no independent second
  structured FPDS signal.**
- **Fallback — J&A text (partial).** The GSA-archive J&A notices (~273 notices / 165 firms, high-precision,
  explicitly cite "SBIR Phase III") are independent of code and USAspending description. But two limits make
  them unfit as a *headline*-carrying third list: (a) **low coverage** (~165 of ~1,487 Phase III firms), and
  (b) **subtype skew** — J&As exist only for *sole-source* actions, so the list systematically misses
  competed Phase IIIs (a reachability bias, not just thin sampling).
- **Decision (per the gate's own rule): MSE stays 2-source; report ~949 as a defensible LOWER BOUND.** The
  J&A list is worth adding only as a **sensitivity extension** (a 3-source fit on the sole-source stratum, to
  probe the code×description dependence), NOT as the basis for a headline point estimate. The clean upgrade
  path is the missing **linkage field** (`eval-validity.md`): if a parent-SBIR-award-ID were populated, there
  would be no dark cell to estimate — the MSE quantifies the cost of its absence.

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

## Frame size, the bounds, and why direct validation is base-rate-blocked (measured 2026-07-18)

The **frame** = all un-flagged post-SBIR DoD contracts to the 8,064 DoD SBIR firms (a dark Phase III *must*
live here: post-SBIR, to an SBIR firm, caught by neither signal, not the SBIR award itself). Uniform sample
n=300 (USAspending recipient pulls, paginated; earlier runs failed on a pre-2007 `start_date` that returns a
misleading HTTP 500 — the indexed window starts 2007-10-01):

- **Frame ≈ 131,000 contracts** — 95% CI [71k, 202k]. Mean **16.3/firm**, median **0** (53% of SBIR firms have
  zero un-flagged post-SBIR contracts; the frame is concentrated in an established-firm minority, max 599).

This pins the **bounds on the dark cell**: `949 ≤ dark ≤ 131,000`. The lower bound (capture-recapture,
list-overlap) is a real estimate; the upper bound is the *trivial* ceiling (every un-flagged contract being a
Phase III — absurd). So the count is well-constrained below and barely constrained above: **total DoD Phase
III ∈ [≥7,441, ~137,500]**, dark ∈ [949, 131,000] — two orders of magnitude wide on the high side.

**Implied dark Y-rate for 949 = 949/131,000 = 0.7%.** This kills direct-sampling validation at small n: at a
0.7% rate a 15-row dark-cell probe expects **0.1 hits** (P(0 hits | 949 true) ≈ 90%), so it cannot distinguish
949 from 0 or from 3,000; observing ~5 hits needs **~700** hand-adjudicated rows. **The base-rate wall that
blocked the detector also blocks the validation.** Capture-recapture stands alone (it infers from overlap, not
sampling); the 15-row dark-cell stratum is demoted to an *existence scan*, not a count check.

**To narrow the range** (the real open problem): the lower bound won't move without a clean independent 3rd
signal (the feasibility gate found none). The productive path is **tightening the UPPER bound** — rank the
131k frame with the *structural* (non-text) detector and estimate the Phase-III rate per score band via
**stratified adjudication**, yielding a point estimate + CI instead of only the 949 floor. That is the one
design that uses the detector for what it's good at (ranking to concentrate the base rate) rather than as a
counter.

## Heterogeneity-stratified capture-recapture (run 2026-07-18)

Chapman per sub-agency stratum (labels normalized across lists — a naive string match fabricates phantom
zero-overlap strata; 5/821 overlap pairs genuinely disagree on sub-agency across lists, immaterial):

| stratum | n1 (coded) | n2 (desc) | overlap | dark | code-miss rate |
|---|--:|--:|--:|--:|--:|
| Air Force | 2,467 | 352 | 304 | 340 | 13.6% |
| Navy | 1,642 | 253 | 205 | 335 | 18.9% |
| DCMA | 607 | 77 | 58 | 177 | **24.4%** |
| Army | 994 | 194 | 165 | 145 | 14.9% |
| DLA / MDA / other | 641 | 86 | 84 | 10 | ~0–9% |
| **Stratified sum** | | | | **1,007 [812–1,202]** | |

- **The floor rises 949 → 1,007** — the direction heterogeneity theory predicts (pooled LP is biased low when
  capture rates vary). Office-prefix stratification gives 733 as a weak-stratification sensitivity point; the
  honest reporting band is **dark ≈ 950–1,200, floor ~1,000**.
- **The miss rate is organizationally structured, not random:** DCMA 24% (administers others' awards — coding
  context lost), Navy 19%, AF 14%, MDA ~0%. This targets the fix: the undercount concentrates where contract
  *administration* is separated from the awarding program office.

## What further stratification teaches (run 2026-07-18)

**Contract vehicle — the cleanest and biggest axis** (encoded in the award key itself, so per-stratum
overlaps sum to exactly 821; no cross-list assignment error possible):

| vehicle | n1 | n2 | overlap | miss rate | dark |
|---|--:|--:|--:|--:|--:|
| standalone contract | 2,692 | 578 | 524 | **9.3%** | 223 |
| task order under IDV | 3,659 | 384 | 297 | **22.6%** | 982 |
| **sum** | | | | | **1,205** |

The 10Q code is lost **at the order level under contract vehicles** — task orders miss 2.4× more than
standalone contracts. This corroborates and sharpens the DCMA finding (24% miss): the undercount concentrates
where award and administration separate. **Floor progression: pooled 949 → sub-agency 1,007 → vehicle 1,205**
— each finer (valid) stratification raises the floor, exactly as heterogeneity predicts. Best defensible floor
now **~1,200**.

**Time trend — the miss rate is WORSENING.** Using origination-year bands parsed identically from the PIID on
both lists (the naive version — coded transaction-FY vs desc origination-FY — puts the same contract in
different bands and explodes the estimate; caught via the overlap-sum check, 561≠821):

| origination band | miss rate | dark |
|---|--:|--:|
| pre-FY16 | 18.2% | 93 |
| FY16–18 | 5.0% | 38 |
| FY19–21 | 13.5% | 202 |
| FY22–25 | **17.3%** | 490 |

Coding compliance deteriorated ~3.5× from FY16-18 to FY22-25. The undercount is a *growing* problem, not a
legacy one — directly relevant to the urgency of the linkage-field fix.

## Rank-then-stratify: evaluated and NOT currently viable (run 2026-07-18)

Test: use coded Phase IIIs (n=5,282) as pretend-dark positives vs the 471-contract un-flagged pool; measure
how much available *structural* features concentrate the 0.7% frame prevalence.

- **Office lineage INVERTS** (LR 0.9×): un-flagged contracts match the firm's SBIR office *more* often (46.5%)
  than Phase IIIs do (41.9%) — a firm's routine work stays at the office that knows it, while Phase III
  production often moves to a *different* buying command. The presumed-best lineage feature is anti-signal.
- Timing helps (65% vs 33% within [−2,+5] of last SBIR year) but combined LR is only **1.4×** → best band
  prevalence ~**1.0%**, requiring **~3,000 hand labels for ~30 hits.** Not a feasible adjudication design.
- Caveats: negatives are from 44 established firms (not the full frame); positives are coded P3 (the usual
  has/lacks-property caution). But the effect sizes are nowhere near the ~30–50× concentration needed, so the
  conclusion is robust to those.

**Spike (a) RUN — richer features tested, verdict unchanged.** Re-pulled the pool with PSC (710 contracts,
100% PSC coverage; `Type of Set Aside` is None throughout — dead end confirmed). R&D-PSC alone: LR 1.6×
(P3 49.3% vs un-flagged 30.8%). Best combination (R&D-PSC + gap∈[−2,+5]): **LR 4.4×**, band ~8.9k contracts
at **~3.0% prevalence → ~1,000 labels for 30 hits**, and the band captures only 29% of Phase IIIs (out-of-band
dark would still need a model). Better than 1.4×, still not a feasible human adjudication design.
**Final posture: accept the bounds** — *141 proven + dark ≈ 1,200–?* (vehicle-stratified floor), miss rate
worsening (17.3% in FY22-25) and structurally concentrated (task orders 22.6%, DCMA 24%) — with the §638
linkage field as the fix rather than better detection. (A future LLM-assisted screen of the ~8.9k band with
human verification of hits could revisit this, but introduces its own validation loop.)

## Sibling enumeration: direct observation of the dark cell (run 2026-07-18, provisional)

**Question that unlocked it (user):** are IDVs themselves coded Phase III, and do task orders inherit?
Answers: **no vehicle carries the code** (0/676 — 10Q lives only on orders), and only 6 of the 141 miscoded
sit under coded-sibling vehicles (the 22.6% task-order miss is not excused by parent-level coverage). But the
coded orders are heavily **vehicle-concentrated** (top IDV `W15QKN13D0099` hosts 185 coded orders; median 3),
and vehicles dedicated to Phase III imply their *unflagged* orders are Phase III by the vehicle's purpose.

**Full census** (all 676 coded-parent IDVs, `/api/v2/idvs/awards/` children, compound (order,parent) keys —
bare-PIID matching silently absorbs "0001"-style collisions and *hid 108 of 125* top-8 unflagged siblings):
30,288 children total; raw unflagged 26,444 — **misleading**, dominated by general-purpose vehicles where one
Phase III order sits among thousands of unrelated orders. Purity (coded/(coded+unflagged)) separates them:

| vehicle purity | vehicles | unflagged siblings |
|---|--:|--:|
| ≥80% | 60 | 115 |
| 50–80% | 95 | 217 |
| 30–50% | 31 | 244 |
| 10–30% | 40 | 440 |
| <10% (general-purpose) | 76 | 25,428 (not credible candidates) |

**High-purity (≥50%) frame: 155 vehicles, 332 unflagged siblings — 129 distinct holder firms, $861M
obligated (median order $500k; ~$775M after excluding an FMS "Miscellaneous Foreign Contractors" attribution
artifact).** For scale: 3.5× the described-undercount dollars (~$244M). The credible direct-observation set.
Sample content: orders procuring the *product of the SBIR* (e.g., GATR inflatable satellite antenna systems,
spares, and training under `W15QKN13D0099`, 185 coded siblings, adjacent order numbers, no code, no SBIR
text). These are observed dark-Phase-III candidates, not model output — at plausibly high precision,
adjudicable by hand (unlike the 0.7%-prevalence random frame). A sibling stratum is added to the blind
adjudication sheet to measure that precision.

Implications if adjudication confirms: (a) a few hundred of the ~1,205 stratified dark scenario become
**headcount**, (b) "sibling-of-coded-under-high-purity-vehicle" is the first viable concentrator
(rank-then-stratify failed at ≤4.4×; this frame is ~50–90% prevalence by construction), and (c) the
mechanism is pinned — the code is dropped **order-by-order on vehicles whose Phase III character is
documented by their own siblings**.

## The fully-dark layer: self-declared Phase III vehicles (run 2026-07-18, provisional)

The sibling census finds vehicles only *via their coded orders* — so a vehicle with zero coded orders is
invisible to it. Probing the 141's parents found 9 such vehicles, **5 of which declare "SBIR PHASE III" in
their own vehicle-level description** while zero orders carry the code. That exposed an unused capture
signal: we had searched *order* descriptions but never *vehicle* descriptions.

**Systematic pull (IDV award types, description "SBIR PHASE III", DoD):**

| | vehicles | of which |
|---|--:|---|
| Self-declared Phase III IDVs | **149** | |
| — hosting ≥1 coded order | 110 | consistent with the sibling census |
| — hosting ZERO coded orders (**fully dark to the code**) | **39** | 39 distinct firms |

**26% of self-declared Phase III vehicles are entirely invisible to the 10Q code** — matching the task-order
(22.6%) and DCMA (24%) miss rates. Children census of the 39: 132 orders — 87 order-text-flagged, **45
unflagged ($53.2M)** — invisible to BOTH order-level signals, captured only by the vehicle's own description
(e.g. HTX Labs `FA302023D0006` "SBIR PHASE III IDIQ", 8 unflagged orders $14.1M).

**Combined direct observation: ~377 unflagged orders / ~$914M** (332/$861M high-purity sibling frame +
45/$53M fully-dark layer), before adjudication.

**REVISES the feasibility gate: a third capture list exists.** The gate searched *order-level* FPDS
competition/set-aside fields and found none — but "order under a self-declared Phase III **vehicle**" is a
structured, high-precision capture rule entered by a different actor at a different moment (vehicle award vs
order entry), plausibly usable as the MSE's third list (with its dependence on the description list
modeled, not assumed away — both are text, but *different records*). A 3-source log-linear fit (code ×
order-description × vehicle-declaration) is now buildable from data in hand.

## Relation to PRs

Extends the undercount work here on #454 (`undercount-award-grain.md`: 141 described-not-coded is exactly the
desc-only capture cell). The detection ranker (#455) can later join as a 4th list. This is the rigorous
version of the "~1,000 dark" figure that has floated as an unmodeled guess.
