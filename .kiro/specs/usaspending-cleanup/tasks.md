# Tasks

1. Remove unused parameters/docs
   - Update `retrieve_company_contracts_api`/`retrieve_sbir_awards_api` signatures and docstrings.
   - Fix references in `test_psc_retrieval.py`, `docs/archive/*`, and any other call sites.

2. Shared async helper
   - Add `src/utils/async_tools.py` (or similar) exposing `run_sync`.
   - Replace inline `_run_async` definitions with imports (company categorization, other modules/scripts).

3. Auto-detect imported USAspending table names
   - Extend `_import_usaspending_table` to identify the actual DuckDB table/view (e.g., by querying DuckDB's information schema) instead of requiring `_OID` suffixes.
   - Ensure metadata and logging remain the same, and update tests/docs if needed.

4. Cleanup client usage
   - Remove the duplicate `_get_usaspending_client()` call.
   - Ensure `_fetch_award_details` callers no longer pass unused parameters; adjust any call sites/tests accordingly.

5. Tests & scripts
   - Update `test_categorization_validation.py`, `test_psc_retrieval.py`, and any other tests referencing the removed helpers/params to mock `USAspendingAPIClient` or use the new helper.
   - Run targeted pytest selection for affected modules if feasible.
