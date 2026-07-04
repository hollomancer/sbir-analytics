# Data Reliability Manifest — Design

## Overview

The manifest is a single JSON file per asset materialization. It is produced by extending `AlertCollector` (`sbir_etl/utils/monitoring/alerts.py`) with two new capabilities — `emit_caveat` and `record_provenance` — and by adding one new serializer (`save_manifest`) that also computes a diff against the previous run's manifest to populate `resolved_caveats`. The pilot instruments `validated_sbir_awards` (`packages/sbir-analytics/sbir_analytics/assets/sbir_ingestion.py:327-422`), which already computes most of the required signal but persists none of it durably.

No new modules are introduced. No new external dependencies. The total new code is estimated at ~120 lines across two files, plus ~15 lines of asset wiring.

## Architecture

### Data flow

```text
Asset execution                                Manifest emission
────────────────                               ─────────────────

extractor.extract() ──► records provenance ─┐
                        (source, hash, ts,   │
                         row_count)          │
                                             ▼
                          AlertCollector.record_provenance(...)
                                             │
                                             │
asset body:                                  │
  observe signals ──► emit_caveat(...) ──────┤
  (subthreshold                              │
   observations,                             │
   qualitative                               │
   known limits)                             │
                                             ▼
                          AlertCollector.save_manifest(path)
                                             │
                                             │  1. Serialize caveats + provenance to JSON
                                             │  2. Read most-recent prior manifest (mtime scan)
                                             │  3. Compute resolved_caveats = prior − current by metric_name
                                             │  4. Write to reports/reliability/<asset>/<run_id>.json
                                             │
                                             ▼
                          Dagster MaterializationMetadata:
                          - caveat_count
                          - resolved_caveat_count
                          - manifest_path
```

Existing `Alert` machinery (severity, thresholds, `save_to_file`) is untouched. The manifest lives in a separate JSON file from the alert log so that a downstream consumer reading the manifest does not need to filter alerts out of the payload.

### Module layout

```text
sbir_etl/utils/monitoring/alerts.py
├── Alert                                    (existing, unchanged)
├── AlertSeverity                            (existing, unchanged)
├── AlertThresholds                          (existing, unchanged)
├── AlertCollector                           (extended)
│   ├── emit_caveat(...)                     NEW
│   ├── record_provenance(...)               NEW
│   ├── save_manifest(...)                   NEW
│   └── (all existing methods unchanged)
├── Caveat                                   NEW dataclass
└── ProvenanceEntry                          NEW dataclass

packages/sbir-analytics/sbir_analytics/assets/sbir_ingestion.py
└── validated_sbir_awards                    (extended: ~15 lines added)

reports/reliability/
└── validated_sbir_awards/
    ├── <run_id>.json                        (manifest per run)
    └── <run_id>.json                        (manifest per run)
```

## Components

### 1. `Caveat` and `ProvenanceEntry` dataclasses

Both live in `sbir_etl/utils/monitoring/alerts.py` alongside `Alert`. They mirror `Alert`'s pattern: frozen dataclass, `to_dict()` method for JSON serialization.

```python
@dataclass(frozen=True)
class Caveat:
    """Subthreshold reliability observation. Disclosure, not failure."""

    timestamp: datetime
    dimension: Literal["accuracy", "completeness", "consistency", "validity"]
    metric_name: str          # stable key for cross-run diffing
    observed_value: Any       # float, int, or string for qualitative caveats
    expected_value: Any       # threshold, target, or expected-shape description
    description: str          # one-sentence human-readable statement
    impact: str               # one-sentence downstream-effect statement
    asset_name: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ProvenanceEntry:
    """Per-input-source record. One entry per source the asset consumed."""

    source_id: str            # stable identifier, e.g., "sbir_gov_bulk_download"
    location: str             # URL or absolute path
    retrieved_at: datetime    # UTC
    sha256: str | None        # None permitted; requires hash_omitted_reason
    row_count: int
    extractor_module: str     # dotted Python path, e.g., "sbir_etl.extractors.sbir_duckdb"
    hash_omitted_reason: str | None = None

    def to_dict(self) -> dict[str, Any]: ...
```

