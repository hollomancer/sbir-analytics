# FAST border study: cross-border county-pair comparison

**Reader:** SBIR program-evaluation and state economic-development analysts
assessing whether SBA's Federal and State Technology (FAST) Partnership Program
raises SBIR participation.

**Tier:** `exploratory` — non-citable. No number in this document may be quoted
as a finding about FAST, and no research question becomes answerable on it.

**Window:** FY2010–FY2024. **Status:** design implemented and run. It produces a
stable, robust, nominally significant negative coefficient that is **not** a
FAST effect: a placebo using *future* treatment recovers most of it, so the
design's parallel-trends assumption fails.

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
(44%), never falling below 29 across FY2010–2024.

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
| FAST treatment panel | USAspending assistance listing 59.058 | 339 awards, FY2010–2024, 50 states. `data/reference/fast/fast_awards_fy2010_2024.csv`, built by `scripts/usaspending/fetch_fast_awards.py`. USAspending holds no FAST records before FY2010. |
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
| Phase I | ≤40 km | 71 | 810 | 10,967 | **−25.8%** | 0.015 | 38.0% | −25.2% |
| Phase I | ≤60 km | 122 | 1,408 | 20,402 | **−25.8%** | 0.028 | 39.7% | −25.8% |
| First-time | ≤40 km | 62 | 590 | 3,331 | **−29.1%** | 0.020 | 44.3% | −28.1% |
| First-time | ≤60 km | 103 | 979 | 5,401 | **−26.5%** | 0.025 | 39.4% | −26.5% |

The estimate is stable across bandwidth and outcome (−26% to −29%), survives
dropping the five highest-volume pairs almost unchanged (they carry 34–39% of
awards), and clears conventional significance under randomization inference.
On its face this looks like a well-behaved result saying FAST availability is
associated with about a quarter fewer Phase I awards on the funded side of a
state line.

It is not a FAST effect.

### The pre-trend placebo

FAST status *in the future* cannot cause awards *today*. Re-estimating with the
treatment indicator led by one, two and three years:

| Outcome | Band | Lead | Current-year estimate | **Future-treatment estimate** |
|---|---|---|---|---|
| Phase I | 40 km | t+1 | −24.8% | **−24.3%** |
| Phase I | 40 km | t+2 | −29.4% | **−20.4%** |
| Phase I | 40 km | t+3 | −31.4% | **−23.0%** |
| Phase I | 60 km | t+1 | −25.0% | **−23.3%** |
| Phase I | 60 km | t+2 | −28.9% | **−18.9%** |
| Phase I | 60 km | t+3 | −31.0% | **−20.4%** |
| First-time | 60 km | t+2 | −25.3% | **−12.0%** |

At a one-year lead the placebo coefficient is almost identical to the
contemporaneous one. At two and three years it remains large and negative. A
state's SBIR activity relative to its cross-border neighbour is already
depressed well before FAST arrives.

### What that means

The negative coefficient measures **selection into treatment**, not the effect
of treatment. FAST is allocated toward states with weak or deteriorating SBIR
activity — which is what a capacity-building program is supposed to do — and
states plausibly apply when their pipeline is thin. The border design controls
for shocks common to a *region*; it does nothing about a state being selected
into FAST on the basis of its own SBIR trajectory. Parallel trends fails, and
with it the identifying assumption.

Descriptively, across the 719 discordant pair-years at the 60 km band, the
FAST-funded side averages 6.16 Phase I awards against 6.93 on the unfunded
side — the same gap, visible without any model.

## 4. Verdict

**The design is implementable on public data and does not identify a FAST
effect.** Report as *not assessed* — not as evidence that FAST has no effect,
and emphatically not as evidence that FAST reduces SBIR activity by a quarter.
The coefficient is stable and nominally significant, and it is still
uninterpretable, because a placebo on future treatment reproduces most of it.

Two further cautions that survive the correction:

- **Model-based standard errors remain invalid here.** Treatment is assigned at
  state x fiscal year while observations are county pairs. Any future FAST
  specification reporting model or clustered SEs without a permutation check
  should be treated as wrong.
- **The point estimate sits below its own minimum detectable effect** (−26%
  against an MDE near 39%). Even setting selection aside, an estimate that
  significant in a design this underpowered is the regime where magnitudes are
  inflated, not a regime for reading effect sizes.

The border design's value was always bias reduction relative to a state-level
panel — holding regional shocks fixed — rather than added power. Power is
governed by the number of independently treated units, still ~51 states however
finely the outcome is sliced. This run shows that the bias it removes is not
the bias that matters: the binding confound is selection of states into FAST,
which operates at exactly the level the border cannot see.

### What this run rules in and out

- **Out:** state-level and border-level designs on public award counts, as a
  route to a citable FAST effect. Any design whose treatment varies only at
  state x year inherits the selection problem demonstrated above; a credible
  estimate needs either variation within state-year or an explicit model of
  how SBA allocates FAST.
- **In, and now higher priority:** the voluntary referral-election design, if
  SBIR submitters elect referral to a FAST site and that field is recoverable —
  it moves treatment to the firm level, where 3,804 firms are observed in both a
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
    --bands 40 60 --outcomes p1 --draws 300 --out reports/fast-border/
```

Randomization inference is seeded (`seed=3`); permutation draws are
reproducible. Award year 2025 is a partial vintage in the award file and is
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
- The pre-trend placebo demonstrates that parallel trends fails; it does not
  quantify how much of the coefficient is selection. Decomposing that needs a
  model of FAST allocation, which this study does not build.
- Pairs whose `dF` never changes, and pairs with all-or-nothing outcomes, are
  dropped as uninformative under the pair fixed effect. At the 60 km band this
  leaves 122 of 1,298 unordered pairs.

## 7. References

- Lanahan, L. & Feldman, M. P. (2018). "Approximating Exogenous Variation in
  R&D: Evidence from the Kentucky and North Carolina SBIR State Match Programs."
  *Review of Economics and Statistics* 100(4), 740–752.
  doi:10.1162/rest_a_00681
- Lanahan, L. & Feldman, M. P. (2015). "Multilevel innovation policy mix."
  *Research Policy* 44(7), 1387–1402. doi:10.1016/j.respol.2015.04.002
