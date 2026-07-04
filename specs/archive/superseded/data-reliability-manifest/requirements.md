# Data Reliability Manifest — Requirements

## Introduction

The SBIR ETL pipeline ingests data from a heterogeneous set of federal sources (SBIR.gov bulk downloads, SAM.gov entity extracts, USAspending, SEC EDGAR, USPTO) and produces a graph and analytic outputs used to answer the research questions in `docs/research-questions.md`. Downstream consumers — internal analysts, external reviewers, and eventually publications citing the graph — have no principled way to inspect *why* a given asset's output should be trusted, or where it falls short. Quality signals exist (validators, `AlertCollector`, `sbir_etl/quality/dashboard.py`, per-run reports under `reports/`) but they are scattered, non-uniform across assets, and — critically — many subthreshold signals are logged and then discarded rather than persisted as an audit artifact.

GAO-20-283G, *Assessing Data Reliability*, defines a four-dimension framework (**accuracy, completeness, consistency, validity**) and a tiered conclusion (**sufficiently reliable**, **not sufficiently reliable**, **reliability undetermined**) that GAO auditors apply when deciding whether external data is fit to support an audit finding. The framework is an assessment methodology, not an implementation library. This spec adapts it into a concrete pipeline artifact: a **Reliability Manifest** emitted per Dagster asset materialization that records the evidence an external auditor would need to arrive at the tiered conclusion themselves.

Explicitly out of scope: changing which records the pipeline accepts, replacing existing quality gates, or blocking runs on newly-surfaced signals. The manifest is a **disclosure surface**, not a gate. Signals that already fail a gate continue to fail it; signals that today are logged-and-dropped will instead be persisted as machine-readable caveats on the manifest — visible, auditable, and non-blocking.

### Prior framing

Earlier quality work (`sbir_etl/quality/baseline.py`, `sbir_etl/quality/dashboard.py`, and the `AlertCollector` in `sbir_etl/utils/monitoring/alerts.py`) focused on **regressions against a historical baseline** — did match rates drop, did enrichment slow down. That framing answers "is today worse than yesterday" but not "is today's output fit for the intended use." This spec adds the fitness-for-use lens on top of the existing regression lens; it does not replace it.

## Glossary

- **Reliability Manifest** — Machine-readable JSON artifact emitted once per asset materialization, capturing the four GAO dimensions, the intended use, the fitness verdict, provenance, transformations, and any subthreshold caveats. Persisted to `reports/reliability/<asset_name>/<run_id>.json` and surfaced as Dagster `MaterializationMetadata`.
- **Fitness Verdict** — Enum drawn from GAO's tiered conclusions, adapted: `sufficient`, `sufficient_with_caveats`, `undetermined`, `insufficient`. Assigned per asset per run against the asset's declared intended use.
- **Intended Use Declaration** — Per-asset static declaration of the downstream purposes the asset is fit to serve (e.g., `"phase_transition_detection"`, `"cohort_construction"`, `"exploratory_reporting"`). Different intended uses can have different reliability thresholds against the same underlying data.
- **Reliability Caveat** — Structured, machine-readable disclosure of a subthreshold-but-observed issue. Recorded on the manifest without failing the run. Distinct from an `Alert` in that a caveat does not require a numeric threshold breach — it can describe a *known limitation* (e.g., "UEI recall is 60% on pre-2015 firms; downstream longitudinal joins on this asset will under-count").
- **Provenance Ledger** — Section of the manifest recording each input source: URL or path, retrieval timestamp, content hash (SHA-256), row count, and the extractor identifier that consumed it.
- **Transformation Ledger** — Section of the manifest recording each mutation applied to source data during the asset's execution: canonicalization, imputation (where applied), identifier resolution, filtering. Each entry records rows affected, method identifier, and a reversibility flag.

## Requirements

### Requirement 1 — Reliability Manifest emitted per asset materialization

**User Story:** As an external reviewer, I want a single machine-readable artifact per asset run that records every reliability-relevant fact about that run, so that I can reconstruct the auditor's judgment without needing pipeline internals or ad-hoc log excavation.

#### Acceptance Criteria

