# Superseded Specifications

Specifications archived because they have been superseded or deferred.

## MCP Interface (mcp_interface/)
**Archived:** 2026-03-12
**Reason:** Superseded by `mcp_agent_tools` spec which defines a more focused Phase 1 approach.

## Web Search Enrichment (web_search_enrichment/)
**Archived:** 2026-03-12
**Reason:** No functional code was built. Requires re-scoping and explicit re-prioritization before pursuing. The original spec defined provider adapters, evaluation CLI, and benchmarking, but none were implemented.

## ModernBERT Bayesian MoE (modernbert-bayesian-moe/)
**Archived:** 2026-11-14
**Reason:** The Bayesian routing, LoRA expert, uncertainty, FAISS, and dedicated
monitoring proposal was never implemented or validated and had no current
operating owner. The active `modernbert-analysis-layer` spec now covers the
maintained exploratory single-model similarity path; reviving the superseded
proposal requires a new scope review.

## Jev CI Failure Triage (jev-ci-triage/)
**Archived:** 2026-11-21
**Reason:** Dropped, not completed. The pilot sent sanitized CI failures to an
LLM for triage. It answered no research question in
`docs/research-questions.md`. Its non-blocking `Experimental Jev Triage
Contract` CI job was skipped in 30 of 30 recent pull-request runs, and live Jev
calls never cleared their gates. The `scripts/ci/jev_triage/` package, its
fixtures, tests, and CI job were removed with this archive. Git history holds
the code. The separate `jev-preflight` and `jev-ci-enforcement` specs are not
affected.
