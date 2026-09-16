# Perplexity Intel Enricher (PitchBook + CB Insights) — Requirements

> **Lifecycle status:** Gated backlog
> **Spec-file progress:** In progress
> Anchors inventory question **F3** (SBIR-to-private-capital leverage) and
> **A2** (awardee commercialization outcomes) in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `pipelines`
(enrichment primitive; downstream `evidence`-tier analyses consume the output)

**Research question anchor:** F3 — post-award VC/PE formation rates by agency,
phase, and CET area; A2 — awardee survival and exit-type distribution
**Answers for:** entrepreneurial finance researcher, SBIR program manager
**RQ complexity tier:** Relational

---

## Done when

An analyst can state:

> "Of SBIR Phase II awardees in [agency/CET cohort], X% have a confirmed
> PitchBook record. Of those, Y% raised at least one post-award funding
> round. Z% were acquired; W% are confirmed defunct. The CB Insights sector
> classification aligns with the existing CET taxonomy at a P% rate."

Satisfaction requires:

1. `company_intel()` runs against a benchmark cohort of ≥200 SBIR awardees
   and returns a match-rate report.
2. A cost/latency profile is recorded (sonar-pro API cost per record,
   p50/p95 latency).
3. The `PerplexityIntelRecord` fields are assessed for accuracy against
   a 20-record spot-check versus canonical PitchBook data (if accessible)
   or public funding announcements.
4. A go/no-go decision is documented in this file under **Evaluation Results**.

---

## Background

Existing enrichers (OpenCorporates, SEC EDGAR, SAM.gov) confirm company
existence, registration status, and public filings — but none surface
post-award private funding rounds or market-positioning context. The
F3 leverage-ratio question (does SBIR investment catalyze VC formation?)
requires a firmographic layer that extends through the post-award lifecycle.
Perplexity's PitchBook Essentials and CB Insights Premium Source connectors
provide an accessible entry point without a direct PitchBook API contract.

## Glossary

- **PitchBook Essentials**: The dataset subset available via Perplexity
  Premium Sources — firmographics, funding round *count*, investor names,
  and acquisition status. Does **not** include round financials,
  valuations, or cap-table data.
- **CB Insights Premium Source**: Curated subset of CB Insights research
  reports and market maps accessible via Perplexity connectors. Not
  the full CB Insights library.
- **Connector freshness**: The lag between PitchBook/CB Insights data
  updates and Perplexity's indexed version — unknown; must be assessed
  empirically.

---

## Requirements

### Requirement 1 — Company-level firmographic lookup

**User story:** As an entrepreneurial finance researcher, I want to look up
confirmed PitchBook presence and post-award funding activity for an SBIR
awardee by legal name, so that I can classify awardees into
"catalyzed VC" vs. "no follow-on capital" cohorts for leverage analysis.

#### Acceptance Criteria

1. WHEN `company_intel(company_name)` is called with a valid SBIR awardee
   name, THE System SHALL return a `PerplexityIntelRecord` with
   `pitchbook_confirmed`, `funding_rounds_confirmed`, `latest_funding_stage`,
   and `investor_names` populated where available in PitchBook Essentials.
2. WHEN PitchBook has no record for the company, THE System SHALL return
   `None` (not raise an exception) and log at DEBUG level.
3. WHEN the Perplexity API returns a non-JSON or malformed response,
   THE System SHALL return a partial `PerplexityIntelRecord` with
   `raw_response` populated and all structured fields set to `None`/empty.
4. WHEN `PERPLEXITY_API_KEY` is not set, THE System SHALL raise
   `ConfigurationError` on client instantiation (not on first call).
5. WHEN called with `include_cbinsights=True` (default), THE System SHALL
   also populate `cbinsights_confirmed` and `sector_classification`.

---

### Requirement 2 — Market-context sector lookup

**User story:** As a SBIR program manager, I want to place a funded
technology area within a CB Insights market-map segment, so that I can
assess whether the portfolio is concentrated in crowded or emerging
market segments and brief accordingly.

