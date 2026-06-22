# SBA Commercialization Rate Benchmark — Methodology

This document describes how a per-firm audit harness — `scripts/data/run_commercialization_benchmark.py` paired with `scripts/data/audit_one_firm.py` — computes a public-data approximation of the SBA Commercialization Rate Benchmark for SBIR/STTR firms, with explicit citations to the governing statute, regulation, and SBA guidance.

It also documents where our methodology diverges from the authoritative SBA process and why.

## Implementation status — read this first

The audit harness this doc describes (`run_commercialization_benchmark.py`, `audit_one_firm.py`, the FY2026 audited CSV at `reports/validation/commercialization_benchmark_eval_fy2026.csv`) is **local-only / not committed to this repo**. It exists on the author's machine and was used to produce the FY2026 figures cited below (143 cohort firms, 28 Tier-1/2 firms, 2 dual-penalty firms).

The shippable counterpart on `main` is `scripts/run_benchmark.py` + `sbir_etl/models/benchmark_models.py`, which implements the same statutory framework (§638(qq) tier thresholds, 10-FY window, cohort selection) via a different CLI shape (`evaluate` / `sensitivity` / `company` subcommands). It does not currently produce per-firm audit JSON files or do the USAspending + Form D proxy substitution the harness does.

This doc is committed as the **methodology record** so the audit-harness logic is auditable and reproducible, even before the harness itself ships. **Future work**: migrate the harness into `scripts/run_benchmark.py` (or alongside it under `packages/sbir-analytics/`) so the cited file paths resolve and the run is reproducible from `main`. See research-questions.md "Output products" section for the broader status.

## Authoritative sources

| Source | Use |
|---|---|
| **15 U.S.C. § 638(mm)** — Performance Standards | Standard tier eligibility and threshold |
| **15 U.S.C. § 638(qq)(3)** — Increased Minimum Performance Standards / "covered sale" definition | Tier 1/2 eligibility, threshold, and federal-fund exclusion |
| **SBA Performance Benchmark Requirements** (sbir.gov/performance-benchmarks) | Operational rules: 10-FY window for all tiers, dollar thresholds, patent path |
| **Completing the Company Commercialization Report — Instructions and Definitions** (PDF on sbir.gov) | Defines what counts as "sales" vs "additional investment" vs "Phase III contracts"; Do's and Don'ts |
| **SBA Policy Directive (May 2023)** | Background context; the statutory rules take precedence |

The **Company Commercialization Report (CCR)** that SBA uses for actual benchmark determinations is firm-self-reported through SBIR.gov's "My Dashboard" and is **not publicly downloadable**. Our work substitutes public proxies (USAspending obligations + SEC Form D offerings) for the firm-reported sales and investment data.

## Cohort selection

A firm is included if it has **≥16 Phase II awards in the past 10 fiscal years, excluding the 2 most recently completed FYs**. For FY2026 eval, that window is **FY2014–FY2023**.

This matches SBA's published rule: *"The Commercialization Rate Benchmark only applies when a company has received 16 or more Phase II awards during the past ten fiscal years, excluding the two most recently completed fiscal years."*

Source: `data/raw/sbir/award_data.csv` (SBIR.gov award export). The cohort SQL is in `load_cohort` and aggregates by UEI.

## Tier classification

All three tiers use the **same 10-FY window** for both the P2-count threshold and the per-Phase-II denominator. Tier assignment in `assign_firm_window`:

| Tier | P2 count in 10-FY | Threshold | Federal $ in sales? | Patent path? |
|---|---|---|---|---|
| Standard | ≥16 | $100K / P2 | Yes (per CCR Sales + Additional Investment buckets) | Yes (≥15% / P2) |
| Tier 1 | ≥51 | $250K / P2 | **No** (covered-sale rule) | No |
| Tier 2 | ≥101 | $450K / P2 | **No** (covered-sale rule) | No |

The 5-FY "covered period" defined in §638(qq) applies to the **Phase I→Phase II Transition** increased standard, **not** to the Commercialization Rate Benchmark — confirmed by SBA's published guidance which states Tier 1/2 use "the past ten fiscal years, excluding the two most recently completed fiscal years."

## "Covered sale" rule at Tier 1/2

Per **15 U.S.C. § 638(qq)(3)(B)(iii)(II)**, a "covered sale" is:

