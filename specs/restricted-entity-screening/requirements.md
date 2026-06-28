# Requirements — Restricted-Entity Screening Lists Ingestion

> **Status:** Not yet started. Current FOCI exposure coverage is "SEC-filer subset
> only." Full screening requires ingesting the eight lists mandated by Pub. L. 119-83.
> Anchors inventory questions **A1** (FOCI exposure share per CET area) and **A2**
> (adversary-affiliation screening) in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** A1 — foreign ownership / control (FOCI) exposure share per CET area (A-CP4); A2 — adversary-affiliation screening of awardees and key personnel
**Answers for:** DoD acquisition leadership, OSTP, congressional defense committees
**Complexity tier:** Foundational data acquisition

---

## Done when

> A DoD acquisition analyst can state: "All eight Pub. L. 119-83 restricted-entity
> lists are ingested and normalized in `data/reference/restricted_entities/`. The
> `RestrictedEntityScreener` checks any SBIR awardee name or UEI against all eight
> lists in a single pass and returns a match report with list name, match confidence,
> and entity detail. Lists are refreshed weekly. FOCI exposure share per CET area is
> computable as a Dagster asset."

---

## Introduction

Pub. L. 119-83 (SBIR/STTR reauthorization, signed April 13, 2026) mandates
risk-based due-diligence screening against eight restricted-entity lists for SBIR/STTR
applicants. The pipeline currently detects FOCI exposure only for the SEC-filer subset
(via EDGAR Exhibit 21 / 8-K ownership disclosures), which misses private SBIR firms
— the majority of the awardee population.

Ingesting all eight lists and building a `RestrictedEntityScreener` enables the A1
FOCI exposure question to be answered for the full awardee universe, not just the
disclosed/structured ownership subset.

**The eight lists (all publicly downloadable):**

| List | Authority | Format |
|------|-----------|--------|
| UFLPA Entity List | CBP / DHS | CSV |
| NS-CMIC List (Non-SDN Chinese Military-Industrial Complex) | OFAC / Treasury | CSV |
| Section 889 Prohibition List | GSA / FCC | CSV |
| 1260H List | DoD | CSV / PDF |
| Military End-User (MEU) List | BIS / Commerce | CSV |
| BIS Entity List | BIS / Commerce | CSV |
| FCC Covered List | FCC | JSON |
| CBP WRO/Findings List | CBP / DHS | CSV |

---

## User Stories

**As a DoD acquisition analyst,** I want every SBIR awardee screened against all
eight Pub. L. 119-83 restricted-entity lists, so that I can produce the FOCI exposure
share per CET area required by the statute's risk-based due-diligence framework.

**As a pipeline engineer,** I want the eight lists normalized to a common schema and
refreshed weekly, so that new additions to any list are reflected in the next
enrichment run without manual intervention.

---

## Requirements

### Requirement 1 — List ingestion and normalization

#### Acceptance Criteria

1. THE System SHALL implement a downloader for each of the eight lists, fetching from
   their authoritative government sources on a configurable schedule (default: weekly).
2. THE System SHALL normalize each list to a common schema:
   `entity_name`, `entity_aliases`, `country`, `list_name`, `list_authority`,
   `effective_date`, `source_url`, `raw_id`.
3. THE System SHALL persist each list to
   `data/reference/restricted_entities/<list_name>.parquet` and maintain a
   `data/reference/restricted_entities/manifest.json` recording the last-fetched
   timestamp and record count per list.
4. WHEN a list source URL returns a non-200 status, THE System SHALL retain the prior
   version and emit an alert so the staleness does not go undetected.

### Requirement 2 — RestrictedEntityScreener

#### Acceptance Criteria

1. THE `RestrictedEntityScreener` SHALL accept an entity name, UEI, or CAGE code and
   return a list of matches across all eight lists, including list name, match
   confidence (exact / fuzzy / alias), and matched entity detail.
2. THE screener SHALL use exact match on UEI/CAGE where available, and fuzzy name
   matching (threshold ≥ 0.85, same as `SAMGovAPIClient`) for name-only checks.
3. THE screener SHALL complete a single-entity check in < 500ms for the full
   eight-list corpus.
4. THE screener SHALL expose a batch mode for screening the full SBIR awardee
   universe in one pass, with results written to
   `data/derived/restricted_entity_matches.parquet`.

### Requirement 3 — FOCI exposure Dagster asset

#### Acceptance Criteria

1. THE System SHALL implement a `foci_exposure_by_cet` Dagster asset in the
   `industrial_base` asset group that:
   - Joins `restricted_entity_matches` to SBIR awards via entity resolution
   - Computes share of awardees and award dollars per CET area with at least one
     list match
   - Emits the result to `reports/foci-exposure/foci_exposure_<period>.parquet`
2. THE asset SHALL distinguish between the eight lists in its output so that
   consumers can filter to specific statutory concerns (e.g., UFLPA for Xinjiang
   supply-chain exposure vs. NS-CMIC for military-industrial complex).
3. ALL match results SHALL carry the caveat that this is a LOWER-BOUND proxy —
   structured lists detect only disclosed/public entity relationships, not private
   beneficial ownership.
