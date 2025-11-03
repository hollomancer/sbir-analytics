# Evaluate Web Search-Based Enrichment Providers

## Why

- Public web search/meta-search endpoints (SearXNG, Tavily, Brave Search API, Google Custom Search/Programmable Search, Perplexica, etc.) can fill information gaps—company descriptions, leadership changes, PI bios, product launches—that traditional government APIs do not expose.
- We need a structured evaluation to determine which providers deliver reliable, policy-compliant enrichment signals (structured snippets, entity metadata, citations) while keeping API quotas, latency, and operating costs acceptable for nightly refresh cycles.
- Some options (SearXNG) can be self-hosted for air-gapped environments, while others require paid keys; we must document trade-offs so security/compliance stakeholders can green-light production integration.

## What Changes

- **Discovery & benchmarking**
  - Stand up test harnesses for SearXNG (self-hosted), Tavily, Brave, Google Custom Search API wrapper, and Perplexica (self-hosted or managed) to measure response quality, rate limits, and structured data coverage using representative SBIR entities.
  - Capture normalized scoring (precision/recall on targeted facts, freshness, citation quality) plus cost-per-1k queries and operational complexity.
- **Evaluator tooling**
  - Build a `poetry run evaluate_search_enrichers` CLI that replays a curated set of enrichment prompts (company detail, PI bio, commercialization milestone) against each provider and stores outputs, latency, and scoring metrics in `reports/search_enrichment_benchmark.md` and accompanying JSON.
  - Include configurable search templates so future providers can be added without code rewrite.
- **Integration decision gates**
  - Document data handling/compliance requirements (PII exposure, caching policy, hosting posture) and produce a recommendation matrix highlighting which providers should move to pilot integration for iterative enrichment.
  - Provide clear go/no-go criteria (e.g., must return structured org summary with citation in <2s, cost <$0.05/query, allow caching evidence for 30 days).

## Impact

### Affected Specs

- **data-enrichment**: Add requirements for evaluating and validating web-search-based enrichment providers before integrating them into the pipeline.

### Affected Code / Docs

- `scripts/evaluate_search_enrichers.py` (new) — CLI harness driving provider benchmarks.
- `src/search_providers/` (new) — thin adapters for SearXNG, Tavily, Brave, Google API wrapper, Perplexica with common interface + telemetry.
- `reports/search_enrichment_benchmark.(md|json)` — captures results, scoring tables, compliance notes.
- `docs/enrichment/web-search-evaluation.md` — methodology, scoring rubric, onboarding instructions for each provider.
- `config/base.yaml` — optional `search_enrichment` section for API keys/endpoints and feature flags.

### Data Volume & Performance Considerations

- Benchmark set ~500 queries covering companies, people, awards; each provider must complete within 15 minutes to be viable for nightly refresh. Response payloads stored locally for reproducibility (<=200MB).

### Dependencies

- Potential new client libraries/SDKs (Tavily, Brave, Google) or generic HTTP client (httpx already proposed in iterative change) plus optional Docker image for SearXNG/Perplexica. Document licensing/cost implications before adoption.
