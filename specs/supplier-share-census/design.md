# Supplier-Share Census Frozen Design

**Revision:** 0
**Target tier:** exploratory / non-citable
**Research question:** F2, supplier-track share of the SBIR/STTR portfolio
**Status:** frozen for exploratory implementation; validation gates remain open

## Neutral Definition And Estimand

The population of interest is **sustained federal performers**: canonical SBIR/STTR firm
envelopes with at least one observed federal-persistence criterion and no observed venture
signal, where required venture channels were actually searchable.

**Declared estimand:** For each frozen `(T, N, window)` cell, among canonical SBIR/STTR firms
whose first observed award is at least `window` calendar years before the declared as-of year,
estimate (a) the fraction of firms and (b) the fraction of cumulative observed SBIR/STTR award
dollars in each federal-persistence x venture-signal cell. The primary descriptive quantity is
the persistent + no-observed-venture cell. Cumulative dollars include every observed award to an
eligible firm, not only awards inside the minimum observation window.

This estimand describes observed records. It does not estimate what firms would have done without
SBIR/STTR, whether firms are commercially successful, or whether an awardee is a "mill."

## Current Machinery: Active Versus Gated

| Component | Registry state | Use here |
|---|---|---|
| `phase-iii-census` | Active; reproducible, not citable | Reuse release-eligible materialized award/contract inputs only |
| `phase-iii-source-materialization` | Maintenance | Canonical SBIR.gov source parquet |
| completed Form D pipeline | Archived completed feature | Consume existing high-confidence records and scoring; no new matcher |
| completed Form D + EFTS M&A detector | Archived completed feature | Consume final high/medium event tiers as data |
| `agency-private-capital-comparison` | Active, Phase 2 gated | Reuse input adapters only; do not revive its gated comparison |
| `ma-discovery-integration` | Deferred | No web-search recall expansion |
| `phase-iii-hand-label-validation` | Gated backlog | Do not implement; this census has its own exploratory review packet |

## Denominator And Identity

The input is `data/processed/phase_iii_census_sbir_awards.parquet`, verified by its existing source
materialization check. Every retained row with a nonblank `company_name` enters. Source company
labels are assigned to canonical envelopes by `build_canonical_company_map(...,
policy=CanonicalMergePolicy.PRELOAD_V1)`. The readout reports both counts so the legacy M&A-study
denominator (34,460 labels in the design-time source cut) reconciles to the current envelope count.

External records resolve to an envelope in this order:

1. unique exact normalized UEI;
2. if no UEI match, unique exact DUNS digits;
3. if neither identifier matches, unique existing normalized award-name alias;
4. otherwise unmatched or ambiguous.

There is no fuzzy comparison, manual alias, transitive repair, or post-result adjudication in the
classification path. Form D and M&A records have already passed their upstream matching rules;
the name step only attaches their recorded SBIR company label to its existing envelope.

Public products use `firm_id = first 20 hex characters of SHA-256("supplier-share-v1\\0" +
canonical firm key)`. Names and identifiers appear only in an ignored private validation packet.

## Time And Dollar Rules

- `as_of_year` is explicit in the run manifest and defaults to the maximum valid SBIR award year.
- `observation_years = as_of_year - first_award_year` at calendar-year resolution.
- A firm is headline-eligible when `observation_years >= window`.
- The minimum window is a maturity gate. Criteria and dollars use all history through the input
  data cut; they are not truncated at year 12 or 15.
- Award count is the number of retained materialized SBIR.gov source rows assigned to the firm.
- Award dollars are parsed from `award_amount`; missing or invalid amounts contribute neither
  dollars nor a zero. Coverage is reported.
- Firm-level agency dollars retain the award's agency. Agency firm counts are distinct firms with
  at least one award in that agency group, so agency firm counts are not additive across groups.

## Frozen Grid

The complete grid is the Cartesian product:

```text
T = 8, 10, 12 years
N = 4, 6, 10 awards
window = 12, 15 years
```

All 18 cells are mandatory. The central descriptive cell is `(T=10, N=6, window=15)`. No grid
cell may be selected or omitted based on its result.

## Axis 1: Observed Federal Persistence

The clauses execute in this order and every clause result is retained:

1. **P0 — maturity:** `observation_years >= window` (headline eligibility only).
2. **P1 — tenure:** `last_award_year - first_award_year >= T`.
3. **P2 — award volume:** `award_count >= N`.
4. **P3 — contract continuation:** positive net signed prime obligations after the firm's earliest
   explicit Phase II `contract_end_date` and no later than the contract source cutoff. Contract
   rows with no exact firm match or firms with no explicit Phase II completion anchor cannot fire
   P3. No completion date is imputed.
5. **P4 — axis:** `federal_persistent = P1 OR P2 OR P3`.

P3 uses an already materialized prime-contract transaction parquet when supplied. FPDS sees
primes only. The input manifest records its date range and whether it is a full-history or partial
snapshot. Failure to observe P3 is not proof of no federal continuation.

## Axis 2: Observed Venture Signal

The clauses execute in this order:

1. **V1 — Form D:** at least one existing `high` match after the existing excluded-industry and
   false-positive filters. Medium and low matches do not fire V1.
2. **V2 — M&A:** at least one existing final `high` or `medium` event from the two-tier Form D +
   EFTS method. Low events do not fire V2.
3. **V3 — optional IPO:** at least one supplied EDGAR registration-statement signal (`S-1`,
   `S-1/A`, `F-1`, or `F-1/A`). Absence of this optional input does not make the required axis
   unsearchable.
