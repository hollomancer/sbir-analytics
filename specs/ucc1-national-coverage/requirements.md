# Requirements — UCC-1 National Coverage (49-State Public-Portal Expansion)

> **Status:** Not yet started — but a significant CA pilot implementation exists.
> `scripts/data/ucc/` contains the full pilot framework: `schema.py` (typed dicts
> `UCCFiling`, `UCCLifecycle`, `UCCMatch`, `ClassifiedSecuredParty`; enums
> `FilingType`, `UCCStatus`), `ca_extractor.py` (reference extractor),
> `matcher.py` (fuzzy debtor-side matching), `_common.py` (data path helpers
> with `SBIR_DATA_DIR` env override), and `cohort_state_filter.py`.
> **The task is to build a per-state extractor framework on top of these
> existing components** rather than from scratch.
>
> **CA pilot scope note:** Delaware was explicitly abandoned — no free public
> UCC search portal. The CA pilot ran against 70 of 3,639 cohort firms and
> was stopped by Imperva anti-bot protections; `curl_cffi` was used for
> JS-challenge bypass. These are known constraints the national expansion must
> account for per-state.
>
> Anchors inventory questions **F1** (secured-debt activity, debt-vs-equity
> composition) and **A-CP9** (UCC-1 financial-distress signal for choke-point
> firms) in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** F1 — what fraction of SBIR awardees show secured-debt activity, and what mix of equipment finance, depository-bank lending, and venture debt? A-CP9 — do UCC-1 lapse/lien-churn patterns flag financial distress among choke-point firms?
**Answers for:** entrepreneurial finance researchers, defense industrial base analysts, pipeline engineers
**Complexity tier:** Foundational data acquisition

---

## Done when

> A pipeline engineer can state: "UCC-1 financing statement extractors exist for all
> **49 states with free public SOS portals** (Delaware excluded — no free public
> portal; documented as `state_fips=10 unavailable`). The framework extends the CA
> pilot pattern in `scripts/data/ucc/ca_extractor.py`. Each state's SOS portal has a
> documented extractor with rate limits, session-handling, and anti-bot notes. The
> `UCC1StateExtractor` base class and registry sit alongside the existing `schema.py`
> typed dicts, which are reused unchanged. Extracted filings are normalized to
> `data/derived/ucc1_filings.parquet` with a `state_fips` column and refreshed on a
> per-state configurable cadence. National coverage reports carry an explicit
> Delaware-exclusion caveat and denominator adjustment because UCC jurisdiction follows
> state of organization, not HQ state."

---

## Introduction

UCC-1 financing statements are filed by secured creditors (equipment lenders, banks,
venture-debt providers) in the state where a company is organized. Each filing reveals:
the debtor name, the secured party (lender) name, and collateral type — a window into
a firm's secured-debt capital structure that is invisible in SEC filings (private
firms don't file 8-K or Form D for debt).

The CA pilot (`scripts/data/ucc/ca_extractor.py`, `specs/ucc1-financing-analysis/`)
scraped California bizfileOnline using `curl_cffi` to bypass Imperva/JS-challenge
anti-bot protections. Findings: equipment finance + community-bank lending patterns in
the CA SBIR population; absence of venture-debt lenders in the CA channel. The pilot
stopped at 70 of 3,639 cohort firms when anti-bot rate limits were hit.

**Existing framework (do not rewrite):**

| File | Role |
|------|------|
| `scripts/data/ucc/schema.py` | `UCCFiling`, `UCCLifecycle`, `UCCMatch`, `ClassifiedSecuredParty` typed dicts; `FilingType`, `UCCStatus` enums |
| `scripts/data/ucc/ca_extractor.py` | Reference extractor — becomes the first `UCC1StateExtractor` subclass |
| `scripts/data/ucc/matcher.py` | Fuzzy debtor-side matching (Jaro-Winkler + address + person-name rejection) |
| `scripts/data/ucc/_common.py` | `data_dir()` / `data_path()` helpers; respects `SBIR_DATA_DIR` env var |
| `scripts/data/ucc/cohort_state_filter.py` | Cohort firm filtering by state |

