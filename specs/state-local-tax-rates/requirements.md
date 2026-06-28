# Requirements — State & Local Tax Rate Reference Data

> **Status:** Not yet started — but significant existing implementation.
> `sbir_etl/transformers/fiscal/state_rates.py` already contains all 50 states
> with hardcoded 2024 Tax Foundation / Census ASGF rates and a `StateRateProvider`
> class. **The task is to make those rates data-driven** (loaded from a refreshable
> CSV) rather than hardcoded constants. The `StateTaxRates` dataclass and
> `StateRateProvider` interface stay unchanged.
>
> Required by **Phase 3** of [../fiscal-tax-impact-v2.md](../fiscal-tax-impact-v2.md) and
> **Requirement 3** of [../fiscal-sensitivity-reconciliation/](../fiscal-sensitivity-reconciliation/).
> Anchors inventory questions **D2** and **D3** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** D2 — state-level fiscal return stratification; D3 — does state-specific vs. national-average rate choice materially change state-by-state ROI estimates?
**Answers for:** pipeline engineers, Treasury / OMB analysts, state economic-development offices
**Complexity tier:** Foundational data acquisition

---

## Done when

> A pipeline engineer can state: "`data/reference/tax/state_effective_rates.csv`
> contains the same rates as `state_rates.py`'s `_STATE_RATES_2024` dict — but
> refreshed from Tax Foundation and Census ASGF source files, not hardcoded. Running
> `poetry run refresh-state-rates` downloads the latest Tax Foundation tables and
> updates the CSV. `StateRateProvider` loads from the CSV when a path is supplied,
> falls back to the hardcoded dict otherwise. Existing tests pass unchanged."

---

## Current state

`sbir_etl/transformers/fiscal/state_rates.py` already has:

- `StateTaxRates` dataclass (income_rate, sales_rate, property_rate, has_income_tax, has_sales_tax)
- `_STATE_RATES_2024` — all 50 states + D.C. hardcoded with 2024 Tax Foundation (income, sales) and Census ASGF (property) rates
- `StateRateProvider` class with `get_rates(state)` and no-income-tax / no-sales-tax helpers

Tests at `tests/unit/transformers/fiscal/test_state_rates.py`.

The hardcoded dict is the problem: it requires a code change every year to update rates and has no provenance trail (which exact Tax Foundation edition, which line?). This spec makes the rates data-driven without changing the interface.

---

## User Stories

**As a pipeline engineer,** I want the state rate data loaded from a version-controlled
CSV rather than a hardcoded Python dict, so that annual rate updates don't require a
code change — only a data file update with a cited source.

**As a Treasury analyst,** I want each rate in the CSV to carry a source citation
(Tax Foundation edition year, table, line), so that the methodology is auditable
without reading source code.

---

## Requirements

### Requirement 1 — CSV reference file with source citations

#### Acceptance Criteria

1. THE System SHALL create `data/reference/tax/state_effective_rates.csv` with one
   row per state-year containing: `state_fips`, `state_abbr`, `fiscal_year`,
   `income_rate`, `sales_rate`, `property_rate`, `has_income_tax`, `has_sales_tax`,
   `income_source`, `sales_source`, `property_source`.
2. THE initial population SHALL match the values in `_STATE_RATES_2024` exactly, with
   `fiscal_year = 2024` and source columns citing the specific Tax Foundation and
   Census ASGF publications used.
3. WHEN a state has no income tax (AK, FL, NV, NH, SD, TN, TX, WA, WY) or no sales
   tax (DE, MT, NH, OR), the corresponding rate SHALL be 0.0 and the `has_*` flag
   SHALL be `False`.

### Requirement 2 — StateRateProvider updated to load from CSV

#### Acceptance Criteria

1. THE `StateRateProvider` class SHALL accept an optional `csv_path: Path | None = None`
   parameter. When provided, it loads rates from the CSV filtered to
   `fiscal_year = max(available year ≤ requested_year)`. When `None`, it falls back
   to `_STATE_RATES_2024` for backwards compatibility.
2. THE public interface (`get_rates(state)`, `states`, `no_income_tax_states`,
   `no_sales_tax_states`) SHALL remain unchanged so all existing callers work without
   modification.
3. Existing tests in `tests/unit/transformers/fiscal/test_state_rates.py` SHALL pass
   without modification after this change.

### Requirement 3 — Annual refresh CLI

#### Acceptance Criteria

1. THE System SHALL implement `poetry run refresh-state-rates` that downloads the
   latest Tax Foundation "State Individual Income Tax Rates" and "State and Local
   Sales Tax Rates" tables, appends a new fiscal-year row for each state, and
   writes the updated CSV.
2. WHEN a state-year already exists in the CSV, THE System SHALL overwrite it rather
   than append a duplicate.
3. THE CLI SHALL log which Tax Foundation edition it sourced and the count of states
   updated, and fall back gracefully (log warning, no update) if the download fails.
