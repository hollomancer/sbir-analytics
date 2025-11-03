# Add Iterative API Enrichment Refresh Loop

## Why

- The current enrichment stage performs a heavy, mostly one-off merge after SBIR bulk ingestion, so company, award, and patent metadata start to drift as soon as external systems publish corrections or new records.
- The external sources we already rely on (SBIR.gov awards API, USAspending v2, SAM.gov entity data, NIH RePORTER, PatentsView, plus the other APIs called out across docs/config) publish updated snapshots daily to monthly; without an iterative refresh we miss compliance actions, debarments, UEI/DUNS changes, new transitions, and patent grants that happen after the initial load.
- Downstream CET classification, transition detection, and commercialization analytics need fresh enrichment signals to remain trustworthy; manually kicking off another full enrichment run takes hours and wastes API quotas instead of incrementally refreshing only what changed.

## What Changes

- **Iterative enrichment scheduler**
  - Add a Dagster job (`iterative_enrichment_refresh_job`) plus sensor that activates once bulk enrichment assets have succeeded and then runs on a rolling schedule (nightly by default).
  - Partition work by API/source and record cohort (e.g., UEI batches for SAM.gov, award years for USAspending) so each run respects rate limits and can be retried independently.
  - Persist checkpoints (`last_attempt_at`, `last_success_at`, cursor token) so interrupted refreshes resume without re-enriching the same slice.
- **Per-source refresh policies**
  - Define freshness SLAs for every external API we reference: SBIR.gov (weekly), USAspending (daily), SAM.gov (weekly), NIH RePORTER (weekly), PatentsView (monthly), and any other API defined under `config.enrichment.*`.
  - Store target cadence, window size, and max parallel requests in config so operators can tune per environment.
- **Connector + delta upgrades**
  - Build/lightweight clients for SBIR.gov, NIH RePORTER, and PatentsView (SAM.gov + USAspending clients already sketched) with caching of ETags/last-modified to avoid redundant calls.
  - Extend enrichment outputs with normalized source payload hashes so we can skip writes when nothing changed and emit `enrichment_events` records whenever a field flips.
- **Freshness telemetry + remediation**
  - Materialize a DuckDB/Parquet table (and Neo4j nodes) that tracks per-record, per-source freshness plus the SLA delta so we can surface “stale” cohorts in the Dagster UI and CLI.
  - Wire metrics into the existing pipeline metrics framework so we can alert when any source slips below 90% fresh coverage.
- **Operator tooling & docs**
  - Provide `poetry run refresh_enrichment --source sam_gov --window 2023-10-01:2023-10-07` for ad-hoc backfills.
  - Document API credentials, throttling, retry expectations, and the iterative workflow in `docs/enrichment/iterative-refresh.md`.

### Additional External API Targets

- **OpenCorporates REST API**: Company registries, officers, and beneficial ownership data (~200M entities). Useful for validating SBIR company status, corporate events, and officer history. Supports incremental queries via `updated_at` filters and company search endpoints.
- **SEC EDGAR / Company Facts API**: Provides filing metadata, SIC, and financial metrics for public SBIR alumni; change detection via filing accession numbers. Helps flag commercialization milestones and revenue growth.
- **DLA CAGE / Business Identification Search (BIS)**: Delivers CAGE codes, facility locations, and defense-specific compliance data; complements SAM.gov for manufacturing footprint and vendor eligibility checks.
- **SAM Exclusions API**: Separate endpoint focusing on excluded parties/debarments so compliance alerts surface sooner than weekly bulk refreshes.
- **ORCID + OpenAlex APIs**: Allow enrichment of Principal Investigator identities with publication histories, affiliations, and persistent IDs, tightening researcher-level insights.
- **OpenFEC / Campaign Finance API**: Optional source to flag political contributions associated with SBIR leadership teams for governance/compliance analytics.
- **Other Search APIs**: Reserve slots in config for commercial enrichment providers (e.g., Clearbit, People Data Labs) so environments with licenses can plug them in via the same iterative refresh harness.

## Impact

### Affected Specs

- **data-enrichment**: Add requirements covering iterative refresh cadences, per-source TTL tracking, and source-payload diffing.
- **pipeline-orchestration**: Add requirements for the Dagster job/sensor, resumable checkpoints, and rate-limit aware partitioning.

### Affected Code

- `src/enrichers/`: Add API-specific clients (`sbir_gov_client.py`, `nih_reporter_client.py`, `patentsview_client.py`) plus shared iterative orchestrator.
- `src/assets/iterative_enrichment.py`: New Dagster assets/job wiring iterative refresh into the main graph.
- `src/models/enrichment.py`: Extend models with freshness metadata, payload hashes, and per-source run bookkeeping.
- `config/base.yaml` + `config/*.yaml`: New `enrichment_refresh` section for cadences, concurrency, and SLA overrides per environment.
- `scripts/refresh_enrichment.py`: CLI entry point for manual refreshes and troubleshooting.
- `docs/enrichment/iterative-refresh.md`: Operator guide for credentials, scheduling, and recovery.

### Data Volume & Performance Considerations

- Expect ~70K active SBIR companies and 200K awards needing refresh coverage; each source has different release sizes (USAspending daily mods ~50K, SAM.gov UEI updates ~5K/day, NIH RePORTER weekly updates ~1K projects, PatentsView weekly patents ~5K records).
- The scheduler must cap concurrent requests to stay under published quotas (SAM.gov 60/minute per API key, USAspending 120/minute, NIH 25/minute, PatentsView 10/minute) while still closing freshness gaps within 24h.
- Persisting source payload hashes avoids reloading unchanged data and keeps nightly API volume under 250K calls across all sources.

### Dependencies

- Add **httpx** for async API clients and connection pooling.
- Add **tenacity** (or reuse existing backoff helpers if introduced elsewhere) for exponential backoff and jittered retries.