1. THE pipeline SHALL emit exactly one Reliability Manifest per Dagster asset materialization for every asset covered by this spec's rollout (see Requirement 7).
2. THE manifest SHALL be persisted as JSON to `reports/reliability/<asset_name>/<run_id>.json` and SHALL be attached to the asset materialization as Dagster `MaterializationMetadata` under the key `reliability_manifest`.
3. THE manifest SHALL be schema-versioned via a top-level `schema_version` field; a JSON Schema definition SHALL be checked in at `specs/data-reliability-manifest/schema.json` (to be produced in the design phase).
4. THE manifest SHALL be self-contained: no reader SHALL need to consult the Dagster run store, the source database, or any external log to understand the reliability claim being made. All numeric evidence SHALL be inline in the manifest.
5. THE manifest SHALL be idempotent: re-running an asset on identical inputs SHALL produce a byte-identical manifest modulo the `run_id`, `run_started_at`, and `run_completed_at` fields.

### Requirement 2 — Intended-use declaration and tiered fitness verdict

**User Story:** As an analyst about to consume an asset, I want a per-run verdict that tells me whether the asset is fit for my intended use, and, if only conditionally fit, exactly which caveats attach, so that I can make an informed decision without reverse-engineering the pipeline.

#### Acceptance Criteria

1. THE manifest SHALL include an `intended_uses` array declaring the downstream purposes the asset is designed to support, drawn from a controlled vocabulary defined in `docs/steering/reliability_intended_uses.md` (to be created in the design phase).
2. THE manifest SHALL include a per-intended-use `fitness_verdict` field taking one of `sufficient`, `sufficient_with_caveats`, `undetermined`, `insufficient`.
3. THE verdict SHALL be derived deterministically from the four-dimension evidence per rules documented in `design.md`; the manifest SHALL include a `verdict_rationale` array of the specific evidence rows that drove the verdict.
4. WHERE the verdict is `sufficient_with_caveats` or `undetermined`, the manifest SHALL enumerate the specific caveats (see Requirement 5) that qualify or block the verdict.
5. THE verdict SHALL NOT block the run: an `insufficient` verdict SHALL emit `AlertSeverity.WARNING` and persist the manifest, but SHALL NOT raise or short-circuit downstream assets unless a separate existing quality gate independently fails.

### Requirement 3 — Four-dimension evidence instrumentation

**User Story:** As an auditor applying GAO-20-283G, I want each of the four reliability dimensions surfaced as inspectable evidence, so that I can independently reach a conclusion about the asset's fitness for a stated purpose.

#### Acceptance Criteria

1. THE manifest SHALL include a top-level `dimensions` object with sub-objects for `accuracy`, `completeness`, `consistency`, and `validity`.
2. THE `accuracy` sub-object SHALL summarize the Provenance Ledger (Requirement 4) — source hashes, retrieval timestamps, and any accuracy signals available (e.g., cross-source agreement rates for identifiers).
3. THE `completeness` sub-object SHALL record per-field `{present, absent, parse_failure}` counts as emitted by `field_parse_status` (per `specs/input-validation-hardening/`), plus row counts at extraction, post-validation, and post-transformation stages.
4. THE `consistency` sub-object SHALL record cross-source join hit rates (e.g., SBIR-to-SAM.gov identifier match %), identifier resolution rates by tier (per `specs/firm-identity-resolution/`), and referential-integrity check results for any foreign-key-style joins the asset performs.
5. THE `validity` sub-object SHALL record schema conformance rate, range-check violations, enumeration conformance rates, and count of records where date-consistency violations were detected (per `specs/input-validation-hardening/` Requirement 3).
6. Each sub-object SHALL include, alongside the raw counts, a `dimension_status` field taking one of `pass`, `caveat`, `undetermined` — where `caveat` means the dimension is populated but a subthreshold issue was recorded (see Requirement 5).

### Requirement 4 — Provenance and transformation ledgers

**User Story:** As an auditor tracing a suspicious output row back to its origin, I want a complete record of every input consumed by the asset run and every transformation applied within it, so that I can independently verify the derivation.

#### Acceptance Criteria

1. THE manifest SHALL include a `provenance_ledger` array with one entry per input source consumed by the asset. Each entry SHALL record: `source_id`, `location` (URL or path), `retrieved_at` (ISO 8601 UTC), `sha256`, `row_count`, and `extractor_module`.
2. THE `sha256` field SHALL be computed on the extractor's byte input where feasible (source file, API response body). For streaming sources where a single hash is impractical, THE ledger SHALL record `sha256: null` with a `hash_omitted_reason` field explaining why.
3. THE manifest SHALL include a `transformation_ledger` array with one entry per row-affecting transformation the asset applied. Each entry SHALL record: `step_id`, `method_module`, `rows_in`, `rows_out`, `rows_affected`, and a `reversibility` flag (`lossless`, `lossy_reversible`, `lossy_irreversible`).
4. Entries with `reversibility: lossy_irreversible` SHALL include a `justification` field explaining why the transformation is applied and what information is lost.
5. THE transformation ledger SHALL include filtering operations (rows dropped due to validation, deduplication) as first-class entries, so that the sum of `rows_in − rows_out` across the ledger equals the difference between extraction row count and final row count.

