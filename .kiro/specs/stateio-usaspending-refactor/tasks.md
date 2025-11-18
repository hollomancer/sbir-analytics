# Tasks

## 1. StateIO Fallback Implementation
- [ ] Add helpers in `src/transformers/r_stateio_functions.py` to extract technical coefficient matrices (A), compute the Leontief inverse (I - A)^-1, and derive sector-level value-added ratios using StateIO outputs.
- [ ] Update `_compute_impacts_via_stateio` in `src/transformers/r_stateio_adapter.py` to call the new helpers per state, multiply shock demand vectors by the Leontief inverse, and populate wage/GOS/tax components using extracted ratios.
- [ ] Add logging + quality flags that distinguish between direct StateIO computations and partial fallbacks (e.g., when some components are missing), and include sensible confidence scores (e.g., based on available ratios).
- [ ] Expand/adjust unit tests (or add new ones) covering non-zero outputs, caching, and error pathways for the fallback mode.

## 2. Company Categorization Client Refactor
- [ ] Extend `USAspendingAPIClient` with async helper methods needed by categorization (recipient autocomplete, transaction search with PSC filters, SBIR-only search) and synchronous wrappers for existing call sites.
- [ ] Replace `_make_rate_limited_request`, `_fuzzy_match_recipient`, `retrieve_company_contracts_api`, and `retrieve_sbir_awards_api` HTTP plumbing with logic that reuses a shared `USAspendingAPIClient` instance (with caching preserved).
- [ ] Ensure the refactor maintains existing metadata outputs/columns and updates tests or adds new ones to validate the new pathways.

## 3. USAspending Ingestion Asset Helper
- [ ] Introduce a helper function (e.g., `_build_usaspending_asset`) in `src/assets/usaspending_ingestion.py` that encapsulates repeated logic for DuckDB import assets (config fetch, extractor init, metadata construction).
- [ ] Rewrite `raw_usaspending_recipients` and `raw_usaspending_transactions` using the helper while keeping asset signatures/metadata identical.
- [ ] Add targeted tests or Dagster asset snapshots if necessary (or at least run existing tests) to ensure behavior is unchanged.
