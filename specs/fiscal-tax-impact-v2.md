# Fiscal Tax Impact v2 — Development Plan

**Date:** 2026-04-19
**Status:** Spec
**Branch:** `research/open-source-tax-impact-modeling`
**Research:** `docs/research/open-source-tax-impact-modeling.md`

## Goal

Replace the current hardcoded effective tax rates in `FiscalTaxEstimator` with
data-driven rates from BEA NIPA tables, producing defensible federal, state,
and local tax receipt estimates from SBIR spending.

The current pipeline produces `tax_impact` as a single number using a flat
~22% effective rate. The upgrade should produce **jurisdiction-separated**
estimates (federal income, payroll, corporate, state, local) grounded in
published BEA data, comparable to what IMPLAN produces.

## Current State

```
sbir_etl/enrichers/fiscal_bea_mapper.py     # NAICS → BEA sector mapping (stateior-based)
sbir_etl/transformers/bea_api_client.py     # BEA API client
sbir_etl/transformers/bea_io_adapter.py     # I-O table adapter
sbir_etl/transformers/bea_io_functions.py   # Multiplier calculations
sbir_etl/transformers/sbir_fiscal_pipeline.py  # Main pipeline (SBIRFiscalImpactCalculator)
sbir_etl/transformers/fiscal/
    taxes.py          # FiscalTaxEstimator — REPLACE THIS
    roi.py            # FiscalROICalculator — consumes tax estimates
    components.py     # Economic component decomposition
    sensitivity.py    # Sensitivity analysis
    shocks.py         # Scenario shock modeling
    district_allocator.py  # Congressional district allocation
```