The `dimension` field on `Caveat` is a `Literal`, not an enum, to keep the vocabulary flat and inline with Requirement 1.2. A `TypedDict` was considered and rejected — dataclasses match the existing `Alert` shape and keep serialization symmetric.

### 2. `AlertCollector.emit_caveat`

```python
def emit_caveat(
    self,
    dimension: Literal["accuracy", "completeness", "consistency", "validity"],
    metric_name: str,
    observed_value: Any,
    expected_value: Any,
    description: str,
    impact: str,
) -> Caveat:
    """Emit a subthreshold reliability disclosure.

    Does NOT append to self.alerts and does NOT change run outcome.
    Caveats are persisted only via save_manifest().
    """
    if dimension not in ("accuracy", "completeness", "consistency", "validity"):
        raise ValueError(f"Invalid dimension: {dimension!r}")

    caveat = Caveat(
        timestamp=datetime.now(UTC),
        dimension=dimension,
        metric_name=metric_name,
        observed_value=observed_value,
        expected_value=expected_value,
        description=description,
        impact=impact,
        asset_name=self.asset_name,
        run_id=self.run_id,
    )
    self.caveats.append(caveat)
    return caveat
```

`self.caveats: list[Caveat]` is initialized as an empty list in `__init__`.

**Routing existing `check_*` subthreshold observations.** The current `check_*` methods have a single-threshold shape: observation exceeds threshold → emit Alert; otherwise return None. Only `check_memory_pressure` has a genuine two-band structure (warn vs critical); the others do not have a natural subthreshold band today. The pilot does NOT introduce caveat thresholds inside `check_*` methods. Instead, the asset code emits caveats directly by inspecting `self.alerts` at the end of the run and calling `emit_caveat` for any `WARNING`-severity alert that does not already fail a gate. This keeps `check_*` behavior unchanged and localizes the "alert vs caveat" policy decision to the asset.

If a future asset needs a genuine two-threshold `check_*` variant, it is added as a new method (e.g., `check_match_rate_with_caveat`), not by modifying existing methods.

### 3. `AlertCollector.record_provenance`

```python
def record_provenance(
    self,
    source_id: str,
    location: str,
    row_count: int,
    extractor_module: str,
    sha256: str | None = None,
    hash_omitted_reason: str | None = None,
    retrieved_at: datetime | None = None,
) -> ProvenanceEntry:
    """Record one input source. Called by extractors or by the asset body
    after an extractor completes."""
    if sha256 is None and not hash_omitted_reason:
        raise ValueError("sha256=None requires hash_omitted_reason")

    entry = ProvenanceEntry(
        source_id=source_id,
        location=location,
        retrieved_at=retrieved_at or datetime.now(UTC),
        sha256=sha256,
        row_count=row_count,
        extractor_module=extractor_module,
        hash_omitted_reason=hash_omitted_reason,
    )
    self.provenance.append(entry)
    return entry
```

**Where the call happens.** Per Requirement 2.3, extractors know their source metadata. For the pilot, however, the extractor (`SbirDuckDBExtractor`) does not currently take an `AlertCollector`, and threading one through is out of proportion for a single asset. The pilot calls `record_provenance` from the asset body immediately after `extractor.import_csv()` / `extract_all()`, populating from the `import_metadata` dict the extractor already returns (which contains file path, size, timestamps, row count). SHA-256 computation on the input CSV is added as a single new line using `hashlib.file_digest` on the CSV path.

Extending `SbirDuckDBExtractor` to accept an `AlertCollector` and self-report provenance is deferred until a second asset onboards; the shape of that extension will be informed by the pilot.

### 4. `AlertCollector.save_manifest`

