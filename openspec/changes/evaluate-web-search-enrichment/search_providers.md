# Web Search Enrichment — Provider Inventory (task 1.1)

This document is an inventory and quick reference for evaluating web-search and meta-search providers for the project's enrichment needs. It captures high-level licensing, authentication, acceptable-use considerations, and an initial recommendation for throttling/release-cadence checks. This is a research artifact: each "verification" entry should be validated against authoritative provider docs and recorded in an authoritative registry (see `openspec/providers.json`).

Goals for task 1.1
- Identify each candidate provider's licensing and acceptable-use constraints.
- Determine the auth model and how secrets / credentials are provisioned.
- Capture any published rate limits or, where missing, record a conservative recommended default to use for initial integration.
- Note whether the provider can be self-hosted (air-gapped option) and whether a local deployment is available for development/benchmarking.
- List next steps to obtain definitive values (doc links, account requests, test keys).

Providers covered
- SearXNG (self-hosted meta-search)
- Tavily (hosted search / enterprise vendor)
- Brave Search API
- Google Programmable Search / Custom Search JSON API
- Perplexica (self-hosted / managed semantic search)
- (Optional) Notes about proxies & meta-search orchestration

Summary table (quick view)
| Provider | License / Hosting | Auth model | Self-hostable? | Known rate-limit (initial) | Acceptable-use considerations | Verification status |
|---|---:|---|---:|---:|---|---:|
| SearXNG | Open-source (AGPL/MIT family components vary) | none for self-hosted; public instances may limit | Yes — fully self-hostable | N/A (depends on instance) — recommend start: 10 req/sec per instance; tune by load | Respect upstream target sites' robots/ToS when proxying; do not use to scrape restricted content | needs_verification (legal: project policies for scraped content) |
| Tavily | Commercial / vendor-specific | API key / token (vendor) | No (hosted) | Vendor-defined — start conservative: 1 req/sec | Vendor TOS and data usage terms; confirm caching rules & PII handling | needs_verification (request docs & trial) |
| Brave Search API | Commercial API | API key (paid tiers) | No (hosted) | Public docs required; estimate: paid tiers allow higher throughput; default: 1 req/sec | Acceptable use per Brave; check caching & retention; may require paid plan for bulk | needs_verification (obtain API docs/plan) |
| Google Programmable Search (Custom Search JSON API) | Google terms; paid tiers | API key & CX (search engine id) | No | Historically strict free quota (small). Paid quotas via billing; default: 100/day free historically — DO NOT assume; use 1 req/sec in tests | Must follow Google API ToS; commercial use may require billing and licensing; caching and scraping restrictions apply | needs_verification (read Google Custom Search docs & pricing) |
| Perplexica | Vendor / possibly self-hosted semantic search | API key or local deployment | Possibly self-hosted (vendor-dependent) | Vendor-defined — conservative: 0.5–1 req/sec until verified | Semantic enrichment may surface PII; check vendor data retention & model provenance policies | needs_verification (get vendor docs / licensing) |

Detailed per-provider notes, verification checklist, and initial recommended safe defaults follow.

---

## SearXNG (meta-search / self-hosted)
- Purpose
  - Aggregates results from many search engines and provides a privacy-respecting meta-search. Useful for reproducible, privacy-preserving enrichment and for air-gapped or self-hosted deployments.
- License / Hosting
  - SearXNG is open source. Instances are typically self-hosted. The project uses open-source licenses — verify individual engine connectors' policies for scraping.
- Auth model
  - Self-hosted SearXNG does not require auth for internal use. Public instances may restrict usage.
- Acceptable-use policies
  - When SearXNG proxies requests to commercial engines, those engines’ terms apply. Do not use SearXNG to circumvent provider rate limits or ToS of upstream engines.
- Delta / release cadence
  - N/A (search results reflect upstream index cadence). No formal "release" cadence; freshness is provider-dependent.
- Rate-limit / throttling guidance
  - Depends on your hosting capacity and upstream engine policies. Conservative starting recommendation for iterative enrichment runs: 5–10 requests/sec per SearXNG instance, with backoff on errors.
- Self-hosting & provisioning
  - Can be deployed via Docker; recommended for offline or policy-sensitive environments.
- Verification actions
  - Deploy a local SearXNG instance and run representative queries; measure latency.
  - Confirm which upstream sources you plan to use and review their ToS.

## Tavily (vendor / hosted)
- Purpose
  - Commercial search/enrichment API (vendor-specific features).
- License / Hosting
  - Commercial; vendor license terms.
- Auth model
  - API key / bearer token (vendor).
- Acceptable-use policies
  - Vendor ToS govern caching, retention, commercial use. Obtain and review before production use.
- Rate-limit / throttling guidance
  - Vendor-defined. For initial tests assume: 1 req/sec per key until quotas verified.
- Verification actions
  - Request trial API key and documentation for rate limits and allowed caching.
  - Evaluate cost per 1k queries.

## Brave Search API
- Purpose
  - Search API from Brave; returns search results with privacy focus.
- License / Hosting
  - Hosted provider with documented API tiers (commercial).
- Auth model
  - API key / token (paid plans).
- Acceptable-use policies
  - Follow Brave's API terms; check for attribution and caching rules.
