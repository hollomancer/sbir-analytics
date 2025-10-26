# Iterative API Enrichment — External API Inventory
This document inventories the external APIs referenced (or commonly used) for enrichment in the repository and captures the metadata needed for designing an iterative (delta-based) enrichment strategy. This is intended to satisfy task 1.1: "Inventory every external enrichment API referenced in repo docs/config and document their release cadence + throttling limits."

For each API below I give:
- Purpose / common enrichment use-cases in the project
- Auth model (what we need to configure)
- Release cadence or data freshness guidance (what to expect)
- Known delta/incremental signals (fields or headers to support "only fetch changed data")
- Pagination / large-result behavior
- Rate-limit / throttling guidance (if publicly documented, otherwise recommended safe defaults)
- Notes & integration considerations (caching, retries, backoff, local testing)
- Links / next actions (what to verify, what secrets/accounts to obtain)

Where public documentation or quota numbers are unclear, I mark that clearly and list immediate action items to obtain the definitive values.

---

## 1) SBIR.gov (Awards Data)
- Purpose
  - Primary source of SBIR award records. Used for initial ingestion and periodic refresh of award-level fields (title, abstract, agency, solicitation, award amount).
- Auth model
  - Public bulk CSV downloads are published (no auth). If an API is used, check the SBIR.gov API documentation for any API key needs.
- Release cadence / freshness
  - SBIR.gov typically provides monthly or periodic CSV exports. Expect monthly updates (confirm with SBIR.gov docs).
- Delta signals
  - The authoritative bulk export includes full rows; delta detection is usually by `award_date`, `last_updated` (if present) or by diffing unique award_id and checking new/changed fields.
- Pagination / bulk
  - Primary pattern is downloadable CSV(s) and not page-by-page API; design connectors to stream/process CSVs in chunks.
- Rate limits / throttling
  - For bulk downloads: limited only by hosting constraints. For any API endpoints, check provider docs.
- Integration notes
  - Prefer bulk CSV ingestion for initial full sync; use incremental diffing to detect changes.
  - Keep local sample fixtures to simulate incremental updates.
- Links / next actions
  - Confirm the official SBIR.gov export cadence and any available API docs.
  - Capture the canonical field names and example rows into `tests/fixtures`.

---

## 2) USAspending (USASpending.gov)
- Purpose
  - Transaction and recipient enrichment (award-level reconciliation, NAICS, place-of-performance, transaction history).
- Auth model
  - Public API endpoints exist. Some endpoints are public; verify if API key is required for high-volume usage.
- Release cadence / freshness
  - USAspending datasets are updated continuously with periodic dumps; official dump cadence can vary. Assume daily/weekly internal updates and occasional full snapshots.
- Delta signals
  - Transaction records often have `modification_date` / `modification_number` / `last_updated` fields useful for incremental pulls.
  - Prefer using server-provided `last_modified` or `If-Modified-Since` where supported.
- Pagination / bulk
  - Supports API pagination and also provides bulk dumps (COPY dumps). For large-volume scanning prefer streaming COPY dumps or DuckDB-backed sampling.
- Rate limits / throttling
  - Public docs sometimes limit requests; if using the public API for many requests, assume conservative limits and batch requests.
  - Action: query provider docs for exact rate limits and recommended usage patterns.
- Integration notes
  - For iterative enrichment, maintain per-source cursor based on `modification_date` and stored `payload_hash`.
  - Use chunked processing when scanning dumps. The repo already contains tools for streaming data from a zip/COPY file.
- Links / next actions
  - Retrieve definitive API rate limit docs and replication of `modification_number` semantics.

---

## 3) SAM.gov
- Purpose
  - Awardee matching and entity-level enrichment (CAGE codes, registration metadata).
- Auth model
  - API key required for SAM.gov APIs. Newer SAM/Gov APIs may require registration of an API key.
- Release cadence / freshness
  - SAM.gov data changes frequently (registrations updated as vendors update), expect near-real-time changes with periodic propagation windows.
- Delta signals
  - Records often include `lastModifiedDate` or `regDate` fields. Use `If-Modified-Since` or a last-updated cursor when available.
- Pagination / bulk
  - Both API and bulk data options are available; check latest provider docs for endpoints and bulk exports.
- Rate limits / throttling
  - SAM enforces request limits per API key (check docs). Conservative default for initial testing: 5 requests/sec or fewer; implement exponential backoff on HTTP 429.
- Integration notes
  - Implement a centralized retry/backoff policy (e.g., exponential backoff with jitter).
  - Cache SAM.gov responses (entity-level) for matching work and avoid repeated lookups for the same entity.
- Links / next actions
  - Obtain SAM.gov developer documentation and request API keys for dev and CI use.

---

## 4) NIH RePORTER / NIH APIs
- Purpose
  - Enrich awards with NIH-related data (project abstracts, investigators, funding activity for NIH-relevant awards).
- Auth model
  - NIH RePORTER public endpoints typically do not require authentication for basic queries.
