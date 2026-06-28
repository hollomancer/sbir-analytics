# Requirements — State & Local Tax Rate Reference Data

> **Status:** Not yet started. Required by **Phase 3** of
> [../fiscal-tax-impact-v2.md](../fiscal-tax-impact-v2.md) and by
> **Requirement 3** of [../fiscal-sensitivity-reconciliation/](../fiscal-sensitivity-reconciliation/).
> Anchors inventory questions **D2** (state-level fiscal returns) and **D3**
> (state-rate sensitivity) in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** D2 — how do fiscal returns stratify by state? D3 — does state-specific vs. national-average rate choice materially change state-by-state ROI estimates?
**Answers for:** pipeline engineers, Treasury / OMB analysts, state economic-development offices
**Complexity tier:** Foundational data acquisition

---

## Done when

> A pipeline engineer can state: "`data/reference/tax/state_effective_rates.csv`
> contains state income tax, state sales tax, state SUTA payroll tax, and local
> effective property tax rates for all 50 states and D.C., by year (2010–present),
> sourced from Tax Foundation annual tables and Census ASGF. Rates are refreshed
> annually. The `FiscalTaxEstimator` uses state-specific rates when a `state` field
> is present and falls back to the NIPA national average with a `rate_source` flag
> when state is missing."

---

## Introduction

BEA NIPA tables (D2 Phase 1, `specs/bea-nipa-tax-rates/`) produce national-average
effective tax rates. Texas has no state income tax; California tops out at 13.3%.
Applying a national average to every SBIR award introduces systematic error for
state-level fiscal return estimates. This spec covers the two data sources that
provide state-specific rates:

- **Tax Foundation** annual tables: state income tax, state sales tax, SUTA (state
  unemployment insurance payroll tax). Published annually; freely downloadable.
- **Census Annual Survey of Government Finances (ASGF)**: local effective property
  tax rates by state, derived from Census-reported local tax collections ÷ Census
  property value estimates.

Both sources are assembled into a single `state_effective_rates.csv` that the
`FiscalTaxEstimator` can join to award records by `state` and `fiscal_year`.

---

## User Stories

**As a pipeline engineer,** I want state-specific effective tax rates in a single
reference CSV, refreshed annually without code changes, so that the fiscal estimator
can apply the correct rate for each award's state rather than a national average.

**As a Treasury analyst reporting state-level SBIR ROI to state economic-development
offices,** I want state-specific rates documented with their Tax Foundation source
year, so that I can defend the rate assumptions in state-facing reports.

---

## Requirements

### Requirement 1 — Tax Foundation state rate ingestion

#### Acceptance Criteria

1. THE System SHALL source the following rates per state per year from Tax Foundation
   published tables: state individual income tax top rate, state sales tax average
   rate, and state SUTA (unemployment insurance) tax rate.
2. THE System SHALL cover years 2010 through the most recent published Tax Foundation
   edition, adding new years annually.
3. THE System SHALL store raw Tax Foundation source files in
   `data/reference/tax/sources/tax_foundation/` with filename including the
   publication year (e.g., `state_individual_income_tax_rates_2024.csv`).
4. THE System SHALL note the Tax Foundation's "State Individual Income Tax Rates and
   Brackets" and "State and Local Sales Tax Rates" annual publications as the
   authoritative source in the reference CSV's header metadata.

### Requirement 2 — Census ASGF local property tax rates

#### Acceptance Criteria

1. THE System SHALL derive local effective property tax rates from Census ASGF
   state-level data: (total local property tax collections) ÷ (total assessed
   property value) per state per year.
2. THE System SHALL cover years 2010–present, refreshing when Census publishes the
   latest ASGF edition (typically 18 months after the survey year).
3. THE System SHALL store raw Census ASGF files in
   `data/reference/tax/sources/census_asgf/`.

### Requirement 3 — Unified reference table

#### Acceptance Criteria

1. THE System SHALL assemble a single `data/reference/tax/state_effective_rates.csv`
   with columns: `state_fips`, `state_abbr`, `fiscal_year`, `state_income_tax_rate`,
   `state_sales_tax_rate`, `state_suta_rate`, `local_property_tax_rate`,
   `income_source`, `sales_source`, `suta_source`, `property_source`.
2. WHEN a state-year cell is missing from any source, THE System SHALL fill it with
   the national average from the NIPA tables and set the corresponding `*_source`
   column to `"nipa_national_avg"`.
3. THE System SHALL include Washington D.C. as a jurisdiction row.
4. THE `FiscalTaxEstimator` SHALL consume this file by joining on `state_fips` and
   `fiscal_year`, and attach a `rate_source` metadata column
   (`"state_specific"` vs. `"nipa_national_avg"`) to each output row.
