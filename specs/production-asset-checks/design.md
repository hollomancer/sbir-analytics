# Production Asset Checks — Design

## Shape

One new module of pure builders, thin `@asset_check` attachments next to the
assets they guard, thresholds in the existing config tree, and a runbook
subsection. Nothing schedules anything: the checks run exactly when their
assets materialize, which is the point.

```
config/base.yaml (data_quality.operational_checks)
        │ get_config()
        ▼
sbir_analytics/asset_checks.py        pure builders: evaluate_freshness,
        │                             evaluate_row_delta, evaluate_completeness
        ▼
@asset_check(..., blocking=True)      thin attachments beside each asset:
  raw_sbir_awards            freshness + row floor
  raw_usaspending_recipients freshness + row floor
  raw_usaspending_transactions freshness + row floor
  raw_sam_gov_entities       freshness + row floor
  enriched_sbir_awards       row delta vs previous + completeness
```

## Builders (pure core)

Signatures shaped for testing without a Dagster instance:

```python
def evaluate_freshness(as_of: datetime | None, *, max_age_days: int, now: datetime) -> CheckOutcome
def evaluate_row_delta(current: int, previous: int | None, *, max_drop_fraction: float, min_rows: int) -> CheckOutcome
def evaluate_completeness(df: pd.DataFrame, *, required: dict[str, float]) -> CheckOutcome
```

`CheckOutcome` is a small frozen dataclass (`passed`, `reason`, `metadata`)
that the attachment layer converts to `AssetCheckResult` with
`AssetCheckSeverity.ERROR`. The severity import reuses the census's
compat shim pattern (`phase_iii_census/assets.py` guards older Dagster with a
try/except fallback class) rather than inventing a second one.

Design decisions:

- **Missing evidence fails.** No as-of metadata → freshness fails with
  `missing freshness metadata`. This is the anti-rot lesson from the test
  audit: a check that silently passes when its input disappears is decoration.
- **Cold start passes once.** `previous=None` → row-delta passes with
  `baseline recorded`, so enabling the checks never wedges the first run.
- **Drop-only in v1.** A row-count surge is suspicious but not damage; the
  drop guard blocks, and a surge guard can be added as config later without
  code changes to callers if the builder takes both bounds from config.

## Previous-count mechanics

The attachment layer reads the prior count from the latest materialization
event's metadata for the same asset key:

```python
event = context.instance.get_latest_materialization_event(asset_key)
previous = event.asset_materialization.metadata.get("row_count") if event else None
```

- The count source of truth is the asset's own `row_count` output metadata —
  the convention already used by `usaspending_database_enrichment.py`.
  Ingestion assets missing it start emitting it (R2.4).
- No sidecar state files: Dagster's event log is the only store, so the check
  is exactly as durable as the deployment's `dagster_home`, which the runbook
  already protects.
- In tests, the builder takes `previous` as a plain argument; only one thin
  integration test exercises the instance-reading path via
  `dagster.materialize(...)` with an ephemeral instance, materializing twice
  to prove the second run sees the first run's count.

## Attachment sites

| Asset | Checks | Notes |
|---|---|---|
| `raw_sbir_awards` (`sbir_ingestion.py`) | freshness, row floor | as-of from the downloaded bulk file's recorded date |
| `raw_usaspending_recipients` / `raw_usaspending_transactions` (`usaspending_ingestion.py`) | freshness, row floor | share one config block |
| `raw_sam_gov_entities` (`sam_gov_ingestion.py`) | freshness, row floor | |
| `enriched_sbir_awards` (`sbir_usaspending_enrichment.py`) | row delta, completeness | completeness reuses `data_quality.completeness` |

Checks live in the same module as their asset (the fiscal pattern), importing
builders from `sbir_analytics.asset_checks`. USPTO ingestion is deliberately
second-tranche: its download path just gained `_guard_html_shell` protections
and its cadence is irregular, so thresholds need operator input first.

Where the as-of timestamp comes from, per source: the download ops already
return path/size/date dicts; ingestion assets record the source file's
modification or embedded as-of date into their output metadata
(`source_as_of`), and the freshness check reads its own asset's metadata from
the current materialization — no cross-asset reads needed.

## Configuration

```yaml
data_quality:
  operational_checks:
    max_row_drop_fraction: 0.2
    sources:
      sbir_awards:        { max_age_days: 14, min_rows: 100000 }
      usaspending:        { max_age_days: 45, min_rows: 10000 }
      sam_gov:            { max_age_days: 45, min_rows: 10000 }
```

Loose on purpose (R3.2): these catch collapse — an empty download, a stale
mirror, a filter bug that drops half the corpus — not gradual drift.
Tightening is a config diff reviewed like any other.

## Failure and bypass behavior

A blocking failure halts downstream assets in the run and fails the run; the
operator sees which check, with observed/threshold/previous in the metadata.
The only sanctioned bypass is a committed threshold change (config PR), which
keeps every override reviewable. No environment-variable kill switch in v1 —
an escape hatch that skips data-integrity checks on the live host is exactly
the kind of quiet hole this spec exists to close.

## Testing strategy

- Builder unit tests (pure, fixture frames): each rule's pass/fail boundary,
  missing-metadata failure, cold-start pass. Fast lane.
- One `materialize()` integration test per check kind with an ephemeral
  instance proving: failing check blocks downstream asset; passing check
  does not; second materialization reads first run's row count. These are
  hermetic (fixtures, no services) and land in `tests/unit/assets/` or
  `tests/functional/` per size.
- `Definitions.validate_loadable` already runs on every PR and will catch
  attachment mistakes (duplicate check names, bad asset keys) for free.

## Alternatives considered

- **Dagster sensors polling source files** — rejected: a sensor is another
  always-on process with its own failure modes; checks ride runs that already
  happen and cost nothing between runs.
- **Direct AlertCollector integration in v1** — deferred: run failure is
  already surfaced by the deployment's existing operational visibility;
  wiring a second channel before the checks have produced a single real
  failure is speculative plumbing.
- **Warn-only introduction period** — rejected: the fiscal checks and the
  census set the precedent that a check either blocks or it is noise; loose
  thresholds are the introduction period.
- **A generic check framework over all assets** — rejected as scope creep;
  five assets, three rules, one module. The tier doc's admission-control
  logic applies to checks too: each one added must earn its blocking status.