> "a sale by a small business concern —
>   (aa) that the small business concern claims to be attributable to an SBIR or STTR award;
>   (bb) **for which no amount of the payment was or is made using Federal funds**;
>   (cc) which the small business concern uses to meet an applicable increased minimum performance standard…
>   (dd) that was or is received during the 5 fiscal years immediately preceding the fiscal year in which the small business concern uses the sale to meet the increased minimum performance standard."

SBA reinforces this on the performance-benchmarks page:

> "Government awards received as a prime or subcontractor that satisfy the definition of Phase III…are not considered covered sales because the payment was or is made using Federal funds."

The script implements this by computing the Tier 1/2 threshold numerator as `Form D / P2 count` only — federal $ is structurally excluded by the covered-sale definition. (Calling Form D "sales" would be a misnomer here; under §638(qq) the federal-excluded numerator collapses to just the private-investment component.)

## Dual-compliance verdicts per firm

§638(mm) and §638(qq) are **layered, not mutually exclusive**. A firm with ≥51 P2 awards is subject to BOTH the Standard rule (must clear $100K/P2) AND the Increased rule (must clear $250K/$450K/P2 on non-federal only). They can fail one, the other, or both — and the consequences stack.

The script writes one verdict per (regime × reading), giving up to four verdicts per firm:

| Column | Regime | Reading | Populated for |
|---|---|---|---|
| `standard_net_status` | §638(mm) | broad (federal counts as investment, own SBIR subtracted) | all 143 firms |
| `standard_strict_status` | §638(mm) | strict (non-R&D contracts only; Form D only) | all 143 firms |
| `increased_net_status` | §638(qq) | broad (federal excluded; Form D only) | 28 firms with P2 ≥ 51 |
| `increased_strict_status` | §638(qq) | strict (same as net — federal excluded) | 28 firms with P2 ≥ 51 |

### Standard tier (`standard_*`) — applies to every firm in the cohort

**§638(mm) reading "net broad" (CCR-aligned):**
Counted dollars = `(federal_observed − own_sbir_total)` (clamped to 0) `+` filtered Form D. Threshold $100K/P2. The first term lands in CCR's "Additional Investment" bucket (follow-on federal contracts/grants); the Form D term lands in CCR's investment bucket too. Both are summed into the `standard_net_sales_counted_usd` column.

This matches CCR Do/Don't #1 ("Do not include Phase I or Phase II SBIR/STTR awards in sales or investment") and the broad operational reading: follow-on federal R&D contracts/grants count under "Additional Investment" because SBA's CCR system auto-populates DoD contracts and "Other Federal Contracts/Grants" as investment.

**§638(mm) reading "strict CCR":**
Counted dollars = non-R&D-NAICS contracts `+` filtered Form D. Threshold $100K/P2. Same column structure as net broad (sums both terms into `standard_strict_sales_counted_usd`) but excludes R&D-NAICS contracts and grants entirely from the federal term.

The CCR Sales definition explicitly excludes "revenue from any other R&D activities, including follow-on R&D contracts or grants." Under the strict reading those dollars don't count at all.

R&D NAICS codes (constant `RD_NAICS`):

| NAICS | Description |
|---|---|
| 541713 | R&D in Nanotechnology |
| 541714 | R&D in Biotechnology (except Nanobiotechnology) |
| 541715 | R&D in the Physical, Engineering, and Life Sciences |
| 541720 | R&D in the Social Sciences and Humanities |
| 541711 | (Pre-2017) R&D in Biotechnology |
| 541712 | (Pre-2017) R&D in the Physical, Engineering, and Life Sciences |

### Increased tier (`increased_*`) — applies only when P2 ≥ 51

Both readings (net and strict) reduce to **`Form D / P2`** because the covered-sale rule excludes all federal $ from the threshold. The two columns are still emitted for schema symmetry but will show the same verdict.

### Why gross broad was dropped

An earlier schema also reported `gross_status` (no own-SBIR subtraction). That reading violates CCR Do/Don't #1 by counting Phase I/II SBIR awards as sales — it is **not a defensible CCR verdict** and was retained only as a methodological upper bound. The current schema omits it. The `net` reading is the lowest-friction CCR-aligned reading.

### Phase III credit (not in the script — post-hoc analysis only)