- Release cadence / freshness
  - NIH updates continue across fiscal cycles; typical releases are monthly/quarterly for some datasets.
- Delta signals
  - NIH frequently provides `lastUpdate` or `project_start` / `project_end`; use `lastUpdate` or `lastMod` if present.
- Pagination / bulk
  - API supports pagination and offers bulk export; use appropriate paging parameters and chunk sizes.
- Rate limits / throttling
  - Public API often has usage guidelines; if unauthenticated, throttle aggressively (e.g., 1–2 requests/sec).
- Integration notes
  - A robust matching strategy (title/PI/funding match) helps reduce false positives. Cache results and implement local fixtures for testing.
- Links / next actions
  - Confirm NIH RePORTER query parameters for `lastUpdate` filters to support incremental runs.

---

## 5) PatentsView
- Purpose
  - Enrich organizations with patent activity and dates; used for technology transfer signals.
- Auth model
  - Public API; no API key required for typical usage.
- Release cadence / freshness
  - PatentsView generally updates periodically (monthly/quarterly). Check their API docs for release cadence.
- Delta signals
  - Patent records have `patent_date`, `last_updated` timestamps—use these for incremental queries.
- Pagination / bulk
  - Supports pagination and complex queries; for large volumes use paging and filters.
- Rate limits / throttling
  - Public endpoints have polite-use policies; use conservative rates (1–2 req/sec).
- Integration notes
  - Patent queries can be broad; design targeted queries per organization and limit fields to reduce payload size.
- Links / next actions
  - Verify exact delta fields and best practices in PatentsView documentation.

---

## 6) OpenCorporates
- Purpose
  - Company registry lookup for normalized company metadata, jurisdictions, corporate identifiers.
- Auth model
  - API key required for higher-rate access; unauthenticated usage is limited.
- Release cadence / freshness
  - Registry data updates depend on jurisdiction; OpenCorporates indexes changes regularly.
- Delta signals
  - Company records often contain `updated_at` or `last_updated` fields.
- Pagination / bulk
  - Supports paginated queries; offers bulk data via license for large-scale access.
- Rate limits / throttling
  - Free tier has strict rate limits; paid plans increase allowed quotas. Always read provider docs for exact quotas.
- Integration notes
  - For high-volume enrichment, coordinate with OpenCorporates for bulk access or a paid plan.
  - Respect robot / terms of service for web scraping — prefer official API.
- Links / next actions
  - Decide whether to use OpenCorporates paid/enterprise access for bulk matching.

---

## 7) SEC EDGAR
- Purpose
  - Financial filings & company disclosures; relevant for public company enrichment and timeline events.
- Auth model
  - Public (no API key for RSS / EDGAR index). The new EDGAR APIs may have different access rules—check docs.
- Release cadence / freshness
  - Filings are posted continuously; EDGAR indexes nightly and provides filings on an ongoing basis.
- Delta signals
  - Filing dates, accession numbers, and index change timestamps are the natural delta signals.
- Pagination / bulk
  - EDGAR supports both feed/RSS and API endpoints with paging.
- Rate limits / throttling
  - EDGAR enforces polite request rates; historically they request no more than one request per second for heavy crawls. Confirm current guidelines.
- Integration notes
  - Use accession numbers and filing dates for idempotent ingestion; avoid heavy scraping in short windows.
- Links / next actions
  - Consult SEC EDGAR API docs for up-to-date usage guidance.

---

## 8) DLA / CAGE / BIS (Defense & CAGE registries)
- Purpose
  - Entity identifiers (CAGE codes) and export control data (BIS), useful for defense contracting enrichment and vendor validation.
- Auth model
  - Varies by source; some data is on SAM or other government sources, others require access agreements.
- Release cadence / freshness
  - Registries update irregularly; expect updates when companies change registration data.
- Delta signals
  - `last_updated` or a similar registration timestamp if present.
- Pagination / bulk
  - Often provided via SAM or separate registry dumps; may require special access.
- Rate limits / throttling
  - Not publicly standardized; follow provider guidance.
- Integration notes
  - These sources may have restricted access; ensure compliance with access policies before pulling large amounts.
- Links / next actions
  - Identify authoritative endpoint(s) for CAGE/BIS used in our enrichment pipeline and request access if required.

---

## 9) ORCID
- Purpose
  - Author / investigator identifier resolution (PI affiliation and publication links).
- Auth model
  - OAuth2 for authenticated requests; a public member API may be available with keys.
- Release cadence / freshness
  - ORCID records are updated by researchers; updates can be frequent for active researchers.
- Delta signals
  - `last-modified-date` in ORCID records is a standard incremental indicator.
- Pagination / bulk
  - Provides search + paginated results; bulk access via ORCID data services may require agreements.
- Rate limits / throttling
  - ORCID enforces API usage rules that vary by endpoint and client type; consult docs.
- Integration notes
  - For matching PIs, require strict matching rules and caching to avoid repeated lookups.
- Links / next actions
  - Get ORCID API policy and developer registration details for production use.

---

