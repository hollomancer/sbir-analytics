# Dagster Pipelines, Schedules & Sensors

Operator reference for the Dagster orchestration: what jobs exist, what each
materializes, their schedules, and the one sensor. Names below are the real
`name=` values (which sometimes differ from the Python variable) and are
code-verified against `packages/sbir-analytics/sbir_analytics/`.

## Code locations & launching

- **Primary code location:** `sbir_analytics.definitions` — declared in
  `workspace.yaml`. This is what `dagster dev` loads by default.
- **Secondary (heavy ML/fiscal):** `sbir_analytics.definitions_ml` — *not* in
  `workspace.yaml`; invoked directly (it forces `DAGSTER_LOAD_HEAVY_ASSETS=true`).

```bash
# Launch the Dagster UI (dev) — primary location
make dev                       # = uv run dagster dev -m sbir_analytics.definitions
# UI at http://localhost:3000 under Docker/server profiles

# Run a heavy job from the secondary location (e.g. on a GitHub Actions runner)
uv run dagster job execute -m sbir_analytics.definitions_ml -j fiscal_returns_mvp_job
```

### Heavy-asset gating

`DAGSTER_LOAD_HEAVY_ASSETS` (default `"true"`) controls whether memory-hungry
modules load. When it is `false` (the Mac-mini/server profile), the four heavy
jobs — `cet_full_pipeline_job`, `fiscal_returns_*`, `modernbert_job`,
`uspto_ai_extraction_job` — and their assets are skipped in the primary location;
run them from `definitions_ml` instead. If an upstream asset module fails to
import, its job is replaced by an empty **placeholder** job (name suffixed
`_placeholder`) so the code location still loads.

## Jobs

### Core (always loaded)

| Job (`name`) | Selection | Purpose |
|---|---|---|
| `sbir_analytics_job` (var `etl_job`) | `AssetSelection.all()` | Complete SBIR ETL pipeline |
| `core_refresh_job` | all currently-loaded non-heavy assets | Weekly refresh of core (non-heavy) assets |
| `cet_drift_job` | `["ml","validated_cet_drift_detection"]` | CET drift detection (only created if that ML asset is loaded) |
| `sbir_weekly_refresh_job` | raw→validated→enriched SBIR + `neo4j_sbir_awards` | Weekly refresh subset; uses `in_process_executor` to fit 7 GB CI runners |
| `uspto_validation_job` | `raw`/`validated_uspto_assignments` | Lightweight USPTO validation (CI) |
| `sec_edgar_pipeline_job` | validated awards → SEC EDGAR enrichment → Neo4j | Opt-in; enable with `SBIR_ETL__ENRICHMENT_REFRESH__SEC_EDGAR__ENABLED=true` |
| `usaspending_iterative_enrichment_job` | `usaspending_freshness_ledger`, `stale_usaspending_awards` | Identify & refresh stale USASpending awards (kicked by the sensor below) |
| `phase_transition_latency_job` | Phase II/III pairs + survival | Phase-transition latency analysis |
| `transition_mvp_job` / `transition_full_job` / `transition_analytics_job` | vendor resolution → scoring → evidence (→ detections/analytics → Neo4j) | Transition detection at MVP / full / analytics-only scope |

### Heavy (loaded only when `DAGSTER_LOAD_HEAVY_ASSETS=true`)

| Job (`name`) | Selection | Notes |
|---|---|---|
| `cet_full_pipeline_job` | 8 CET keys (classifications, profiles, Neo4j CET nodes/edges) | Ships run config (parquet/json paths, `batch_size: 1000`, create constraints/indexes) |
| `fiscal_returns_mvp_job` | 9 fiscal keys (NAICS→BEA, inflation, economic/tax) | R/StateIO; needs 8 GB+ RAM (AWS Batch) |
| `fiscal_returns_full_job` | asset groups `fiscal_data_prep`, `economic_modeling`, `tax_calculation`, `sensitivity_analysis` | Full fiscal run incl. sensitivity sweep |
| `modernbert_job` | ModernBERT award/patent embeddings + similarity | Requires ML extras |
| `uspto_ai_extraction_job` | USPTO AI extract + dedup + human sample | — |

## Schedules

Cron strings are env-overridable; defaults below are verified. Dagster's default
`default_status` is **STOPPED** unless noted.

### Primary location (`definitions.py`)

| Schedule | Job | Cron (default) | Default status |
|---|---|---|---|
| `daily_sbir_analytics` | `sbir_analytics_job` | `0 2 * * *` (02:00 UTC daily) | **RUNNING** (disable via `SBIR_ETL__DAGSTER__SCHEDULES__DAILY_ALL_ASSETS_ENABLED=false`) |
| `weekly_core_refresh` | `core_refresh_job` | `0 3 * * 0` (Sun 03:00 UTC) | STOPPED |
| `daily_cet_full_pipeline` | `cet_full_pipeline_job` | `0 2 * * *` | STOPPED (only if the job is loaded) |
| `daily_cet_drift_detection` | `cet_drift_job` | `0 6 * * *` | STOPPED (only if the drift asset is loaded) |

Cron overrides use `SBIR_ETL__DAGSTER__SCHEDULES__<JOB>` env vars (e.g.
`..._ETL_JOB`, `..._WEEKLY_CORE_REFRESH_JOB`).

### Secondary location (`definitions_ml.py`)

| Schedule | Job | Cron (default) | Default status |
|---|---|---|---|
| `daily_cet_full_pipeline` | `cet_full_pipeline_job` | `0 3 * * *` | STOPPED |
| `weekly_fiscal_returns` | `fiscal_returns_mvp_job` | `0 4 * * 1` (Mon 04:00 UTC) | STOPPED |

## Sensors

| Sensor | Monitors | Fires | Job kicked | Default status |
|---|---|---|---|---|
| `usaspending_refresh_sensor` | materialization of `enriched_sbir_awards`, `usaspending_freshness_ledger`, `stale_usaspending_awards` | a `RunRequest` when bulk enrichment has materialized **and** stale awards are detected (skips if enrichment not yet run or `stale_count == 0`; triggers once to initialize on first run) | `usaspending_iterative_enrichment_job` | STOPPED |

## Registration

`Definitions(...)` in `definitions.py` registers: all assets/checks
(auto-loaded), `job_definitions` (the two core jobs + `cet_drift_job` if present
+ all auto-discovered public jobs under `assets/jobs/`), `schedules`, and the
sensor. See `packages/sbir-analytics/sbir_analytics/definitions.py` and
`assets/jobs/job_registry.py`.
