# Requirements

## Overview

Following the recent consolidation of USAspending HTTP accessors, a few lingering issues remain:

1. Legacy parameters and documentation still reference the removed direct-HTTP plumbing (e.g., `max_psc_lookups`, `_make_rate_limited_request`).
2. Several modules now need a shared "run async coroutine from sync context" helper instead of re-implementing `_run_async` in-line.
3. The new `_import_usaspending_table` helper still relies on hard-coded OIDs, and redundant client instantiations/logs slipped in during the refactor.
4. Tests and scripts still mock/depend on the old HTTP helpers, making them brittle against the new client API.

## Requirements

1. **Function Signatures & Docs**
   - THE company categorization API helpers SHALL expose only parameters that take effect; remove `max_psc_lookups` (including docs/tests) and update references in quick-test scripts.
   - THE `_fuzzy_match_recipient` docstring SHALL reflect the absence of base URL/timeout parameters.

2. **Shared Async Helper**
   - THE codebase SHALL provide a reusable helper (e.g., `utils/async_tools.run_sync`) that runs an async coroutine from sync contexts while handling `asyncio.run()` conflicts.
   - Modules currently defining `_run_async` SHALL import and use the shared helper instead of duplicating logic.

3. **USAspending Asset Helper Resilience**
   - `_import_usaspending_table` SHALL discover the actual DuckDB view/table name automatically (e.g., by scanning DuckDB metadata) and avoid hard-coded OIDs, while keeping metadata identical.
   - Logging SHALL continue to specify which logical table was imported.

4. **Client Initialization Cleanup**
   - `retrieve_company_contracts_api` SHALL only call `_get_usaspending_client()` once; remove redundant assignments.
   - `_fetch_award_details` SHALL rely on the shared async helper and expose only the award ID argument (already refactored, ensure call sites updated).

5. **Tests & Tooling**
   - Existing tests/scripts that imported `_make_rate_limited_request` SHALL be updated to mock `USAspendingAPIClient` methods instead.
   - The quick PSC retrieval script SHALL no longer accept/forward the removed parameters.