SBA puts Government Phase III contracts in their own bucket that counts toward total commercialization (Do/Don't #6). Many Phase III contracts are classified under R&D NAICS in FPDS, so the strict reading over-excludes them. A "strict + Phase III credit" view can be derived by joining the CSV to `data/processed/sbir_phase3/usaspending_phase3_contracts.jsonl`. This dataset is built from USAspending text-search on `description="SBIR Phase III"`, which catches ~32% of true Phase III on the DoD side per `lookup_sbir_contracts_in_usaspending.py`. **Treat the strict+P3 number as a conservative lower bound** between net and strict.

## Dual-penalty firms — failing both regimes

Firms in the `increased_*` cohort (P2 ≥ 51) that also FAIL their `standard_net_status` face **both** statutory consequences in the next FY:

- §638(mm)(2): ineligible for Phase I awards for 1 year
- §638(qq): capped at 20 SBIR/STTR awards per agency

In our FY2026 run, 2 firms hit this dual-penalty state under net broad: **NanoSonic** (VA, tier 1, 69 P2) and **Nanohmics** (TX, tier 1, 54 P2). Both have ~95% of their federal revenue derived from their own SBIR P1+P2 awards and zero Form D capital. Under strict CCR the dual-penalty count expands materially.

## Sales proxy: USAspending

Three USAspending API calls per firm, all to `/api/v2/search/spending_over_time/` grouped by fiscal year:

1. **Contracts (FPDS)** — `award_type_codes = ["A","B","C","D"]`. Returns prime-recipient action obligations on procurement contracts.
2. **Contracts under R&D NAICS** — same as #1 plus `naics_codes = RD_NAICS`. Used to derive the non-R&D residual.
3. **Grants (FABS)** — `award_type_codes = ["02","03","04","05"]`. Returns prime-recipient obligations on grants, cooperative agreements, direct payments, loans.

Filter on UEI: `recipient_search_text = [uei]`. The endpoint returns **obligations**, not outlays (per Do/Don't #5: *"For sales to or investment by the government, count only the amount of government funding that has been obligated to date"*).

Throttle: 1 second base sleep between calls, exponential backoff on 429/5xx. On 5 consecutive failures: row marked `status="API_ERROR"` and an `*_api_ok=false` flag is set on the affected call.

**FABS grants do not carry NAICS codes**, so the strict-CCR view treats all grants as R&D-by-default (a conservative simplification; most NIH/NSF/DoE grants to SBIR firms are R&D project grants under CFDA codes like 47.041, 93.286).

## Investment proxy: SEC Form D

Source: `data/form_d_details.jsonl`, enriched with `match_confidence` (high/medium/low) by prior pipeline work.

Each cohort firm is matched on `UPPER(TRIM(company_name)) = UPPER(TRIM(firm))`. To suppress cross-state name collisions (e.g., NANOHMICS INC of TX matching NantOmics LLC of CA), an offering is included **only if**:

- The filing's state matches the SBIR firm's USPS state code, **OR**
- The Form D enricher tagged it `match_confidence.tier = "high"`

This filter dropped 14 false-positive matches representing $421M of "investment" from an earlier unfiltered run. Final cohort match rate: **6 of 143 firms (4%)** have any Form D credit. All 6 are Standard tier; **zero Tier 1/2 firms have Form D credit**.

**Known structural undercount**: Form D covers Reg D securities offerings only. Misses bank loans, convertible notes outside Reg D, M&A proceeds, foreign rounds, and companies that file 10-K instead (Luna Innovations is publicly traded). The CCR captures these via self-report; we cannot.

## Patents path: not implemented

CCR Standard tier allows passing via ≥15% patents per P2 as an alternative to the dollar threshold. The script does not test this path because USPTO data on this branch is fixture-only — ingestion has not been run. None of our 115 Standard-tier passes need the patent path under our dollar calculation, but a firm we report as Standard FAIL could potentially be a patent-path PASS.

## Known divergences from the authoritative SBA process

| Divergence | Direction of bias | Mitigation |
|---|---|---|
| Public obligations vs. firm-reported sales | Sales = obligations is closer to "what SBA could verify" but misses commercial product sales | Strict view labels this; CCR is firm-self-reported and includes channels we can't see |
| FABS grants treated as R&D in strict view | Slightly conservative (under-counts non-R&D grants) | Documented; rare for SBIR firms |
| Phase III credit via description text search (~32% recall on DoD) | Under-credits firms with Phase III activity | Use net broad as the upper-bound CCR-aligned verdict; treat strict as floor |
| No patent path | Under-counts standard tier passes that would qualify on patents | Document explicitly |
| Form D as the only private capital proxy | Under-counts firms raising via 10-K, M&A, bank debt, etc. | Document; flag publicly-traded firms (Luna Innovations) where 10-K cross-check is possible |
| `recipient_search_text` is full-text search, not strict UEI equality | Pre-UEI awards (with DUNS only) may be missed | DUNS→UEI mapping wasn't fully back-applied to USAspending; conservative undercount of older obligations |
| No subaward inclusion | Misses subcontract revenue | `subawards=false` explicit in API call |
| Other Transaction Authority (OTA) agreements not in FPDS/FABS | Misses DARPA OTA work | Acknowledged structural blind spot |
| Two sequential USAspending queries on the same firm can return marginally different totals if the index updates between calls | Caused 1 of 143 firms (Lambda Science) to show `contracts_rd_usd` $826 higher than `contracts_fpds_usd` in our FY2026 run — a USAspending-side inconsistency | Script clamps `contracts_non_rd_val = max(contracts − contracts_rd, 0)`; effect on the affected firm's verdict was $0 (strict avg/P2 would have been $52 vs $100K threshold either way). Audit JSON files in `data/audit/fy2026/usaspending/<UEI>_*.json` preserve the source-of-truth API responses |

## Reproducibility

To re-run on the same FY:

```bash
.venv/bin/python scripts/data/run_commercialization_benchmark.py --eval-fy 2026
```

To capture full audit artifacts:

```bash
.venv/bin/python scripts/data/run_commercialization_benchmark.py --eval-fy 2026 --audit-dir data/audit/fy2026/
```

To spot-check a single firm:

```bash
.venv/bin/python scripts/data/audit_one_firm.py <UEI> --eval-fy 2026
```

## File outputs

| File | Contents |
|---|---|
| `reports/validation/commercialization_benchmark_eval_fy{eval_fy}.csv` | Per-firm: tier, observed federal $, R&D split, Form D, four verdicts (Standard net/strict + Increased net/strict where applicable) |
| `data/audit/fy{eval_fy}/usaspending/<uei>_<call_type>.json` (when `--audit-dir` set) | Raw USAspending API responses, one file per call |
| `data/audit/fy{eval_fy}/form_d_matches.jsonl` (when `--audit-dir` set) | Per-firm Form D match decisions: which offerings counted, which were filtered, why |
| `data/audit/fy{eval_fy}/run_metadata.json` (when `--audit-dir` set) | Run-level inputs: eval_fy, window, RD_NAICS list, statute citations, script git SHA |

## CSV column reference

| Column | Type | Meaning |
|---|---|---|
| `uei`, `firm`, `state`, `p2_count`, `sales_window` | identity | Firm identifier, name, state, P2 count in window, FY range |
| `tier` | str | `standard` / `tier1` / `tier2` — the highest §638(qq) tier the firm is subject to (or `standard` if not subject) |
| `contracts_fpds_usd`, `contracts_rd_usd`, `contracts_non_rd_usd`, `grants_fabs_usd` | $ | USAspending obligation totals: total contracts, R&D-NAICS contracts, residual non-R&D contracts, grants |
| `federal_observed_usd`, `federal_non_rd_estimate_usd` | $ | Total federal observation, and the strict-CCR "sales" estimate (= contracts_non_rd, since grants are treated as R&D) |
| `contracts_api_ok`, `contracts_rd_api_ok`, `grants_api_ok` | bool | Whether each USAspending call succeeded |
| `own_sbir_total_usd` | $ | Firm's own SBIR Phase I+II award total in window (always populated for informational purposes) |
| `investment_form_d_usd` | $ | SEC Form D total offerings in window, state/high-conf filtered |
| `standard_required_per_p2_usd` | $ | $100,000 for every firm |
| `standard_net_sales_counted_usd`, `standard_net_avg_per_p2_usd`, `standard_net_status` | $/status | §638(mm) net broad: sales = federal − own SBIR + Form D, vs $100K |
| `standard_strict_sales_counted_usd`, `standard_strict_avg_per_p2_usd`, `standard_strict_status` | $/status | §638(mm) strict: sales = non-R&D contracts + Form D, vs $100K |
| `increased_required_per_p2_usd` | $ | $250K for tier1, $450K for tier2, NaN otherwise |
| `increased_sales_counted_usd` | $ | Always 0 when populated (covered-sale rule excludes federal) |
| `increased_net_avg_per_p2_usd`, `increased_net_status` | $/status | §638(qq) net: Form D / P2, vs tier threshold |
| `increased_strict_avg_per_p2_usd`, `increased_strict_status` | $/status | §638(qq) strict: identical to net (both excluded federal) |