```python
def save_manifest(self, manifest_path: Path) -> Path:
    """Persist manifest JSON. Computes resolved_caveats by diffing against
    the most-recent prior manifest in the same directory."""

    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    prior_caveats = self._read_prior_caveats(manifest_path.parent, manifest_path)
    current_metric_names = {c.metric_name for c in self.caveats}
    resolved = [
        c for c in prior_caveats
        if c["metric_name"] not in current_metric_names
    ]

    manifest = {
        "asset_name": self.asset_name,
        "run_id": self.run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "framework_reference": "GAO-20-283G",
        "caveats": [c.to_dict() for c in self.caveats],
        "resolved_caveats": resolved,
        "provenance": [p.to_dict() for p in self.provenance],
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    logger.info(f"Reliability manifest saved to {manifest_path}")
    return manifest_path

def _read_prior_caveats(
    self, directory: Path, exclude: Path
) -> list[dict[str, Any]]:
    """Return caveats from the most recent manifest in `directory`, excluding
    the file at `exclude`. Empty list if none exists."""
    if not directory.exists():
        return []
    candidates = sorted(
        (p for p in directory.glob("*.json") if p != exclude),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return []
    with open(candidates[0]) as f:
        prior = json.load(f)
    return prior.get("caveats", [])
```

**Notes:**
- `resolved_caveats` are represented by their prior manifest's dict form, unchanged. That gives the reader the previous observed value verbatim without needing to construct a `Caveat` object during diffing.
- Diff granularity is `metric_name`. A caveat "resolves" when a caveat with the same `metric_name` was present last run but is absent this run — no need to compare observed values. If a caveat's observation changes but the caveat is still emitted (say, from 62% to 71% with a 75% expected), it stays in `caveats` with the new observed value; it does not appear in `resolved_caveats`.
- The mtime-scan approach is intentionally simple. A `latest.json` symlink was considered but adds a filesystem-side effect that can desync from actual file mtimes. If the mtime scan becomes a hotspot at scale, revisit.

### 5. Wiring `validated_sbir_awards` (the pilot)

Concrete edits to `packages/sbir-analytics/sbir_analytics/assets/sbir_ingestion.py:327-422`:

```python
def validated_sbir_awards(
    context: AssetExecutionContext, raw_sbir_awards: pd.DataFrame
) -> Output[pd.DataFrame]:
    config = get_config()
    pass_rate_threshold = config.data_quality.sbir_awards.pass_rate_threshold

    # NEW: reliability collector
    collector = AlertCollector(
        asset_name="validated_sbir_awards",
        run_id=context.run_id,
        config=config,
    )

    # NEW: record provenance for the upstream source
    #   raw_sbir_awards is already stamped with data_source_url and ingested_at.
    #   Pull one representative row's stamps as the source metadata.
    if len(raw_sbir_awards) > 0:
        collector.record_provenance(
            source_id="sbir_gov_bulk_download",
            location=str(raw_sbir_awards["data_source_url"].iloc[0]),
            retrieved_at=raw_sbir_awards["ingested_at"].iloc[0],
            row_count=len(raw_sbir_awards),
            extractor_module="sbir_etl.extractors.sbir_duckdb",
            sha256=_compute_source_sha256(raw_sbir_awards, context),  # helper; may return None
            hash_omitted_reason=(
                "raw asset dataframe is post-DuckDB-import, not source-bytes-hashable"
                if _compute_source_sha256(raw_sbir_awards, context) is None
                else None
            ),
        )

    # (existing filter + validation code unchanged)
    filtered_df, filter_audit = _apply_quality_filters(raw_sbir_awards, context)
    quality_report = validate_sbir_awards(df=filtered_df, ...)
    validated_df = filtered_df[~filtered_df.index.isin(failing_indices)].copy()

    # NEW: emit caveats for subthreshold observations
    _emit_validation_caveats(collector, quality_report, filter_audit, len(raw_sbir_awards))

    # (existing metadata dict unchanged)
    metadata: dict[str, Any] = { ... existing ... }

    # NEW: persist manifest + attach metadata
    manifest_path = Path("reports/reliability/validated_sbir_awards") / f"{context.run_id}.json"
    collector.save_manifest(manifest_path)
    metadata["caveat_count"] = len(collector.caveats)
    metadata["resolved_caveat_count"] = _count_resolved(collector, manifest_path)
    metadata["manifest_path"] = str(manifest_path)

    return Output(value=validated_df, metadata=metadata)
```

