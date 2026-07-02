# Superseded Specifications

Specifications archived because they have been superseded or deferred.

## MCP Interface (mcp_interface/)
**Archived:** 2026-03-12
**Reason:** Superseded by `mcp_agent_tools` spec which defines a more focused Phase 1 approach.

## Web Search Enrichment (web_search_enrichment/)
**Archived:** 2026-03-12
**Reason:** No functional code was built. Requires re-scoping and explicit re-prioritization before pursuing. The original spec defined provider adapters, evaluation CLI, and benchmarking, but none were implemented.

## Data Imputation (data-imputation/)
**Archived:** 2026-07-02
**Reason:** Empirical analysis of the SBIR bulk download showed that both headline problems the spec targeted (`award_date` at ~50% missing, `company_uei` missing on many records) were mis-framed. `award_date` missingness is a schema cutover pre-2004 (Award Year is 100% populated — the correct operation is time-key routing, not statistical imputation). `company_uei` missingness is a firm-level bifurcation (40.9% of multi-award firms are 100% missing, ~0% scatter — this is entity resolution, not per-value imputation). No implementation was ever built. Superseded by `specs/firm-identity-resolution/` and `specs/input-validation-hardening/`. See `data-imputation/README.md` for the full reframe.