The pieces that work well and should stay:
- NAICS → BEA sector mapping
- I-O multiplier calculations (production, wage, proprietor income impacts)
- ROI calculator (consumes tax estimates, doesn't need to change)
- Congressional district allocator

The piece that needs replacement: **`taxes.py`** — swap hardcoded rates for
BEA NIPA-derived rates.

## Development Plan

### Phase 1: BEA NIPA Data Ingestion (1 week)

**Goal:** Download and cache the BEA NIPA tables we need for tax rate calculation.

**Tables required:**

| BEA Table | Content | Use |
|-----------|---------|-----|
| **NIPA 3.2** | Federal government current receipts | Total federal tax receipts by type |
| **NIPA 3.3** | State/local government current receipts | Total state+local receipts by type |
| **NIPA 3.4** | Personal current taxes by type | Effective personal income tax rates |
| **NIPA 3.6** | Contributions for government social insurance | Payroll tax rates by industry |
| **NIPA 1.12** | National income by type of income | Compensation, proprietor income, corporate profits by industry |
| **NIPA 6.2D** | Compensation by industry (detail) | Industry-specific wage levels |

**Tasks:**

- [ ] Add BEA NIPA table fetch to `bea_api_client.py` (already has API client, need NIPA endpoints)
- [ ] Create `data/reference/bea/nipa_tax_rates.parquet` cache file
- [ ] Build `NIPATaxRateBuilder` that computes effective rates:
  - Federal individual income tax rate = Table 3.2 personal tax / Table 1.12 compensation
  - Federal payroll tax rate = Table 3.6 contributions / Table 1.12 compensation
  - Federal corporate tax rate = Table 3.2 corporate tax / Table 1.12 corporate profits
  - State+local rate = Table 3.3 receipts / Table 1.12 total income
- [ ] Unit tests with mocked BEA responses
- [ ] Verify: rates should fall in expected ranges (federal income: 12-18%, payroll: 14-15%, corporate: 8-14%)

### Phase 2: Replace FiscalTaxEstimator (1 week)

**Goal:** Swap hardcoded rates for NIPA-derived rates, producing jurisdiction-separated estimates.

**Output schema change:**

```python
# Current: single tax_impact column
tax_impact: float  # ~22% of wage_impact

# New: separated by jurisdiction and type
federal_income_tax: float      # Personal income tax on compensation
federal_payroll_tax: float     # FICA (employer + employee share)
federal_corporate_tax: float   # Corporate income tax on gross operating surplus
federal_excise_tax: float      # Excise taxes on consumption impact
state_income_tax: float        # State personal income tax
state_sales_tax: float         # State sales tax on consumption
local_property_tax: float      # Local property tax on capital stock
local_other_tax: float         # Other local taxes
total_tax_receipt: float       # Sum of all above
```

**Tasks:**

- [ ] Rewrite `FiscalTaxEstimator` to load NIPA rates from cache
- [ ] Apply rates by component:
  - `wage_impact × federal_income_rate → federal_income_tax`
  - `wage_impact × payroll_rate → federal_payroll_tax`
  - `gross_operating_surplus × corporate_rate → federal_corporate_tax`
  - `consumption_impact × excise_rate → federal_excise_tax`
  - `wage_impact × state_income_rate → state_income_tax`
  - `consumption_impact × state_sales_rate → state_sales_tax`
  - Estimate local from Census ASGF effective rates (by state)
- [ ] Update `SBIRFiscalImpactCalculator` output schema
- [ ] Update `FiscalROICalculator` to use new `total_tax_receipt` column
- [ ] Backward compatibility: keep `tax_impact` as alias for `total_tax_receipt`
- [ ] Unit tests comparing old vs new estimates (should be in same ballpark)

### Phase 3: State-Level Rate Variation (1 week)

**Goal:** Use state-specific tax rates instead of national averages.

**Data sources:**

| Data | Source | Granularity |
|------|--------|-------------|
| State income tax rates | Tax Foundation annual tables | State × year |
| State sales tax rates | Tax Foundation + Census | State × year |
| Local effective property tax rates | Census ASGF | State × year |
| State payroll tax (SUTA) | DOL annual reports | State × year |

**Tasks:**

- [ ] Create `data/reference/tax/state_effective_rates.csv` with rates by state and year
- [ ] Source from Tax Foundation's published tables (free, annual updates)
- [ ] Add Census ASGF local rate data (property, sales)
- [ ] Update estimator to use state-specific rates when `state` column is available
- [ ] Fall back to national average when state is missing
- [ ] Add `rate_source` metadata column: "nipa_national" vs "state_specific"

### Phase 4: Validation & Calibration (1 week)

**Goal:** Validate estimates against published benchmarks.

**Benchmarks:**

| Source | What they report | Our comparison |
|--------|-----------------|----------------|
| NASEM (2022) SBIR report | IMPLAN-based fiscal estimates for SBIR | Direct comparison on same award set |
| GAO SBIR program evaluations | Economic impact multipliers | Compare multiplier ranges |
| Bartik (2012) methodology | Effective fiscal impact rates by sector | Compare our sector-level rates |
| IRS SOI | Actual tax receipts by industry | Sanity check on rate ranges |

**Tasks:**

- [ ] Run pipeline on the same SBIR award cohort used in NASEM (2022)
- [ ] Compare total tax receipts, multipliers, and per-dollar returns
- [ ] Document deviations and rationale
- [ ] If estimates diverge >20% from IMPLAN benchmarks, investigate
- [ ] Add calibration adjustment factors if needed (documented, transparent)
- [ ] Write validation report: `docs/fiscal/validation-report.md`

### Phase 5: Future — Tax-Calculator Integration (deferred)

**Goal:** Replace effective-rate approach with microsimulation for higher precision.

This is the full Tax-Calculator/TAXSIM chain described in the research note.
Defer until Phase 4 validation shows the effective-rate approach is insufficient.

**Tasks (for future):**

- [ ] Build income distribution crosswalk (IRS SOI → industry bracket profiles)
- [ ] Generate synthetic tax units from I-O compensation outputs
- [ ] Integrate PSLmodels Tax-Calculator for federal estimates
- [ ] Integrate NBER TAXSIM for state estimates
- [ ] Compare microsim vs effective-rate results

## Dependencies

```toml
# Already in project
# bea_api_client.py handles BEA API access

# New (Phase 1 only)
# No new dependencies — BEA NIPA tables are fetched via existing API client

# Future (Phase 5 only)
# taxcalc >= 4.0  # PSLmodels Tax-Calculator
```

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| BEA API downtime | Cache NIPA tables locally, refresh quarterly |
| Tax law changes | NIPA tables auto-update; rates refresh with pipeline |
| State rate data gaps | Fall back to national average with quality flag |
| Validation benchmark access | Use published NASEM/GAO numbers (public) |
| Scope creep into microsimulation | Strict phase gate — only proceed to Phase 5 if Phase 4 shows need |

## Success Criteria

- [ ] Tax estimates separated by jurisdiction (federal/state/local) and type
- [ ] Rates sourced from BEA NIPA (not hardcoded)
- [ ] State-level variation for the 50 states
- [ ] Per-dollar SBIR return estimate within 20% of published IMPLAN benchmarks
- [ ] Pipeline runs in <5 minutes for full award database
- [ ] No new paid data dependencies