`_emit_validation_caveats` is a new module-local helper (~20 lines) that inspects the existing `quality_report` and `filter_audit` and calls `emit_caveat` for the specific cases listed below.

## What signals become caveats in the pilot

The pilot converts already-computed but currently-not-persisted signals into caveats. No new detection logic is introduced.

| Source signal | Dimension | Caveat threshold | Impact statement |
|---|---|---|---|
| `quality_report.pass_rate` in [pass_rate_threshold, 0.99] | validity | worse than 99% | Records dropped from downstream analyses may bias cohort counts |
| `filter_audit["dropped_duplicates"] > 0` | consistency | any dupes present | Duplicate detection removed rows; check upstream for repeat submissions |
| `filter_audit["coerced_fields"] > 0` | validity | any coercions | Field values silently coerced to nulls (until input-validation-hardening lands) |
| Row-count reduction from raw → validated exceeds 5% | completeness | > 5% | Downstream cohorts under-count relative to raw source |
| `quality_report` reports any `WARNING`-severity issues (e.g., date-consistency violations per `sbir_etl/validators/sbir_awards.py`) | validity | any present | Records with impossible date orderings retained; time-series joins may be affected |

Each becomes one line in `_emit_validation_caveats`. Every caveat's `impact` is a plain-English statement of downstream effect — this is the load-bearing field per Requirement 1.3.

Static, qualitative caveats — for example, "UEI is absent on ~40% of pre-2015 rows by design (firm-level bifurcation, per `specs/firm-identity-resolution/`)" — are declared as an inline dict at the top of `_emit_validation_caveats` and always emitted regardless of run-specific numbers. This gives the manifest a persistent floor of known limitations that consumers can rely on.

## Manifest JSON shape (worked example)

For a run where the pass rate is 97.2% (below the 99% caveat threshold, above the gate) and 12,483 rows were coerced during filtering:

```json
{
  "asset_name": "validated_sbir_awards",
  "run_id": "0b4a5c7d-...",
  "generated_at": "2026-07-02T15:32:04Z",
  "framework_reference": "GAO-20-283G",
  "caveats": [
    {
      "timestamp": "2026-07-02T15:32:04Z",
      "dimension": "validity",
      "metric_name": "sbir_awards_pass_rate",
      "observed_value": 0.972,
      "expected_value": 0.99,
      "description": "Validation pass rate 97.2% below 99% expected floor.",
      "impact": "Approximately 2.8% of raw records dropped from validated output; downstream cohort counts under-report by that magnitude.",
      "asset_name": "validated_sbir_awards",
      "run_id": "0b4a5c7d-..."
    },
    {
      "timestamp": "2026-07-02T15:32:04Z",
      "dimension": "validity",
      "metric_name": "sbir_awards_coerced_field_count",
      "observed_value": 12483,
      "expected_value": 0,
      "description": "12,483 field values silently coerced to null during pre-validation cleanup.",
      "impact": "Field-level completeness reported downstream may include hidden parse failures until input-validation-hardening lands.",
      "asset_name": "validated_sbir_awards",
      "run_id": "0b4a5c7d-..."
    },
    {
      "timestamp": "2026-07-02T15:32:04Z",
      "dimension": "completeness",
      "metric_name": "uei_missing_pre_2015_bifurcation",
      "observed_value": "~40.9% of multi-award firms missing UEI on every award (2000-2020 window)",
      "expected_value": "field present on all records",
      "description": "Known firm-level bifurcation: UEI absence is a firm property, not per-record noise.",
      "impact": "Longitudinal joins keyed on UEI alone under-count firm-level activity; use firm_id (per specs/firm-identity-resolution/) where available.",
      "asset_name": "validated_sbir_awards",
      "run_id": "0b4a5c7d-..."
    }
  ],
  "resolved_caveats": [],
  "provenance": [
    {
      "source_id": "sbir_gov_bulk_download",
      "location": "s3://sbir-analytics-raw/sbir/award_data.csv",
      "retrieved_at": "2026-07-02T14:58:12Z",
      "sha256": "b8c9...",
      "row_count": 540123,
      "extractor_module": "sbir_etl.extractors.sbir_duckdb",
      "hash_omitted_reason": null
    }
  ]
}
```

