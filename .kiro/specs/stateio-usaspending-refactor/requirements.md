# Requirements

## Overview

We need to close three refactoring gaps that still create unnecessary operational risk:

1. StateIO fallback simulations still emit placeholder rows whenever USEEIOR is unavailable. We need a real matrix computation path so fiscal pipelines can run without manual intervention.
2. The company categorization enricher re-implements HTTP clients and rate limiting for three USAspending endpoints instead of using the consolidated `USAspendingAPIClient`, leading to duplicated config, logging, and retry policies.
3. The two raw USAspending ingestion assets are copy/pasted with only table/OID differences, making future fixes error-prone and bloating maintenance surface area.

## Requirements

### StateIO Fallback Simulation
- THE adapter SHALL construct Leontief inverses via StateIO matrices when USEEIOR models are unavailable.
- WHEN the fallback path runs, THE adapter SHALL populate the same impact columns (wage, proprietor income, GOS, taxes, production) as the USEEIOR path using StateIO-provided technical coefficients and value-added components.
- THE fallback implementation SHALL emit descriptive quality flags (e.g., `stateio_direct`) and non-zero confidence scores derived from component coverage.
- THE fallback SHALL reuse helper utilities in `r_stateio_functions.py` for building matrices, computing Leontief inverses, and extracting value-added ratios to avoid duplicating R interop logic.

### Company Categorization USAspending Client Consolidation
- THE company categorization module SHALL delegate HTTP requests, rate limiting, and retries to `USAspendingAPIClient` for fuzzy recipient search, transaction lookups, and SBIR award retrieval.
- WHEN batching API lookups, THE enricher SHALL reuse a single client instance and avoid re-reading configuration for every helper call.
- THE existing caching layer SHALL remain available; API results retrieved via the consolidated client SHALL be stored and retrieved via `USAspendingCache` as before.
- Error and telemetry information SHALL flow through the centralized client, ensuring consistent exception types (`APIError`, `RateLimitError`) and log metadata.

### USAspending Ingestion Asset Deduplication
- THE ingestion module SHALL expose a shared helper/factory that accepts table metadata (name, OID, Dagster description) and returns a fully configured Dagster asset.
- Shared functionality (config loading, extractor instantiation, logging, metadata assembly) SHALL live in the helper to eliminate duplication between recipient and transaction assets.
- The helper SHALL preserve the existing Dagster metadata payload (row counts, previews, column lists) so UI dashboards remain unchanged.
- Future assets SHALL be able to call the helper with minimal parameters to add new dump tables without copy/paste.