4. **V4 — presence:** `venture_signal = V1 OR V2 OR V3`.
5. **V5 — typed absence precedence:**
   - positive V4 -> `signal_present`;
   - otherwise P0 false -> `window_censored`;
   - otherwise either required Form D or M&A channel not searchable -> `not_searchable`, with
     channel-specific detail;
   - otherwise -> `no_filing_found`.

Positive signals remain positive even for young cohorts, but young firms are excluded from the
headline. A required channel may be declared globally searchable only by an explicit run argument
recorded in the manifest; otherwise per-firm searchable coverage must come from an input artifact.

## Matrix And Stratifications

For headline-eligible firms with V5 equal to `signal_present` or `no_filing_found`, the four cells
are:

```text
persistent_venture
persistent_no_venture
not_persistent_venture
not_persistent_no_venture
```

Every other firm is retained as `persistent_unknown_venture` or
`not_persistent_unknown_venture`. The headline is suppressed unless both required venture
channels are searchable for every headline-eligible firm in that grid cell.

The normalized summary reports:

- overall;
- agency groups `DoD`, `HHS`, `NSF`, and `other`, using each award's source agency;
- each first-award year;
- full-history award-count strata `1`, `2-5`, `6-20`, `21+`.

Cumulative-dollar deciles are assigned over headline-eligible firms by descending firm cumulative
award dollars, deterministic ties broken by `firm_id`. The concentration statistic is the share
of persistent-no-venture dollars held by the first `ceil(n/10)` firms in that supplier cell. It is
not a market-concentration statistic.

## Output Contract

Authoritative Parquet grain is one pseudonymous canonical firm x grid cell. Required fields
include input provenance IDs, grid parameters, eligibility, P1-P3, V1-V3, required-channel
searchability, V5, matrix cell, award/dollar fields, agency-dollar fields, `validation_status`, and
`citable=false`.

The single summary CSV has one schema across overall, agency, cohort, and award-count rows. Counts
and dollars reconcile to the authoritative Parquet under the declared stratum semantics. The SVG
plots first-award-year supplier-dollar shares for central `T/N`, shades the minimum/maximum across
all nine `T/N` combinations, and marks both maturity cutoffs. When venture measurement is blocked,
the SVG says so instead of plotting zeros.

## Validation Gates

### Gate 1: stratified hand review

Once every measurable cell is populated, draw 50 firms with seed `20260821`: 13 each from
`persistent_no_venture` and `persistent_venture`, and 12 each from the two nonpersistent cells.
If a cell has fewer rows, redistribute the remainder in frozen cell order. Sampling is uniform
within cell after sorting by `firm_id`. The named packet is private and ignored; the public result
contains cell-level agreement only.

### Gate 2: face-validity anchors

Anchors are supplied in a separate review file with expected persistence and venture axes. The
producer reports aggregate agreement and never uses anchors to alter classification. No anchors
are embedded in this initial freeze; the readout must say `not run` until a reviewed list is
provided.

### Gate 3: negative-control diagnostics

For mature, venture-measurable firms, permute the venture axis within `agency group x five-year
first-award cohort` using seed `20260821`, preserving block-level prevalence. Report the placebo
persistent-no-venture dollar share and its difference from observed. No pass threshold is inferred
from the result; review must approve one before promotion. Classifier functions must not receive
award dollars, agency strata, anchor expectations, or hand labels when assigning either axis
(arm-blindness by interface).

`validation_status` progresses only through explicit supplied review artifacts. A successful
exploratory run remains `citable=false`; promotion requires a separate evidence contract with
input SHA enforcement and blocking checks.

## Required Limitations

- FPDS/USAspending sees prime awards only; sub-tier supply to primes is invisible, biasing observed
  federal continuation downward.
- Coded Phase III undercounts actual Phase III, also biasing observed continuation downward.
- Form D absence is not absence of capital. Bootstrapped growth, bank/debt finance, revenue-funded
  scaling, private offerings not detected by the match, and non-Reg-D capital can make the
  persistent-no-venture cell too large.
- Form D and EFTS coverage varies over time; young cohorts are right-censored and old cohorts can
  be left-censored by electronic filing coverage.
- Award-time firm identity does not establish current corporate identity. Acquisitions, successors,
  aliases, and affiliate structure can split or combine apparent firms.
- Cumulative dollars are nominal observed award amounts, not inflation-adjusted obligations or
  firm revenue.
- The two federal-continuation undercounts and venture-signal undercount work in opposite
  directions. The net bias in the supplier share is ambiguous.

## Naming And Dual Reading

| Candidate label | Connotation and caution |
|---|---|
| Sustained federal performers | Neutral preferred label; describes observed persistence without claiming dependence or intent |
| Mission suppliers | Emphasizes capability delivery; can overstate whether awards map to an operational mission |
| Federal R&D incumbents | Conveys tenure and repeat participation; can imply market power not measured here |
| Supplier-track awardees | Useful contrast with venture-track branding; "track" can falsely imply a chosen strategy |
| Federal-continuity firms | Mechanically accurate but abstract; does not imply commercial failure |

**Mandatory dual-reading caution:** A large persistent-no-venture share can be read as evidence of
a durable federal R&D supplier base. The same number can be described pejoratively as a "mills
share." The classifier supports neither value judgment: it measures observed federal persistence
and observed venture signals under asymmetric public-data coverage.

## What Would Make The Estimate Wrong

- Treating an unavailable Form D/EFTS channel as a measured zero.
- Changing high/high-plus-medium upstream thresholds or applying a new fuzzy match.
- Counting source labels as independent firms without the frozen envelope reconciliation.
- Letting award dollars, agency, or validation labels influence classification.
- Selecting a preferred grid cell after viewing results.
- Describing the persistent-no-venture cell as noncommercial, dependent, or legally ineligible.
