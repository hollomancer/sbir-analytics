# Follow-on Funding Multiplier Analysis — Design

> NASEM's reviews of DoD SBIR call this quantity the *leverage ratio*. This codebase uses *follow-on funding multiplier* for the same calculation to avoid the debt connotation that "leverage" carries in finance.

## Architecture

Builds on existing FPDS extraction and entity resolution pipelines. New code lives in
`src/tools/mission_b/` (the follow-on funding multiplier is a commercialization/outcomes metric).

### Data Flow

```
SBIR.gov awards → entity resolution (UEI/DUNS) → vendor universe
                                                       ↓
FPDS contracts → filter to vendor universe → separate SBIR-coded vs non-SBIR
                                                       ↓
                                          compute multipliers by cohort
                                                       ↓
                                              reconcile with NASEM 4:1
```

### Key Components

1. **`FollowOnMultiplierCalculator`** — Core computation: takes vendor-filtered FPDS data,
   separates SBIR/STTR-coded obligations from non-SBIR, computes multipliers at firm and
   aggregate level.

2. **`CohortStratifier`** — Stratifies multipliers by award vintage, firm size buckets,
   technology area (via CET classifier), and experienced vs. new firm classification.

3. **`NASEMReconciler`** — Compares pipeline output to NASEM benchmark values. Produces
   structured reconciliation report with methodology comparison and difference attribution.

4. **`AgencyComparator`** — Runs the same computation for DOE (civilian benchmark),
   enabling cross-agency comparison that no NASEM study provides.

### Output Format

Results are pandas DataFrames + a structured reconciliation report (JSON + markdown).
Designed for both programmatic consumption (Dagster assets) and human review.