### Requirement 5 — Subthreshold caveat stream (gaps as artifact, not failure)

**User Story:** As a pipeline maintainer, I want subthreshold reliability signals — signals that today are logged and forgotten because they don't rise to a gate failure — persisted as machine-readable caveats on the manifest, so that known limitations are transparently disclosed to consumers rather than absorbed silently.

#### Acceptance Criteria

1. THE manifest SHALL include a `caveats` array. Each entry SHALL be a structured object with: `caveat_id`, `dimension` (one of the four GAO dimensions), `severity` (mapped from `AlertSeverity`: `INFO`, `WARNING`), `metric_name`, `observed_value`, `expected_value`, `threshold_relation` (`below`, `above`, `outside_range`, `qualitative`), `description` (one-sentence human-readable), and `impact` (one-sentence description of what downstream analyses this may affect).
2. Caveats SHALL be emitted for any signal that meets *either* of the following conditions:
   - A numeric signal is worse than a documented `caveat_threshold` but better than the existing gate-failure threshold (subthreshold-but-notable band).
   - A qualitative known limitation applies (e.g., "SAM.gov historical extract has known coverage gaps 2004–2010"); these SHALL be declared statically per asset in the asset's intended-use declaration and echoed on every manifest.
3. Emitting a caveat SHALL NOT change the run outcome. Caveats are informational disclosures, not failures.
4. THE `AlertCollector` in `sbir_etl/utils/monitoring/alerts.py` SHALL be extended with an `emit_caveat(...)` method that records to the manifest without appending to the alert stream that feeds existing failure paths. Existing `check_*` methods that currently discard subthreshold observations SHALL be updated to route those observations through `emit_caveat` instead.
5. Caveats SHALL be surfaced in the human-readable Markdown summary (Requirement 6) under a `## Known Limitations` section, ordered by dimension then severity.
6. WHERE a caveat's `caveat_id` was present on the previous run's manifest but has resolved on this run (metric now within expected range), THE current manifest SHALL record it under a `resolved_caveats` array with the previous and current values, so that improvements are as visible as regressions.

### Requirement 6 — Dagster surface and human-readable summary

**User Story:** As a Dagster operator, I want the fitness verdict and top caveats visible in the Dagster UI's asset materialization view, and a human-readable Markdown summary saved alongside the JSON, so that I can triage without needing a JSON viewer or write ad-hoc queries.

#### Acceptance Criteria

1. THE asset materialization SHALL attach the following Dagster `MaterializationMetadata` keys in addition to `reliability_manifest`:
   - `fitness_verdict` (string, top-level verdict)
   - `caveat_count` (int)
   - `dimension_status_summary` (string, e.g., `"accuracy: pass, completeness: caveat, consistency: pass, validity: pass"`)
2. THE pipeline SHALL persist a human-readable Markdown summary at `reports/reliability/<asset_name>/<run_id>.md` alongside the JSON manifest. The summary SHALL be renderable via the existing `Alert.to_markdown()` pattern (see `sbir_etl/utils/monitoring/alerts.py:69-98`) extended to whole-manifest rendering.
3. THE Markdown summary SHALL open with the verdict line, list caveats grouped by dimension, and end with the provenance ledger as a table.
4. THE existing `sbir_etl/quality/dashboard.py` HTML dashboard SHALL be extended (in a follow-up PR, not blocked by this spec) to include a per-asset reliability tab that reads the last N manifest JSONs and plots verdict-over-time and caveat-count-over-time.

### Requirement 7 — Rollout: vertical slice first, then documented extension

**User Story:** As a reviewer of this spec, I want to see a bounded initial rollout with an explicit extension path, so that I can approve the pattern without endorsing a big-bang rewrite of every asset.

#### Acceptance Criteria

