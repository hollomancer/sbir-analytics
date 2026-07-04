# Data Reliability Manifest — Requirements

## Introduction

Several signals about the reliability of pipeline outputs are computed today and then discarded. `AlertCollector` (`sbir_etl/utils/monitoring/alerts.py`) checks thresholds and returns `None` when observations sit *below* a warning threshold — those subthreshold observations are the ones a downstream consumer most needs to see, because they represent "the pipeline is working, but here is exactly where it falls short." Validators log `WARNING`-level date-consistency issues that pass through unchanged. Extractors know the source URL, retrieval timestamp, and row count of every input they consume, but attach none of that to the resulting asset materialization.

This spec adds a **Reliability Manifest** — a small, per-asset-materialization JSON artifact that captures (a) the subthreshold observations currently dropped and (b) the provenance of each input the asset consumed. The artifact is a **disclosure surface**, not a gate. Signals that fail an existing quality gate continue to fail it. This spec only makes visible what today is invisible.

### Why now, and why this shape

GAO-20-283G (*Assessing Data Reliability*) is the framework federal auditors use to decide whether external data is fit to support an audit finding. It is an assessment methodology, not an implementation library. This spec does **not** attempt to implement the full framework — no tiered fitness verdict, no four-dimension sub-object taxonomy, no vocabulary alignment in the schema. Those extensions have no consumer today. What the framework *does* motivate, correctly, is investing in a **durable, machine-readable record of known limitations** so that downstream consumers (analysts, reviewers, future auditors) can form their own reliability judgment from an artifact rather than log excavation. That record is the caveat stream and provenance ledger in this spec. Framework vocabulary can be layered on later if a specific reviewer surfaces.

A previous, much larger draft attempted the full framework implementation; it is archived at `specs/archive/superseded/data-reliability-manifest/` with the rationale for the cut.

## Glossary

- **Reliability Manifest** — JSON artifact emitted once per Dagster asset materialization at `reports/reliability/<asset_name>/<run_id>.json`. Two sections: `caveats` and `provenance`.
- **Caveat** — Structured, machine-readable disclosure of a subthreshold-but-observed reliability issue. Emitted where a signal is worse than a `caveat_threshold` but better (or unrelated to) the existing gate-failure threshold. Does not fail the run.
- **Provenance entry** — Per-input record capturing source location, retrieval timestamp, content hash, and row count, so that any output can be traced back to the exact source snapshot it was derived from.

## Requirements

### Requirement 1 — Caveat stream: subthreshold observations as artifact, not failure

**User Story:** As a downstream consumer, I want subthreshold reliability signals — signals that today are computed and then discarded because they don't cross a gate threshold — persisted as machine-readable caveats on the asset manifest, so that known limitations of the output are transparently disclosed rather than absorbed silently.

#### Acceptance Criteria

1. THE `AlertCollector` in `sbir_etl/utils/monitoring/alerts.py` SHALL be extended with an `emit_caveat(dimension, metric_name, observed_value, expected_value, description, impact)` method. The method SHALL append a structured caveat to a new `self.caveats` list on the collector.
2. THE `dimension` argument SHALL be a single string drawn from `{"accuracy", "completeness", "consistency", "validity"}` — a flat vocabulary tag on each caveat, not a sub-object structure. Any other value SHALL raise on emit.
3. THE `impact` argument SHALL be a one-sentence human-readable description of what downstream analyses the caveat may affect. This is the load-bearing field for reader legibility and is required, not optional.
4. Existing `check_*` methods on `AlertCollector` that currently return `None` for subthreshold observations SHALL be updated to route those observations through `emit_caveat` before returning. The public return contract of the `check_*` methods SHALL NOT change; only the side effect on `self.caveats` is added.
5. Emitting a caveat SHALL NOT change the run outcome. Caveats are informational disclosures. Existing gate-failure paths (`AlertSeverity.FAILURE` alerts) are unchanged.
6. WHERE a caveat with the same `metric_name` was present on the previous run's manifest and is not emitted on the current run (metric now within expected range), THE current manifest SHALL record it under a `resolved_caveats` array with the previous observed value, so improvements are as visible as regressions.

### Requirement 2 — Provenance ledger

**User Story:** As an analyst tracing a suspicious output row back to its origin, I want a per-input-source record of exactly which source snapshot the asset consumed, so I can independently verify the derivation without needing pipeline internals or log excavation.

#### Acceptance Criteria

