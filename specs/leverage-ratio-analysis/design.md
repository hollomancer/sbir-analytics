# Leverage Ratio Analysis — Design

## Architecture

Builds on existing FPDS extraction and entity resolution pipelines. New code lives in
`src/tools/mission_b/` (leverage ratio is a commercialization/outcomes metric).

### Data Flow

```
SBIR.gov awards → entity resolution (UEI/DUNS) → vendor universe
                                                       ↓
FPDS contracts → filter to vendor universe → separate SBIR-coded vs non-SBIR
                                                       ↓
                                              compute ratios by cohort
                                                       ↓
                                              reconcile with NASEM 4:1
```

### Key Components

1. **`LeverageRatioCalculator`** — Core computation: takes vendor-filtered FPDS data,
   separates SBIR/STTR-coded obligations from non-SBIR, computes ratios at firm and
   aggregate level.

2. **`CohortStratifier`** — Stratifies ratios by award vintage, firm size buckets,
   technology area (via CET classifier), and experienced vs. new firm classification.

3. **`NASEMReconciler`** — Compares pipeline output to NASEM benchmark values. Produces
   structured reconciliation report with methodology comparison and difference attribution.

4. **`AgencyComparator`** — Runs the same computation for DOE (civilian benchmark),
   enabling cross-agency comparison that no NASEM study provides.

### Output Format

Results are pandas DataFrames + a structured reconciliation report (JSON + markdown).
Designed for both programmatic consumption (Dagster assets) and human review.