1. THE initial implementation SHALL instrument exactly two assets end-to-end: `validated_sbir_awards` (the pre-resolution validation checkpoint) and `resolved_sbir_awards` (the post-identity-resolution asset introduced by `specs/firm-identity-resolution/`). All Requirements 1–6 SHALL be satisfied on these two assets before extension.
2. THE implementation SHALL produce a Manifest Contributor Guide at `docs/steering/reliability_manifest_contributor_guide.md` documenting how to add a new asset to the manifest system.
3. Extension to any additional asset SHALL be a one-file PR that adds an intended-use declaration and wires the extended `AlertCollector` — no schema change or framework work required to onboard.
4. THE spec SHALL NOT require or imply retrofitting every existing asset. Assets outside the initial slice remain in the current state (no manifest emitted) until an explicit follow-up PR onboards them.
5. THE first-two-assets rollout SHALL NOT block on `specs/input-validation-hardening/` being fully implemented — where `field_parse_status` is not yet available, THE completeness dimension SHALL populate with a `dimension_status: undetermined` and a caveat describing the missing upstream signal, per Requirement 5's qualitative-limitation clause.

### Requirement 8 — Auditor legibility

**User Story:** As an external reviewer applying GAO-20-283G to this pipeline's outputs, I want the manifest to be legible on its own terms, so that I do not need to learn Dagster, DuckDB, or the internal codebase to form a reliability opinion.

#### Acceptance Criteria

1. THE manifest schema SHALL use vocabulary directly aligned with GAO-20-283G: dimension names (`accuracy`, `completeness`, `consistency`, `validity`) and verdict tiers (`sufficient`, `sufficient_with_caveats`, `undetermined`, `insufficient`) SHALL match the framework's language.
2. THE manifest SHALL reference GAO-20-283G explicitly via a top-level `framework` field (value: `"GAO-20-283G"`) and a `framework_version` field.
3. Every numeric evidence entry SHALL include its unit, its denominator (where a rate), and its computation window (where time-scoped).
4. THE spec SHALL include, in `design.md`, a worked example: a fully-populated manifest for a representative `validated_sbir_awards` run, with commentary tying each field back to the corresponding GAO framework element.

## Non-goals

- **Replacing or modifying existing quality gates.** Gates that fail runs today continue to fail runs; the manifest is orthogonal disclosure.
- **Real-time reliability streaming.** Manifests are per-asset-materialization artifacts, not streaming events.
- **Cross-asset lineage graphs.** Dagster already tracks asset lineage; the manifest describes a single asset's reliability, not the reliability propagation through the DAG. Consumer-side propagation rules are a follow-up spec if warranted.
- **Automatic remediation of caveats.** Caveats disclose known limitations; fixing them is a separate change per limitation.
- **Reliability scoring for external / third-party assets.** Only Dagster-materialized assets in this repo are in scope.
- **A UI review workflow for caveats.** The Dagster UI + Markdown summary are the review surface for this spec; a dedicated caveat review tool is a follow-up if the caveat volume justifies it.

## Reference: existing infrastructure

The following modules already implement most of the machinery this spec requires. The manifest is largely composition and persistence of signals the pipeline already computes but currently discards:

- `sbir_etl/utils/monitoring/alerts.py` — `Alert`, `AlertSeverity`, `AlertCollector`, `AlertThresholds`. Provides the alert model, JSON/Markdown emission, and threshold-driven signal generation. Extend with `emit_caveat(...)` per Requirement 5.
- `sbir_etl/quality/baseline.py`, `sbir_etl/quality/dashboard.py` — Historical baseline comparison and HTML dashboard generation. Reused for the verdict-over-time visualization deferred to Requirement 6, criterion 4.
- `sbir_etl/utils/fiscal_audit_trail.py` — Existing audit-trail scaffolding. Referenced as the model for the transformation ledger's row-count reconciliation semantics.
- `sbir_etl/validators/sbir_awards.py` — Existing validity checks (currently WARNING-level for date-consistency). Directly feeds the validity dimension.
- `reports/quality/`, `reports/validation/` — Existing per-run report directories. `reports/reliability/` is added as a sibling.
- Dagster `MaterializationMetadata` — Already used across `packages/sbir-analytics/sbir_analytics/assets/`. The manifest attaches to existing materialization events; no new event type is introduced.

## Dependencies

- **`specs/input-validation-hardening/`** — `field_parse_status` populates the completeness dimension. The initial rollout can proceed with `dimension_status: undetermined` if input-validation-hardening is not yet merged (Requirement 7, criterion 5), but full completeness reporting requires it.
- **`specs/firm-identity-resolution/`** — Introduces the `resolved_sbir_awards` asset that is the second target of the initial rollout, and produces the identifier resolution rates that populate the consistency dimension.
- Neither dependency is a hard blocker for starting design work on this spec; both are hard blockers for completing the full initial-slice rollout.