- Rate-limit / throttling guidance
  - Published in provider docs — obtain exact numbers. Conservative default: 1 req/sec until official quotas obtained.
- Verification actions
  - Request developer access / API key and the official rate-limit and pricing docs.

## Google Programmable Search (Custom Search JSON API)
- Purpose
  - Google’s custom search API for programmably running queries against configured search engines (supporting site-limited or web-wide queries depending on config).
- License / Hosting
  - Google Cloud API; usage subject to Google Cloud billing/pricing and ToS.
- Auth model
  - API key (and engine ID CX). Billing account for higher quotas.
- Acceptable-use policies
  - Must comply with Google API terms; scraping of Google results outside API is prohibited.
- Rate-limit / throttling guidance
  - Historically small free quota; paid quota increases per billing. DO NOT assume generous free limits.
  - Conservative default: 0.5–1 req/sec for tests (use billing for scale).
- Verification actions
  - Consult Google Custom Search docs and pricing pages to obtain current quotas and costs.

## Perplexica (semantic / vector search)
- Purpose
  - Provides semantic search/embedding-based results — good for entity disambiguation and contextual enrichment.
- License / Hosting
  - Vendor-dependent; may offer self-hosted or managed options.
- Auth model
  - API key for hosted service; self-hosted instances may not require auth.
- Acceptable-use policies
  - Check vendor's model-use and data-retention policies (particularly for PII).
- Rate-limit / throttling guidance
  - Vendor-defined; conservative default: 0.5–1 req/sec for initial tests.
- Verification actions
  - Request evaluation access and self-hosting docs. Validate model provenance and data retention policies.

---

## Cross-provider considerations (applies to all)
1. **Respect Upstream Terms**  
   - Many search providers have explicit prohibitions on scraping or caching. Use official APIs when available and respect headers like `Retry-After` and `robots.txt` when proxies are used.
2. **Conservative Defaults for Initial Integration**  
   - Use a conservative default throttle (1 request/sec or lower) for unknown providers; increase only after verifying provider quotas and costs.
3. **Caching & Legal Compliance**  
   - If you cache provider results, include TTLs aligned to provider allowances and legal requirements. For sensitive data (PII), encrypt stored results and minimize retention.
4. **Instrumentation & Adaptive Backoff**  
   - Implement backoff strategies (exponential backoff with jitter) and honor `429` / `Retry-After`.
   - Instrument request counts, latencies, and 429 rates per provider.
5. **Self-host vs Hosted Trade-off**  
   - Self-hosted (SearXNG / Perplexica) provides control and auditability but requires operational overhead.
   - Hosted providers reduce operational burden but add cost and external dependencies.

---

## Verification checklist (what to do next per provider)
For each provider listed above:
- [ ] Retrieve and save the provider's authoritative API documentation URL(s) (API reference, rate-limit docs, ToS).
- [ ] Obtain test credentials (API key) for hosted providers or spin up a local instance for self-hosted options.
- [ ] Validate published rate limits (including time window: per second/minute/hour) and record exact headers/behavior.
- [ ] Confirm allowed caching and retention policies in provider terms.
- [ ] Run a small pilot: 100 representative queries from the test prompt set to measure latency, reliability, and content quality.
- [ ] Capture costs (per 1k queries) for hosted providers and estimate projected monthly cost for nightly refresh at target volumes.

Suggested initial safe configuration (for benchmarking only)
- Concurrency: 1–2 concurrent requests per provider for initial tests.
- Throttle default: 1 request/sec per provider unless vendor docs specify higher allowance.
- Global orchestration: use a per-provider token bucket to enforce provider-level quotas and avoid throttling spikes when running parallel cohorts.

---

## Representative prompts (for benchmarking)
Create a curated suite of prompts covering:
- Company profile: "Give a short (2–3 sentence) summary of COMPANY_NAME including founding year, core product, and recent news."
- Principal Investigator (PI) bio: "List PI_NAME affiliation, current role, and three recent research keywords or publications."
- Award transition signal: "Has COMPANY_NAME announced a commercialization or spin-out related to AWARD_TOPIC since YEAR?"
- Patent-related query: "List patents (year, title) attributed to COMPANY_NAME in the last 5 years."
- Citation extraction: "Return at most 3 authoritative URLs that support the claim about COMPANY_NAME's product launch."

Store the prompt suite in `openspec/changes/evaluate-web-search-enrichment/prompts.json` for reproducible benchmarking.

---

## Deliverables for task 1.1 completion
- This inventory file (`search_providers.md`) committed to openspec (done).
- `providers.json` or equivalent authoritative mapping updated with discovered doc links and initial findings (use the automated discovery script to assist).
- A short PR checklist for verifying each provider (obtain docs, test keys, record rate-limits) — add results to `providers.json` and move provider `verification.status` to `verified`.

---

If you want, I can:
- Produce `openspec/changes/evaluate-web-search-enrichment/providers.json` analogous to the iterative API change and run an automated discovery pass against the documented `docs_url` values (like the other script did), or
- Start implementing provider adapter scaffolds (`src/search_providers/`) to instrument basic search calls in a controlled benchmarking harness.

Which do you want me to do next?