# FAST border study: cross-border county-pair comparison

**Reader:** SBIR program-evaluation and state economic-development analysts
assessing whether SBA's Federal and State Technology (FAST) Partnership Program
raises SBIR participation.

**Tier:** `exploratory` — non-citable. No number in this document may be quoted
as a finding about FAST, and no research question becomes answerable on it.

**Window:** FY2010–FY2024. **Status:** design implemented and run; the estimand
was **not** identified at usable precision. See the verdict.

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

Outcome: Phase I award counts. Estimation sample requires a non-zero pair-year
total and within-pair variation in `dF`.

| Band | Pairs | Pair-years | Awards | Point estimate | Model SE | RI p-value | RI MDE |
|---|---|---|---|---|---|---|---|
| ≤40 km | 157 | 2,051 | 19,228 | **−14.6%** | 0.0245 | **0.41** | 49.1% |
| ≤60 km | 309 | 3,814 | 40,113 | **−45.5%** | 0.0192 | **0.17** | 121.7% |

Three things to read off this table.

1. **Nothing is distinguishable from zero.** Randomization-inference p-values are
   0.41 and 0.17. The MDEs — 49% and 122% — are far larger than any effect a
   $125k–$180k annual grant could produce.
2. **Model standard errors are catastrophically wrong here.** At the 60 km band
   the model SE of 0.019 against a coefficient of −0.607 implies a t-statistic
   above 30. Reported naively this would read as overwhelming evidence that FAST
   *reduces* SBIR activity by 45%. Randomization inference puts the same estimate
   at p = 0.17. Any future FAST specification that reports clustered or
   model-based SEs without a permutation check should be treated as wrong.
3. **The estimate is not stable.** Widening the band from 40 km to 60 km moves
   the point estimate from −15% to −46%. A design returning an effect that
   triples with a bandwidth change is not measuring the policy.

### Why it is unstable

Five county pairs carry **36.8%** of all awards in the 60 km sample:

| Pair | Awards |
|---|---|
| MA–NH (two distinct county pairs) | 8,748 and 1,486 |
| AL–TN | 2,078 |
| DC–MD | 1,386 |
| NH–VT | 1,050 |

Dropping those five pairs moves the estimate from **−45.5% to −3.7%** — a swing
of 42 percentage points. The same check at the 40 km band moves the estimate from
**−14.6% to +1.6%**, with the top five pairs carrying 30.3% of that sample's
awards. In both bands the estimate collapses to approximately zero once the
highest-volume border metros are removed, and even changes sign at 40 km.

The dominant pair is Massachusetts–New Hampshire, and
**Massachusetts is one of only two states (with Rhode Island) never FAST-funded
in FY2010–2024**. The headline "effect" is therefore close to a comparison of
the densest SBIR cluster in the country against its neighbour, loaded onto the
FAST indicator because Massachusetts is permanently untreated. That is a
structural feature of using SBIR award counts on a border design, not a
correctable outlier.

## 4. Verdict

**The design is implementable on public data and does not identify a FAST
effect.** Report as *not assessed at this power* — not as evidence that FAST has
no effect, and emphatically not as evidence of a negative effect.

The border design's value was always bias reduction — holding regional shocks
fixed — rather than added power. Power is governed by the number of
independently treated units, and that is still ~51 states however finely the
outcome is sliced. The county-pair machinery sharpens the comparison without
changing that arithmetic.

### What this run rules in and out

- **Out:** state-level and border-level designs on public award counts, as a
  route to a citable FAST effect.
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

## 7. References

- Lanahan, L. & Feldman, M. P. (2018). "Approximating Exogenous Variation in
  R&D: Evidence from the Kentucky and North Carolina SBIR State Match Programs."
  *Review of Economics and Statistics* 100(4), 740–752.
  doi:10.1162/rest_a_00681
- Lanahan, L. & Feldman, M. P. (2015). "Multilevel innovation policy mix."
  *Research Policy* 44(7), 1387–1402. doi:10.1016/j.respol.2015.04.002
