# Requirements — NIH RePORTER Enrichment Source

> **Status:** Not yet started. NIH RePORTER is the third pending source in
> `specs/iterative_api_enrichment/` (USAspending iterative enrichment is live;
> SAM.gov, NIH RePORTER, and PatentsView are pending).
> Anchors inventory question **E3** (data freshness) in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** E3 — data-freshness lag for NIH as an SBIR funding source; iterative enrichment refresh for NIH grant records
**Answers for:** pipeline engineers, NIH SBIR program managers
**Complexity tier:** Foundational data acquisition

---

## Done when

> A pipeline engineer can state: "NIH RePORTER SBIR/STTR grant records are fetched
> via the RePORTER Projects API v2, stored in `data/derived/nih_reporter_awards.parquet`,
> and wired into the `iterative_enrichment_refresh_job` as the `nih_reporter` source
> partition. Freshness state is tracked in `data/state/enrichment_refresh_state.json`
> alongside the USAspending partition. The `NIHReporterAPIClient` handles pagination
> and rate limiting with the same retry/backoff semantics as `SAMGovAPIClient`."

---

## Introduction

NIH is the second-largest SBIR funder after DoD. NIH RePORTER (Research Portfolio
Online Reporting Tools) exposes a Projects API (v2) with full SBIR/STTR grant records
including project title, abstract, PI, institution, award amount, fiscal year, and
activity code. These supplement the USAspending FABS grant records — RePORTER provides
richer NIH-specific metadata (activity codes R43/R44/R41/R42, study section, FOA
number) that USAspending does not carry.

The iterative enrichment spec (`specs/iterative_api_enrichment/`) identifies NIH
RePORTER as one of four pending source partitions alongside SAM.gov, USAspending
(live), and PatentsView. This spec covers the client, extractor, and freshness wiring
for the NIH partition only.

---

## User Stories

**As a pipeline engineer maintaining enrichment freshness,** I want NIH RePORTER
records fetched and refreshed on the same nightly schedule as USAspending enrichment,
so that NIH grant metadata stays current and the freshness SLA (no source stale for
more than 7 days) is maintained.

**As an NIH SBIR program manager,** I want NIH-specific award metadata (activity code,
study section, FOA number) available alongside the SBIR award records, so that
downstream analytics can segment NIH-funded work by institute, mechanism, and program.

---

## Requirements

### Requirement 1 — NIH RePORTER API client

#### Acceptance Criteria

1. THE `NIHReporterAPIClient` SHALL fetch SBIR/STTR project records from the NIH
   RePORTER Projects API v2 (`https://api.reporter.nih.gov/v2/projects/search`)
   filtering on `activity_codes` R43, R44, R41, R42 (Phase I / Phase II SBIR/STTR).
2. THE client SHALL implement the same retry and exponential backoff semantics as
   `SAMGovAPIClient` (3 retries, 2s/4s/8s backoff) to respect NIH's rate limits.
3. THE client SHALL paginate through results (default page size: 500) and handle
   the `total` vs. `offset` response envelope to avoid missing records near page
   boundaries.
4. THE client SHALL store raw responses to `data/raw/nih_reporter/` before
   transformation, following the same raw-cache pattern as other extractors.

### Requirement 2 — Record normalization and storage

#### Acceptance Criteria

1. THE System SHALL normalize NIH RePORTER records to include: `project_num`,
   `activity_code`, `fy`, `agency_ic_admin`, `org_name`, `pi_names`, `project_title`,
   `abstract_text`, `award_amount`, `foa_number`, `study_section`.
2. THE System SHALL persist normalized records to
   `data/derived/nih_reporter_awards.parquet` with a `source = "nih_reporter"` tag.
3. WHEN a record already exists (matched on `project_num` + `fy`), THE System SHALL
   overwrite it and update the `last_refreshed_at` timestamp rather than appending
   a duplicate.

### Requirement 3 — Iterative enrichment wiring

#### Acceptance Criteria

1. THE System SHALL register a `nih_reporter` source partition in
   `data/state/enrichment_refresh_state.json`, tracking `last_attempt_at`,
   `last_success_at`, and `staleness_window_days` (default: 7).
2. THE System SHALL be invocable via the targeted-refresh CLI:
   `poetry run refresh_enrichment --source nih_reporter --window <start>:<end>`.
3. WHEN the NIH RePORTER source exceeds its staleness window, THE System SHALL
   emit a Dagster asset check warning consistent with the E3 SLA monitoring
   requirement in `specs/iterative_api_enrichment/`.
