# FAST border study: cross-border county-pair comparison

**Reader:** SBIR program-evaluation and state economic-development analysts
assessing whether SBA's Federal and State Technology (FAST) Partnership Program
raises SBIR participation.

**Tier:** `exploratory` — non-citable. No number in this document may be quoted
as a finding about FAST, and no research question becomes answerable on it.

**Window:** FY2010–FY2024. **Status:** design implemented and run. It produces a
stable, robust, nominally significant negative coefficient (about −25%) that
cannot be read as a FAST effect. A placebo on *future* FAST status, fitted
jointly with current status, gives lead coefficients of similar size (−17% to
−22% for Phase I). Most of those lead coefficients are not distinguishable from
zero under randomization inference. The placebo therefore neither shows that
parallel trends holds nor shows that it fails.

> **Correction notice.** The first revision of this document reported −14.6%
> (40 km) and −45.5% (60 km) with randomization-inference p-values of 0.41 and
> 0.17, and attributed the instability to a handful of high-volume border
> metros. Those numbers came from two implementation defects, both now fixed:
> every unordered county pair nominated reciprocally appeared **twice** in
> mirrored orientations while sharing one pair fixed effect, and the design
> matrix dropped a dummy column without adding an intercept, constraining the
> reference pair to an exact 50/50 split. The corrected estimates are stable
> across bandwidth and robust to dropping the largest pairs. The verdict — that
> no credible FAST effect is identified here — is unchanged, but the reason is
> different and better supported.
>
> **Second correction (review of PR #817).** The second revision fitted the
> future-treatment placebo on the lead alone. FAST status is persistent from
> year to year, so a lead fitted alone mostly reproduces the current-year
> coefficient (it reported −24.3% at t+1 against −24.8% current). That
> revision read the match as proof that parallel trends fails and that the
> coefficient measures selection into treatment. The test could not show
> that. The placebo now fits current and lead status together, keeps pairs
> where either one changes, and gives the lead a permutation p-value. Zero
> and negative obligation rows are also no longer counted as treatment
> (section 2). The "selection into treatment" claim is withdrawn: the
> corrected placebo is consistent with a pre-trend but does not establish
> one.

---

## 1. Question and design

Does a state having an active FAST cooperative agreement in a fiscal year raise
SBIR Phase I activity in that state?

Treatment is a state x fiscal year: SBA makes at most one FAST award per state
per year, so there is no finer unit at which it varies. The design follows
Lanahan & Feldman (2018), which identifies state SBIR match effects from policy
discontinuities at state borders: compare counties that sit on opposite sides of
a state line, where one side's state has an active FAST award that year and the
other's does not. Neighbouring counties share labour markets, industry mix and
regional shocks, so the state line isolates the policy.

The variation exists. Across the 108 adjacent state pairs among the contiguous
48 plus DC, the number with **discordant** FAST status averages 47.3 per year
(44%), never falling below 29 across FY2010–2024. (This count was computed
before the treatment rule in section 2 dropped zero and negative obligation
rows, and was not recomputed: the state-adjacency list behind it is not in the
repo.)

### Estimator

Conditional (fixed-effects) Poisson with pair x year fixed effects. With two
units per pair-year the conditional likelihood reduces to a binomial on the
split of awards between the two sides, with pair dummies absorbing the
time-invariant county-quality difference. The coefficient on
`dF = fast_A − fast_B` is the log ratio of expected awards attributable to FAST
availability.

### Inference

Model-based standard errors are **not valid**: treatment is assigned at the
state x year level while observations are county pairs. Inference is
randomization based — the observed FAST year-profiles are permuted across states
and the estimator refit (300 draws), yielding a p-value and a minimum detectable
effect (MDE, 80% power, 5% two-sided).

## 2. Data

| Input | Source | Note |
|---|---|---|
| FAST treatment panel | USAspending assistance listing 59.058 | 330 state-year rows (339 awards), FY2010–2024, 50 states. `data/reference/fast/fast_awards_fy2010_2024.csv`, built by `scripts/usaspending/fetch_fast_awards.py`. USAspending holds no FAST records before FY2010. **Treatment rule:** a state-year counts as funded only when its net `obligated_usd` is above zero. This keeps 314 state-years (322 awards). The 16 dropped rows have zero or negative obligations (13 in FY2016, plus OH 2015, TX 2011, GA 2024); they are most likely deobligation or closeout actions on earlier agreements, not new agreements. They were not checked award by award. |
| SBIR Phase I awards | `data/raw/sbir/award_data.csv` | 59,904 Phase I awards FY2010–2024 in the 50 states plus DC. |
| County + coordinates | PatentsView `g_location_disambiguated.tsv.zip` | Already in-repo; joined on upper-cased city + state. No external crosswalk needed. |

Geocoding matched **57,151 of 59,904 awards (95.4%)** to a county, across 913
distinct counties. Each county is paired with the nearest county centroid in a
different state; the pair is kept if either side has SBIR activity.

## 3. Results

Outcome `p1` is Phase I award counts; `ftw` is first-time Phase I winners. The
estimation sample requires a non-zero pair-year total, within-pair variation in
`dF`, and a non-separated pair.

| Outcome | Band | Pairs | Pair-years | Awards | Estimate | RI p | RI MDE | Drop top-5 pairs |
|---|---|---|---|---|---|---|---|---|
| Phase I | ≤40 km | 72 | 812 | 10,969 | **−25.2%** | 0.04 | 40.7% | −25.3% |
| Phase I | ≤60 km | 125 | 1,416 | 20,410 | **−25.3%** | 0.04 | 42.4% | −25.7% |
| First-time | ≤40 km | 63 | 592 | 3,333 | **−28.9%** | 0.02 | 47.0% | −27.9% |
| First-time | ≤60 km | 105 | 984 | 5,406 | **−27.1%** | 0.03 | 41.8% | −27.8% |

The estimate is stable across bandwidth and outcome (−25% to −29%), survives
dropping the five highest-volume pairs almost unchanged (they carry 34–39% of
awards), and clears conventional significance under randomization inference
(p = 0.02 to 0.04 over 300 draws).
On its face this looks like a well-behaved result saying FAST availability is
associated with about a quarter fewer Phase I awards on the funded side of a
state line.

It cannot be read as a FAST effect, for the reasons below.

### The pre-trend placebo

FAST status *in the future* cannot cause awards *today*. The placebo adds FAST
status led by one, two or three years and fits it **together with** current
status. The lead coefficient is read conditional on current status. A pair
enters the sample when either its current or its lead status changes. The lead
coefficient gets a randomization-inference p-value from the same permutation
of state FAST profiles as the main estimate (300 draws).

| Outcome | Band | Lead | Pair-years | Current status (joint) | **Lead status (joint)** | Lead RI p |
|---|---|---|---|---|---|---|
| Phase I | 40 km | t+1 | 731 | −15.5% | **−21.2%** | 0.047 |
| Phase I | 40 km | t+2 | 657 | −24.4% | **−18.6%** | 0.17 |
| Phase I | 40 km | t+3 | 610 | −28.1% | **−21.7%** | 0.15 |
| Phase I | 60 km | t+1 | 1,290 | −16.9% | **−19.6%** | 0.07 |
| Phase I | 60 km | t+2 | 1,167 | −24.4% | **−17.0%** | 0.22 |
| Phase I | 60 km | t+3 | 1,086 | −28.4% | **−19.9%** | 0.19 |
| First-time | 40 km | t+1 | 531 | −22.7% | **−14.3%** | 0.37 |
| First-time | 40 km | t+2 | 481 | −25.2% | **−14.4%** | 0.44 |
| First-time | 40 km | t+3 | 441 | −28.2% | **−15.9%** | 0.38 |
| First-time | 60 km | t+1 | 898 | −19.2% | **−15.7%** | 0.31 |
| First-time | 60 km | t+2 | 819 | −24.0% | **−7.7%** | 0.67 |
| First-time | 60 km | t+3 | 755 | −26.8% | **−15.9%** | 0.35 |

For comparison, the earlier lead-only fit reported −24.3% (Phase I, 40 km,
t+1) against a current-year −24.8%. That match came from the persistence of
FAST status, not from a pre-trend.

### What that means

- **The lead point estimates are still negative and not small.** For Phase I
  they sit between −17% and −22%, close to the size of the main estimate. That
  is the pattern a pre-trend or selection into FAST would produce.
- **They are mostly not distinguishable from zero.** One of 12 lead
  coefficients has a permutation p-value below 0.05 (Phase I, 40 km, t+1,
  p = 0.047), and one more is below 0.10 (60 km, t+1, p = 0.07). The other 10
  range from 0.15 to 0.67. With 12 tests, one result near 0.05 is about what
  chance alone gives.
- **At a one-year lead the two regressors share the effect.** Adding the t+1
  lead cuts the current-year coefficient from about −25% to −15% to −17%.
  Year-to-year persistence of FAST status makes current and next-year status
  hard to separate, so this split is imprecise.

So the corrected placebo does **not** show that parallel trends fails, and it
does not show that FAST is allocated toward states with weakening SBIR
activity. It also does not clear the design: the test is underpowered (the main
estimate's MDE is about 41% to 47%) and the lead point estimates are the same
sign and similar size as the main estimate. Selection of states into FAST
remains a plausible explanation for the negative coefficient, but this study
does not establish it.

Descriptively, across the 682 discordant pair-years at the 60 km band, the
FAST-funded side averages 6.11 Phase I awards against 6.99 on the unfunded
side — the same gap, visible without any model.

## 4. Verdict

**The design is implementable on public data and does not identify a FAST
effect.** Report as *not assessed* — not as evidence that FAST has no effect,
and emphatically not as evidence that FAST reduces SBIR activity by a quarter.
The coefficient is stable and nominally significant, and it is still
uninterpretable: the placebo leads are of similar size and sign, and the
placebo is too weak either to confirm or to rule out a pre-trend.

Two further cautions that survive the correction:

- **Model-based standard errors remain invalid here.** Treatment is assigned at
  state x fiscal year while observations are county pairs. Any future FAST
  specification reporting model or clustered SEs without a permutation check
  should be treated as wrong.
- **The point estimate sits below its own minimum detectable effect** (−26%
  against an MDE of 41% to 47%). Even setting selection aside, an estimate that
  significant in a design this underpowered is the regime where magnitudes are
  inflated, not a regime for reading effect sizes.

The border design's value was always bias reduction relative to a state-level
panel — holding regional shocks fixed — rather than added power. Power is
governed by the number of independently treated units, still ~51 states however
finely the outcome is sliced. The confound this run cannot exclude is
selection of states into FAST, which operates at exactly the level the border
cannot see. The corrected placebo leaves that confound open; it neither
confirms nor rules it out.

### What this run rules in and out

- **Out:** state-level and border-level designs on public award counts, as a
  route to a citable FAST effect. Any design whose treatment varies only at
  state x year is exposed to the selection problem described above, and has
  too few treated units to test for it with useful power; a credible
  estimate needs either variation within state-year or an explicit model of
  how SBA allocates FAST.
- **In, and now higher priority:** the voluntary referral-election design, if
  SBIR submitters elect referral to a FAST site and that field is recoverable —
  it moves treatment to the firm level, where 3,703 firms are observed in both a
  FAST-funded and an unfunded state-year. The decisive question is whether the
  election is recorded at registration, at proposal submission, or only on
  awards; only the submission case yields a frame including non-winners.
- **In:** the Phase 0 sub-grant regression discontinuity, using grantee-held
  scored applications with rejected applicants.
- **Required regardless:** state-level proposal counts by fiscal year. FAST acts
  on proposals; awards = proposals x win rate. Without proposals no award-based
  design can separate "no effect" from "more proposals of lower average quality."

## 5. Reproduce

```bash
python scripts/usaspending/fetch_fast_awards.py \
    --out data/reference/fast/fast_awards_fy2010_2024.csv

python scripts/research/fast_border_study.py \
    --awards data/raw/sbir/award_data.csv \
    --locations data/raw/uspto/patentsview/g_location_disambiguated.tsv.zip \
    --fast data/reference/fast/fast_awards_fy2010_2024.csv \
    --bands 40 60 --outcomes p1 ftw --draws 300 --out reports/fast-border/
```

Randomization inference is seeded (`seed=5`); permutation draws are
reproducible. The run takes about 7 minutes on a laptop; most of it is the
permutation draws for the 12 placebo fits. Award year 2025 is a partial vintage in the award file and is
outside the window by construction.

## 6. Limitations

- FAST services are not geographically rivalrous: a grantee may serve its whole
  state and border firms may reach a neighbouring state's programming or an
  SBDC. The treatment contrast is attenuated by an unmeasured amount.
- The treatment panel starts at FY2010. FY2001–2009 is outside USAspending
  coverage and absent here.
- County assignment uses PatentsView's disambiguated city list; 4.6% of awards
  did not match and are dropped, and that attrition is not profiled by state.
- "Nearest out-of-state county" is a proxy for border adjacency; it is not a
  shared-boundary test.
- Massachusetts and Rhode Island are never treated in the window, so they
  contribute only as control mass.
- The pre-trend placebo is underpowered. It can neither confirm nor rule out
  a pre-trend, and it does not say how much of the coefficient is selection.
  Decomposing that needs a model of FAST allocation, which this study does not
  build.
- Pairs whose `dF` never changes, and pairs with all-or-nothing outcomes, are
  dropped as uninformative under the pair fixed effect. At the 60 km band this
  leaves 125 of the 439 unordered pairs within the band (1,273 pairs at any
  distance).

## 7. References

- Lanahan, L. & Feldman, M. P. (2018). "Approximating Exogenous Variation in
  R&D: Evidence from the Kentucky and North Carolina SBIR State Match Programs."
  *Review of Economics and Statistics* 100(4), 740–752.
  doi:10.1162/rest_a_00681
- Lanahan, L. & Feldman, M. P. (2015). "Multilevel innovation policy mix."
  *Research Policy* 44(7), 1387–1402. doi:10.1016/j.respol.2015.04.002
