# Neo4j Failure Configuration Changes

## Summary

Modified the ETL pipeline to fail when Neo4j Aura is unavailable, unless "Skip Neo4j loading" is explicitly selected via the `SKIP_NEO4J_LOADING` environment variable.

## Changes Made

### 1. Workflow Configuration (.github/workflows/etl-pipeline.yml)

- Added `SKIP_NEO4J_LOADING: ${{ github.event.inputs.skip_neo4j }}` environment variable to all pipeline jobs that use Neo4j:
  - SBIR Pipeline
  - USPTO Pipeline
  - CET Classification Pipeline

### 2. CET Assets (src/assets/cet/company.py)

- Modified `_get_neo4j_client()` function to:
  - Check `SKIP_NEO4J_LOADING` environment variable
  - Raise `RuntimeError` when Neo4j is unavailable and not explicitly skipped
  - Return `None` gracefully only when skip flag is set to true

### 3. CET Loading Assets (src/assets/cet/loading.py)

- Updated all loading assets to change return reason from `"neo4j_unavailable"` to `"neo4j_skipped"` when client is None
- Assets affected:
  - `loaded_cet_areas`
  - `loaded_award_cet_enrichment`
  - `loaded_company_cet_enrichment`
  - `loaded_award_cet_relationships`
  - `loaded_company_cet_relationships`

### 4. SBIR Neo4j Loading (src/assets/sbir_neo4j_loading.py)

- Modified `_get_neo4j_client()` function to:
  - Check `SKIP_NEO4J_LOADING` environment variable
  - Raise `RuntimeError` when Neo4j connection fails and not explicitly skipped
  - Log warning and return `None` only when skip flag is set

### 5. USPTO Assets (src/assets/uspto/utils.py)

- Modified `_get_neo4j_client()` function to:
  - Check `SKIP_NEO4J_LOADING` environment variable
  - Raise `RuntimeError` when Neo4j client is unavailable or connection fails and not explicitly skipped
  - Return `None` gracefully only when skip flag is set

### 6. Transition Assets (src/assets/transition/utils.py)

- Modified `_get_neo4j_client()` function to:
  - Check `SKIP_NEO4J_LOADING` environment variable
  - Raise `RuntimeError` when Neo4j client is unavailable or connection fails and not explicitly skipped
  - Return `None` gracefully only when skip flag is set

### 7. Company Categorization (src/assets/company_categorization.py)

- Added skip Neo4j logic to `neo4j_company_categorization` asset:
  - Check `SKIP_NEO4J_LOADING` environment variable
  - Return skipped status when flag is set
  - Raise `RuntimeError` when Neo4j connection fails and not explicitly skipped

## Behavior Changes

### Before

- Pipeline would gracefully skip Neo4j operations when Neo4j was unavailable
- No way to distinguish between intentional skipping and connection failures
- Pipeline would succeed even when Neo4j Aura was offline

### After

- Pipeline **fails** when Neo4j is unavailable unless explicitly skipped
- User must set `skip_neo4j: true` in workflow dispatch to skip Neo4j operations
- Clear error messages indicate Neo4j connection issues and how to skip if needed
- When skipped, assets return appropriate status indicating the skip was intentional

## Usage

### To run pipeline with Neo4j (default behavior)

- Use workflow dispatch with `skip_neo4j: false` (default)
- Pipeline will fail if Neo4j Aura is unavailable

### To run pipeline without Neo4j

- Use workflow dispatch with `skip_neo4j: true`
- Pipeline will skip all Neo4j operations and succeed

### Environment Variable

- `SKIP_NEO4J_LOADING=true` - Skip Neo4j operations
- `SKIP_NEO4J_LOADING=false` or unset - Require Neo4j connectivity (fail if unavailable)

## Error Messages

When Neo4j is unavailable and not skipped, users will see clear error messages like:

```text
RuntimeError: Neo4j connection failed but Neo4j loading not skipped: [connection error]. Set SKIP_NEO4J_LOADING=true to skip.
```