Extending to **49 states with free public portals** requires a per-state extractor —
each state Secretary of State portal has a different HTML structure, session model,
and rate-limit policy. **Delaware (state of organization for many private firms) has
no free public portal and is excluded from coverage.** Downstream F1/A-CP9 reporting
MUST surface this gap explicitly (coverage denominator excludes DE-organized firms;
national rates are not complete for DE-incorporated entities).

**Scope note:** Each state SOS portal is a distinct integration effort. This spec
scopes the national framework and the first five-state expansion. Remaining states
should be tackled in batches, prioritized by SBIR awardee concentration (TX, VA, MA,
CO, MD are the top non-CA states by SBIR award volume). Anti-bot mitigations
(Imperva, CAPTCHA, JS challenges) must be documented per state.

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
   state_fips, date_from, date_to)` → `list[UCCFiling]` (using the existing typed dict
   from `schema.py`).
2. THE `ca_extractor.py` SHALL be refactored to extend `UCC1StateExtractor` as the
   reference implementation, preserving existing behavior.
3. THE System SHALL implement a registry (`scripts/data/ucc/registry.py`) mapping each
   `state_fips` to its extractor class and configuration (base URL, session model,
   rate limit, anti-bot notes). Delaware (FIPS 10) SHALL be absent from the registry
   with a documented comment explaining no free public portal exists.
4. WHEN an extractor for a state is not yet implemented, THE registry SHALL return a
   `NotImplementedExtractor` that logs a warning rather than silently skipping.
5. THE base class SHALL document the expected anti-bot pattern per-state (CAPTCHA type,
   JS challenge, Imperva) so each implementation includes session-handling notes.

### Requirement 2 — Priority-state extractors (first batch)

#### Acceptance Criteria

1. THE System SHALL implement extractors for the five states with the highest SBIR
   awardee concentration after California: Texas, Virginia, Massachusetts, Colorado,
   and Maryland — covering approximately 35% of non-CA SBIR award volume.
2. EACH extractor SHALL document: the SOS portal URL, session/cookie requirements,
   known anti-bot measures (CAPTCHA, JS challenges, Imperva), rate limit
   (requests/minute), and field mapping to `UCCFiling` keys.
3. EACH extractor SHALL be tested against at least one known SBIR awardee in that
   state (verifiable via the CA-pilot entity resolution pattern in `matcher.py`).

### Requirement 3 — Normalization and storage

#### Acceptance Criteria

1. THE System SHALL normalize all state extractor outputs to the existing `UCCFiling`
   typed dict schema from `schema.py`, adding a `state_fips` column to disambiguate
   multi-state output. The `ClassifiedSecuredParty` taxonomy
   (venture_debt / equipment_finance / bank_depository / tax_authority / foreign /
   other / unknown) SHALL be applied post-extraction using the existing classification
   logic.
2. THE System SHALL persist to `data/derived/ucc1_filings.parquet`, partitioned by
   `state_fips`, appending new records and updating existing ones on re-extraction.
3. THE System SHALL link filings to SBIR awardees via entity resolution using the
   existing `matcher.py` Jaro-Winkler + address-overlap + person-name-rejection
   pipeline, populating `debtor_uei` via UEI → CAGE → DUNS → fuzzy-name cascade
   consistent with `SAMGovAPIClient`.
4. THE System SHALL emit coverage metadata (per-state extractor status, Delaware
   exclusion flag, and DE-organized cohort share) alongside F1/A-CP9 outputs so
   consumers do not treat 49-state portal coverage as a complete national universe.

### Requirement 4 — Cadence and scheduling

#### Acceptance Criteria

1. THE System SHALL support per-state configurable refresh cadence (default: monthly)
   via `config/base.yaml` under `enrichment_refresh.ucc1.*`.
2. THE System SHALL track per-state freshness in `data/state/enrichment_refresh_state.json`
   alongside other enrichment sources, consistent with `specs/iterative_api_enrichment/`,
   using the `data_path()` helper from `_common.py` for all path resolution.
3. WHEN a state portal is unreachable or returns an error (including anti-bot blocks),
   THE System SHALL retain the prior extract and emit a staleness warning rather than
   clearing existing records.
