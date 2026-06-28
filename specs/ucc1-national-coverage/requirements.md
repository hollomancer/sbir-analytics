# Requirements — UCC-1 National Coverage (50-State Expansion)

> **Status:** Not yet started. California pilot is live (PRs #303 / #305, extractor
> at `scripts/data/ucc/ca_extractor.py`). CA pilot findings: equipment finance +
> community-bank lending patterns; absence of venture-debt lenders in the CA channel.
> Anchors inventory questions **F1** (secured-debt activity, debt-vs-equity composition)
> and **A-CP9** (UCC-1 financial-distress signal for choke-point firms) in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** F1 — what fraction of SBIR awardees show secured-debt activity, and what mix of equipment finance, depository-bank lending, and venture debt? A-CP9 — do UCC-1 lapse/lien-churn patterns flag financial distress among choke-point firms?
**Answers for:** entrepreneurial finance researchers, defense industrial base analysts, pipeline engineers
**Complexity tier:** Foundational data acquisition

---

## Done when

> A pipeline engineer can state: "UCC-1 financing statement extractors exist for all
> 50 states, extending the CA pilot pattern. Each state's SOS portal has a documented
> extractor with rate limits, session-handling, and anti-bot notes. Extracted filings
> are normalized to `data/derived/ucc1_filings.parquet` with a `state_fips` column
> and refreshed on a per-state configurable cadence. National coverage enables the
> F1 debt-vs-equity question to be answered for the full SBIR awardee universe, not
> just California-incorporated firms."

---

## Introduction

UCC-1 financing statements are filed by secured creditors (equipment lenders, banks,
venture-debt providers) in the state where a company is organized. Each filing reveals:
the debtor name, the secured party (lender) name, and collateral type — a window into
a firm's secured-debt capital structure that is invisible in SEC filings (private
firms don't file 8-K or Form D for debt).

The CA pilot (`scripts/data/ucc/ca_extractor.py`, `specs/ucc1-financing-analysis/`)
scraped California bizfileOnline using `curl_cffi` to bypass anti-bot protections and
found equipment finance + community-bank lending patterns in the CA SBIR population.
Extending to all 50 states requires a per-state extractor — each state Secretary of
State portal has a different HTML structure, session model, and rate-limit policy.

**Scope note:** Each state SOS portal is a distinct integration effort. This spec
scopes the national framework and the first-five-state expansion. Remaining states
should be tackled in batches, prioritized by SBIR awardee concentration (TX, VA, MA,
CO, MD are the top non-CA states by SBIR award volume).

---

## User Stories

**As an entrepreneurial finance researcher,** I want UCC-1 coverage extended beyond
California so that the debt-vs-equity composition question (F1) reflects the full
national SBIR awardee population rather than a single-state pilot.

**As a defense industrial base analyst,** I want UCC-1 lapse and lien-churn data for
choke-point firms across all states so that the A-CP9 financial-distress signal is
computable for the full set of thin-base CET area suppliers, not just those
incorporated in California.

---

## Requirements

### Requirement 1 — Per-state extractor framework

#### Acceptance Criteria

1. THE System SHALL define a `UCC1StateExtractor` base class in
   `scripts/data/ucc/base_extractor.py` with the interface: `fetch_filings(debtor_name,
   state_fips, date_from, date_to)` → raw filing records.
2. THE `ca_extractor.py` SHALL be refactored to extend `UCC1StateExtractor` as the
   reference implementation.
3. THE System SHALL implement a registry (`scripts/data/ucc/registry.py`) mapping each
   `state_fips` to its extractor class and configuration (base URL, session model,
   rate limit, anti-bot notes).
4. WHEN an extractor for a state is not yet implemented, THE registry SHALL return a
   `NotImplementedExtractor` that logs a warning rather than silently skipping.

### Requirement 2 — Priority-state extractors (first batch)

#### Acceptance Criteria

1. THE System SHALL implement extractors for the five states with the highest SBIR
   awardee concentration after California: Texas, Virginia, Massachusetts, Colorado,
   and Maryland — covering approximately 35% of non-CA SBIR award volume.
2. EACH extractor SHALL document: the SOS portal URL, session/cookie requirements,
   known anti-bot measures (CAPTCHA, JS challenges), rate limit (requests/minute),
   and field mapping for debtor name, secured party name, and collateral description.
3. EACH extractor SHALL be tested against at least one known SBIR awardee in that
   state (verifiable via the CA-pilot entity resolution pattern).

### Requirement 3 — Normalization and storage

#### Acceptance Criteria

1. THE System SHALL normalize all state extractor outputs to a common schema:
   `state_fips`, `filing_number`, `debtor_name`, `debtor_uei` (if resolved),
   `secured_party_name`, `secured_party_type` (equipment / bank / venture-debt /
   unknown), `collateral_desc`, `filing_date`, `lapse_date`, `status`
   (active / lapsed / terminated), `extracted_at`.
2. THE System SHALL persist to `data/derived/ucc1_filings.parquet`, partitioned by
   `state_fips`, appending new records and updating existing ones on re-extraction.
3. THE System SHALL link filings to SBIR awardees via entity resolution
   (`debtor_uei` backfill using the same UEI → CAGE → DUNS → fuzzy-name cascade as
   `SAMGovAPIClient`), populating `debtor_uei` where a match is found.

### Requirement 4 — Cadence and scheduling

#### Acceptance Criteria

1. THE System SHALL support per-state configurable refresh cadence (default: monthly)
   via `config/base.yaml` under `enrichment_refresh.ucc1.*`.
2. THE System SHALL track per-state freshness in `data/state/enrichment_refresh_state.json`
   alongside other enrichment sources, consistent with `specs/iterative_api_enrichment/`.
3. WHEN a state portal is unreachable or returns an error on extraction, THE System
   SHALL retain the prior extract and emit a staleness warning rather than clearing
   existing records.