The static qualitative caveat (`uei_missing_pre_2015_bifurcation`) is included on every manifest as a persistent known limitation. Numeric caveats appear only when their thresholds trigger. Provenance is always populated.

## Testing strategy

- **Unit — `Caveat` / `ProvenanceEntry` construction and serialization:** frozen-dataclass invariants; `to_dict` round-trips; `dimension` validation raises on invalid values.
- **Unit — `emit_caveat`:** appends to `self.caveats` without touching `self.alerts`; invalid dimension raises; returned `Caveat` is identical to the appended one.
- **Unit — `record_provenance`:** appends to `self.provenance`; `sha256=None` without `hash_omitted_reason` raises; `retrieved_at` defaults to now-UTC when omitted.
- **Unit — `save_manifest`:** writes valid JSON to the expected path; parent directories are created; `resolved_caveats` diff correctly identifies metric_names present in prior manifest but absent in current; empty prior directory produces empty `resolved_caveats`; a run identical to the prior produces empty `resolved_caveats` (no self-resolution).
- **Integration — pilot asset:** materialize `validated_sbir_awards` against a fixture with known coercion counts; assert manifest is written to the expected path; assert `MaterializationMetadata` includes `caveat_count`, `resolved_caveat_count`, `manifest_path`.
- **Integration — cross-run diff:** run the pilot twice with different fixtures; assert caveats present in run 1 but absent in run 2 appear in run 2's `resolved_caveats`.

No CI gates are added by this spec. The manifest is disclosure, not enforcement (Requirement 1.5).

## Open questions

1. **Static qualitative caveats — declared where?** The design places them inline in `_emit_validation_caveats`. An alternative is a per-asset YAML file (e.g., `packages/sbir-analytics/sbir_analytics/assets/validated_sbir_awards.reliability.yaml`) so that adding a known limitation does not require a Python edit. YAML costs one new config-loading path; inline dict costs zero. Recommendation: inline for the pilot; revisit if the second asset finds itself duplicating declarations.

2. **SHA-256 of the upstream source.** The pilot's raw dataframe is post-DuckDB-import; hashing the DataFrame is not the same as hashing the source bytes. Computing sha256 on the CSV file itself (before/during import) is a one-line addition in the extractor but requires threading either an `AlertCollector` or a returned hash through `SbirDuckDBExtractor.import_csv()`. Recommendation: for the pilot, hash the raw CSV path if it is a local file, and set `hash_omitted_reason: "streaming s3 source, per-byte hash not computed in-pipeline"` for S3 sources. Revisit when a second extractor onboards.

3. **`resolved_caveats` payload — full prior object or slimmed?** The current design carries the prior manifest's full caveat dict (including its impact statement and description). A slimmer form (just `metric_name`, `observed_value`, `resolved_at`) is smaller but loses the context that made the caveat legible. Recommendation: keep the full prior form; the manifest is not size-constrained.

4. **Manifest retention.** Manifests accumulate one file per run per asset. No pruning is proposed. If retention becomes an issue, a simple mtime-based `keep_last_n` policy can be added to `save_manifest`. Recommendation: defer.

5. **Static qualitative caveat for `input-validation-hardening` gap.** Until that spec lands, the manifest includes the "field values silently coerced" caveat as a persistent disclosure. Once landed, that caveat becomes conditional on `field_parse_status`. The transition is a one-line change in `_emit_validation_caveats`. Recommendation: proceed with the static caveat now; convert to conditional when input-validation-hardening merges.