#### Acceptance Criteria

1. WHEN `market_context(technology_area, agency=agency)` is called,
   THE System SHALL return a `MarketContextRecord` with
   `sector_classification`, `competitive_density`, and `key_players`
   populated where available in CB Insights.
2. WHEN CB Insights has no relevant content for the technology area,
   THE System SHALL return `None` and log at DEBUG level.
3. `competitive_density` SHALL be constrained to one of:
   `"crowded"`, `"emerging"`, `"sparse"`, or `None`.

---

### Requirement 3 — Evaluation benchmark

**User story:** As a pipeline engineer, I want a documented evaluation
of match-rate, accuracy, cost, and latency before this enricher is
promoted to standard use, so that I can make a data-driven go/no-go
decision.

#### Acceptance Criteria

1. WHEN run against the benchmark cohort (200 awardees drawn from
   FY2018–FY2022 Phase II awards across DoD, NIH, NSF), THE System
   SHALL produce a match-rate report with:
   - Overall PitchBook match rate
   - Match rate stratified by agency and CET area
   - CB Insights sector classification coverage rate
2. A cost/latency table SHALL be recorded: sonar-pro API cost per
   record (USD), p50 and p95 latency (seconds).
3. A 20-record spot-check table SHALL compare `funding_rounds_confirmed`
   and `acquisition_status` against a reference source (public
   CrunchBase, press releases, or direct PitchBook access if available).
4. A go/no-go decision SHALL be documented under **Evaluation Results**
   below before this enricher is merged to `main`.

---

## Open Questions

| # | Question | Blocks |
|---|---|---|
| OQ-1 | What is the PitchBook Essentials match rate for small, pre-revenue SBIR Phase I awardees (the majority of the corpus)? PitchBook skews toward later-stage firms. | Req 3, go/no-go |
| OQ-2 | How stale is Perplexity's PitchBook index? A 6–12 month lag would miss recent exits. | Req 1 accuracy |
| OQ-3 | Does sonar-pro reliably return valid JSON at scale, or does the JSON-extraction regex need a more robust fallback (e.g., `instructor` / structured outputs)? | Req 1, Req 2 |
| OQ-4 | Should this be a subdirectory enricher (`perplexity_intel/`) with separate `client.py`, `models.py`, `prompts.py`? Flat file is fine for evaluation; promote to subdir if it survives go/no-go. | Architecture |
| OQ-5 | CB Insights sector labels — do they align with the existing CET taxonomy well enough to use as a cross-walk, or will a separate mapping table be required? | Req 2, downstream analysis |

---

## Dependencies

- `sbir_etl.enrichers.base_client.BaseAsyncAPIClient` — EXISTS
- `sbir_etl.enrichers.rate_limiting.RateLimiter` — EXISTS
- `sbir_etl.exceptions.ConfigurationError` — EXISTS
- `PERPLEXITY_API_KEY` environment variable — **NOT YET in `.env.example`**
  (add before merging to `main`)
- Perplexity `sonar-pro` subscription with PitchBook + CB Insights
  Premium Sources enabled — **CONFIRM account tier**
- Benchmark cohort selection: coordinate with `specs/phase-iii-census/`
  for FY2018–FY2022 Phase II awardee list

---

## Evaluation Results

> *(Populate before merge to `main`)*

| Metric | Value | Notes |
|---|---|---|
| PitchBook match rate (overall) | — | |
| PitchBook match rate (DoD Phase II) | — | |
| PitchBook match rate (NIH Phase II) | — | |
| CB Insights coverage rate | — | |
| Cost per record (USD, sonar-pro) | — | |
| p50 latency (s) | — | |
| p95 latency (s) | — | |
| JSON parse failure rate | — | |
| Spot-check accuracy (funding rounds) | — | |
| Spot-check accuracy (acquisition status) | — | |
| **Go / No-Go** | **PENDING** | |