## 10) OpenAlex
- Purpose
  - Scholarly metadata (authors, works, institutions); alternative to CrossRef and OpenAlex is popular for open academic metadata enrichment.
- Auth model
  - Public, no API key needed for modest usage; the API supports rate-limited access.
- Release cadence / freshness
  - OpenAlex updates continuously and provides metadata change dates.
- Delta signals
  - `updated_date` fields on works/authors are useful for incremental pulls.
- Pagination / bulk
  - Pagination supported; OpenAlex offers data dumps for bulk use.
- Rate limits / throttling
  - Public rate limits exist; check docs. Implement conservative defaults and backoff for heavy loads.
- Integration notes
  - Use work/author IDs and updated timestamps for delta detection.
- Links / next actions
  - Add OpenAlex to config `enrichment_refresh` when ingestion cadence is defined.

---

## 11) OpenFEC
- Purpose
  - Campaign / PAC / political contributor data; relevant for political funding enrichment.
- Auth model
  - API key required.
- Release cadence / freshness
  - Data is updated with filings and periodic batches; check docs.
- Delta signals
  - Filing date and last_updated fields.
- Pagination / bulk
  - Paginated API and bulk downloads available.
- Rate limits / throttling
  - API key required; rate limits documented per API key (check docs).
- Integration notes
  - Only add if political funding is relevant to enrichment scope; treat as optional connector behind feature flag.
- Links / next actions
  - Determine whether this source is required for current enrichment goals.

---

## Generic integration guidance (applies to all connectors)
1. Authentication & secrets
   - Add per-source config keys in `config/base.yaml` (or `config/docker.yaml` for container defaults):
     - api_key / client_id / client_secret / oauth settings / base_url / rate_limit_hint.
   - Do not commit secrets. Use `.env` for local dev and repository secrets / CI OIDC for CI.

2. Rate limiting and backoff
   - Implement a shared connector base using `httpx.AsyncClient` + `tenacity`:
     - Exponential backoff with jitter on 429/5xx.
     - Respect `Retry-After` header when present.
     - Use adaptive concurrency (limit concurrent requests per source based on documented limits).
   - Default conservative limit: 1–5 requests/sec per API until provider docs confirm higher quotas.

3. Delta & cursor management
   - Maintain a per-source cursor file or state object (e.g., `data/state/enrichment_refresh_state.json`).
   - Record:
     - last_successful_timestamp
     - last_attempt_timestamp
     - per-entity payload hash (for change detection)
     - pagination cursor / next token
   - Prefer provider-managed delta (ETags, modified_since, change feeds) where available.

4. Pagination & batching
   - Implement connectors to page results using provider pagination parameters (limit/offset, page token).
   - Always prefer server-side filters (date range, updated_after) to reduce data scanned.
   - Provide chunking controls in config: `batch_size`, `concurrency`, `parallel_partitions`.

5. Contract tests and fixtures
   - Create and maintain recorded HTTP fixtures for unit tests (VCR-style or mocked httpx).
   - Capture sample responses for typical delta/diff scenarios: no-change (304), partial updates, rate-limited responses.

6. Local dev & CI
   - Provide `--dry-run` modes and `--limit` flags for connectors to allow safe local testing.
   - Provide a mock server or MinIO-like service for integration tests to avoid hitting provider quotas during CI.
   - Document how to obtain API keys and which environment variables to set.

7. Operational monitoring
   - Emit metrics per source: requests, successes, failures, rate-limited events, average latency, freshness coverage (% within SLA).
   - Store metrics artifacts in `artifacts/metrics` for historical trend analysis.

---

## Task 1.1 — Immediate next actions checklist (what to do to complete the inventory)
- [ ] For each API above, retrieve and link the authoritative provider documentation pages (API reference, rate limits, auth).
- [ ] For each API, obtain a test API key or identify test endpoints (for SAM.gov, OpenCorporates, OpenFEC, etc.).
- [ ] Populate `config/base.yaml` with `enrichment_refresh` placeholders for each source (cadence, default batch_size, concurrency_hint).
- [ ] Add a small `openspec` metadata JSON describing the authoritative docs/contacts for each provider and commit it as `openspec/changes/add-iterative-api-enrichment/providers.json`.
- [ ] Add quick local test instructions to `docs/enrichment/iterative-refresh.md` referencing the credentials and minimal query examples for each API.
- [ ] Reserve quota budget / CI usage policy for initial integration testing (to avoid provider rate limit blocks).

---

## Notes for reviewers / owners
- This file intentionally focuses on the integration-relevant qualities of each API (delta signals, auth, rate limits) rather than detailed API parameter lists — the latter should be collected from the official provider docs and recorded in `openspec/providers.json`.
- Wherever specific quotas and headers are needed (for example, `Retry-After` semantics or exact `If-Modified-Since` support), fetch the provider docs and update this inventory with exact values.
- For the next implementation steps, I recommend starting with NIH, SAM.gov, USAspending, and PatentsView connectors (these are already referenced in the repo and provide the highest immediate enrichment value). Add more connectors only after a validated iterative refresh pattern is in place.

---