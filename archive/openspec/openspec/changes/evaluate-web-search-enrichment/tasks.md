# Implementation Tasks

## 1. Research & Environment Prep

- [x] 1.1 Confirm licensing, auth requirements, and acceptable-use policies for SearXNG, Tavily, Brave Search API, Google Programmable Search, and Perplexica; capture in docs.
  - Notes: Inventory and initial verification artifacts created — see `openspec/changes/evaluate-web-search-enrichment/search_providers.md` for provider summaries and `openspec/changes/add-iterative-api-enrichment/providers.json` for the canonical provider registry. Automated discovery tooling (`scripts/openspec/fetch_provider_docs.py`) was used to fetch and annotate public documentation pages; follow-up manual verification of provider rate limits and licensing is required.
- [ ] 1.2 Provision credentials or local deployments needed for benchmarking (Dockerized SearXNG/Perplexica, API keys for hosted services).
- [ ] 1.3 Define the representative enrichment prompt set (companies, principal investigators, award transitions) and expected truth data for scoring.

## 2. Provider Adapter Layer

- [ ] 2.1 Create a `BaseSearchProvider` interface with `search(query: str, context: dict) -> ProviderResponse` plus structured metadata (citations, snippet text, latency).
- [ ] 2.2 Implement adapters for SearXNG, Tavily, Brave, Google API wrapper, and Perplexica, including rate-limit/backoff handling and configuration hooks.
- [ ] 2.3 Add provider-specific unit tests using recorded fixtures/mocks to ensure consistent response normalization.

## 3. Benchmark Harness & Metrics

- [ ] 3.1 Implement `scripts/evaluate_search_enrichers.py` (Typer CLI) that executes the prompt suite against each enabled provider, records latency/cost, and writes JSON lines plus Markdown summary.
- [ ] 3.2 Build scoring functions (precision on key facts, citation availability, structured data fields) leveraging the ground-truth dataset.
- [ ] 3.3 Integrate metrics with existing pipeline metrics utilities so results can be compared run-over-run.

## 4. Reporting & Recommendations

- [ ] 4.1 Generate `reports/search_enrichment_benchmark.md` with tables comparing accuracy, latency, cost, compliance posture, and operational complexity per provider.
- [ ] 4.2 Document go/no-go decision criteria and recommended next steps in `docs/enrichment/web-search-evaluation.md`.
- [ ] 4.3 Produce a recommendation narrative identifying which providers advance to pilot integration (including dependency/cost implications) and which are deferred.