1. THE manifest SHALL include a `provenance` array with one entry per input source consumed by the asset. Each entry SHALL record: `source_id` (stable string), `location` (URL or absolute path), `retrieved_at` (ISO 8601 UTC), `sha256`, `row_count`, and `extractor_module` (dotted Python path of the extractor that consumed it).
2. WHERE computing a `sha256` on the raw source bytes is impractical (streaming APIs, cursor-paginated results), THE entry SHALL record `sha256: null` and a `hash_omitted_reason` string. All other fields remain required.
3. THE provenance ledger SHALL be produced by extractors, not by the asset — extractors already know their source metadata. A thin helper in `sbir_etl/utils/monitoring/` SHALL provide the append-to-manifest surface the extractors call.
4. THE asset SHALL forward the collected provenance entries into its manifest at materialization time. Assets that transform data from another asset (rather than extracting from an external source) SHALL propagate the upstream asset's provenance entries verbatim rather than re-declaring them.

### Requirement 3 — Pilot on `validated_sbir_awards`

**User Story:** As a reviewer of this spec, I want a bounded initial rollout with no framework overhead, so that I can evaluate the pattern on a single working example before endorsing wider adoption.

#### Acceptance Criteria

1. THE initial implementation SHALL instrument exactly one asset end-to-end: `validated_sbir_awards`. All Requirements 1 and 2 SHALL be satisfied on this asset before any additional asset is onboarded.
2. THE asset materialization SHALL attach the following Dagster `MaterializationMetadata` keys, in addition to whatever the asset already attaches:
   - `caveat_count` (int) — length of the `caveats` array
   - `resolved_caveat_count` (int) — length of the `resolved_caveats` array
   - `manifest_path` (str) — filesystem path to the persisted JSON manifest
3. THE persisted manifest SHALL be written to `reports/reliability/validated_sbir_awards/<run_id>.json` using the existing `Alert.to_dict()`-style JSON emission pattern. No new Markdown renderer, no new dashboard tab, no schema versioning file are required by this spec.
4. Extending the pattern to any additional asset SHALL be a self-contained PR that (a) constructs an `AlertCollector` in the asset, (b) routes the asset's existing subthreshold checks through `emit_caveat`, and (c) attaches the same three metadata keys. No changes to this spec, `AlertCollector`, or the manifest shape SHALL be required per additional asset.

## Non-goals

- **Tiered fitness verdicts** (`sufficient` / `sufficient_with_caveats` / `undetermined` / `insufficient`). No downstream code can branch on a verdict field; adding one is documentation cosplaying as data. See the archived draft for the extended version if a specific reviewer surfaces demand.
- **Four-dimension sub-object taxonomy** in the manifest. The `dimension` field on each caveat is the vocabulary hook; a nested `dimensions.accuracy.dimension_status: pass|caveat|undetermined` structure was cut as a naming layer with no consumer.
- **Transformation ledger with `reversibility` flags**. `sbir_etl/utils/fiscal_audit_trail.py` covers row-count reconciliation where it matters. Per-step reversibility classification had no consumer.
- **GAO-20-283G vocabulary alignment in the JSON schema.** Referenced in the intro as motivation; not embedded in the schema. Layer on if a specific external reviewer materializes.
- **JSON Schema check-in, worked example doc, contributor guide.** All follow-ups if wider adoption warrants them; not blocking on this spec.
- **HTML dashboard tab for reliability manifests.** `sbir_etl/quality/dashboard.py` can be extended in a future PR if operators ask for it.
- **Replacing or modifying existing quality gates.** Gates that fail today continue to fail today.
- **Cross-asset lineage / propagation semantics.** Dagster already tracks asset lineage; this spec describes a single asset's reliability record.

## Reference: existing infrastructure

- `sbir_etl/utils/monitoring/alerts.py` — `Alert`, `AlertSeverity`, `AlertCollector`, `AlertThresholds`. Requirement 1 extends `AlertCollector` with `emit_caveat`; the JSON emission pattern for the manifest reuses `Alert.to_dict()`'s style. **This is where most of the code lives.**
- `sbir_etl/validators/sbir_awards.py` — Existing validators that emit `WARNING`-level date-consistency signals. Feeds the caveat stream directly.
- `sbir_etl/utils/fiscal_audit_trail.py` — Existing audit-trail scaffolding. Referenced but not extended.
- `reports/quality/`, `reports/validation/` — Existing per-run report directories. `reports/reliability/` is added as a sibling.
- Dagster `MaterializationMetadata` — Already used across `packages/sbir-analytics/sbir_analytics/assets/`. Requirement 3 attaches to existing materialization events.

## Dependencies

- **`specs/input-validation-hardening/`** — Once landed, `field_parse_status` provides a source of subthreshold signals for the completeness dimension. Not a hard blocker: this spec can ship on the caveats that already exist today (validator WARNINGs, `AlertCollector.check_*` subthreshold observations).
- **`specs/firm-identity-resolution/`** — Provides identifier-resolution-rate signals that would populate consistency-dimension caveats when the pilot extends to `resolved_sbir_awards`. Out of scope for the pilot in Requirement 3, which targets only `validated_sbir_awards`.
