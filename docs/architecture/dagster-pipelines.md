# Dagster Pipelines, Schedules & Sensors

Operator reference for the Dagster orchestration: what jobs exist, what each
materializes, their schedules, and their sensors. Names below are the real
`name=` values (which sometimes differ from the Python variable) and are
code-verified against `packages/sbir-analytics/sbir_analytics/`.

## Code locations & launching

- **Primary code location:** `sbir_analytics.definitions` — declared in
  `workspace.yaml`. This is what `dagster dev` loads by default.
- **`sbir_analytics.definitions_ml`** is an alias. It re-exports the primary
  `defs` so that existing `-m sbir_analytics.definitions_ml` commands keep
  working. The separate heavy code location is retired; neither workspace file
  loaded it.

The primary location is built by
`sbir_analytics.definitions_factory.build_definitions` and honors
`DAGSTER_LOAD_HEAVY_ASSETS`.

```bash
# Launch the Dagster UI (dev) — primary location
make dev                       # = uv run dagster dev -m sbir_analytics.definitions
# UI at http://localhost:3000 under Docker/server profiles

# Run a heavy job by hand on a suitably provisioned host
uv run dagster job execute -m sbir_analytics.definitions -j fiscal_returns_mvp_job
```

### Heavy-asset gating

`DAGSTER_LOAD_HEAVY_ASSETS` (default `"true"`) controls whether memory-hungry
modules load in the primary location. When it is `false`, the four heavy jobs —
`cet_full_pipeline_job`, `fiscal_returns_*`, `modernbert_job`, and
`uspto_ai_extraction_job` — and their assets are skipped. `definitions_ml`
follows the same toggle, so run heavy jobs with the variable unset or `true`.
Intentional profile exclusions occur before import.
The discovery layer propagates unexpected asset and job import failures. A
missing sensors package remains optional, but import failures from an existing
sensor module propagate. Job modules fail the code location when their assets
cannot import; the repository does not substitute empty jobs.

## Jobs

### Core (always loaded)

| Job (`name`) | Selection | Purpose |
|---|---|---|
| `core_refresh_job` | all currently-loaded non-heavy assets | Weekly refresh of core (non-heavy) assets |
| `cet_drift_job` | `["ml","validated_cet_drift_detection"]` | CET drift detection (only created if that ML asset is loaded) |
| `sbir_weekly_refresh_job` | raw→validated→enriched SBIR | Weekly refresh subset; uses `in_process_executor` to fit 7 GB CI runners |
| `uspto_validation_job` | `raw`/`validated_uspto_assignments` | Lightweight USPTO validation (CI) |
| `sec_edgar_pipeline_job` | validated awards → SEC EDGAR enrichment | Opt-in; enable with `SBIR_ETL__ENRICHMENT_REFRESH__SEC_EDGAR__ENABLED=true` |
| `usaspending_iterative_enrichment_job` | `usaspending_freshness_ledger`, `stale_usaspending_awards` | Identify & refresh stale USASpending awards (kicked by `usaspending_pipeline_after_download`) |
| `phase_transition_latency_job` | Phase II/III pairs + survival | Phase-transition latency analysis |
| `transition_mvp_job` / `transition_full_job` / `transition_analytics_job` | vendor resolution → scoring → evidence (→ detections/analytics) | Transition detection at MVP / full / analytics-only scope |

### Heavy (loaded only when `DAGSTER_LOAD_HEAVY_ASSETS=true`)

| Job (`name`) | Selection | Notes |
|---|---|---|
| `cet_full_pipeline_job` | CET classifications, profiles, analytics, and validation | Ships run config for governed tabular outputs |
| `fiscal_returns_mvp_job` | 9 fiscal keys (NAICS→BEA, inflation, economic/tax) | Exploratory Python/BEA model; memory requirement is not yet measured |
| `fiscal_returns_full_job` | asset groups `fiscal_data_prep`, `economic_modeling`, `tax_calculation`, `sensitivity_analysis` | Full fiscal run incl. sensitivity sweep |
| `modernbert_job` | ModernBERT award/patent embeddings + similarity | Requires ML extras |
| `uspto_ai_extraction_job` | USPTO AI extract + dedup + human sample | — |

## Schedules

Cron strings are env-overridable; defaults below are verified. Dagster's default
`default_status` is **STOPPED** unless noted.

### Primary location (`definitions.py`)

| Schedule | Job | Cron (default) | Default status |
|---|---|---|---|
| `weekly_core_refresh` | `core_refresh_job` | `0 3 * * 0` (Sun 03:00 UTC) | STOPPED |

Cron overrides use `SBIR_ETL__DAGSTER__SCHEDULES__<JOB>` env vars (for example,
`..._WEEKLY_CORE_REFRESH_JOB`).

No schedule runs a heavy job. `cet_full_pipeline_job`, `cet_drift_job`, and
`fiscal_returns_mvp_job` are run by hand.

## Sensors

The download-chaining sensors start each pipeline after its download job
succeeds. See
[Pipeline chaining](../deployment/self-hosted-server.md#pipeline-chaining) for the
sensor table and toggles.

## Registration

The shared definitions factory registers all assets and checks, the jobs for the
selected profile, its schedules, and its sensors. `definitions.py` is the
stable, thin Dagster entry point; `definitions_ml.py` re-exports its `defs`. See
`packages/sbir-analytics/sbir_analytics/definitions_factory.py` and
`assets/jobs/job_registry.py`.

Eleven heavy asset keys currently belong to no named job: the four USPTO AI
evidence keys and seven `ml/` CET training/analysis keys. They remain selectable individually in the Dagster UI or CLI, but cannot
be launched as one of the registered jobs. No schedule covers heavy assets.
