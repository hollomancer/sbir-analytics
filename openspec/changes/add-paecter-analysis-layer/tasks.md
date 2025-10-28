## 0. Prepare and Validate Change
- [ ] 0.1 Read proposal and design for this change (PaECTER analysis layer).
- [ ] 0.2 Create/verify change directory and spec deltas are present and formatted (ADDED requirements, scenarios).
- [ ] 0.3 Run OpenSpec strict validation for this change ID and fix issues.
- [ ] 0.4 Confirm no conflicting active changes (naming, overlapping assets).

## 1. Configuration (YAML + ENV)
- [ ] 1.1 Add `paecter.*` configuration block to config/base.yaml with defaults:
  - [ ] provider: `huggingface` (default), `local` (explicit fallback only)
  - [ ] endpoint.type: `inference_api` (default), `endpoint` (later option)
  - [ ] endpoint.url: "" (required only when `endpoint.type=endpoint`)
  - [ ] auth.token_env: `HF_API_TOKEN`
  - [ ] remote.batch.size: 64
  - [ ] remote.max_qps: 10
  - [ ] remote.timeout_seconds: 60
  - [ ] remote.retry.max_retries: 5
  - [ ] remote.retry.backoff_seconds: base 0.5, jittered, cap 30
  - [ ] max_length: 512
  - [ ] cache.enable: false
  - [ ] text.award_fields: ["solicitation_title", "abstract"]
  - [ ] text.patent_fields: ["title", "abstract"]
  - [ ] similarity.top_k: 10
  - [ ] similarity.min_score: 0.60
  - [ ] join.limit_per_award: 50
  - [ ] index.backend: `bruteforce` (default) | `faiss` (optional)
  - [ ] index.path: artifacts/indexes/paecter/awards_patents.faiss
  - [ ] enable_neo4j_edges: false
  - [ ] neo4j.prune_previous: false
  - [ ] neo4j.mark_current: false
  - [ ] neo4j.max_concurrency: 1
  - [ ] neo4j.txn_batch_size: 5000
  - [ ] neo4j.dry_run: false
  - [ ] validation.coverage.patents: 0.98
  - [ ] validation.coverage.awards: 0.95
  - [ ] validation.similarity.neg_mean_max: 0.30
  - [ ] validation.similarity.pos_mean_min: 0.55
  - [ ] validation.cohesion.margin_min: 0.05
  - [ ] validation.cohesion.min_share: 0.70
  - [ ] validation.cohesion.min_size: 50
- [ ] 1.2 Implement ENV override mapping for all keys (prefix: SBIR_ETL__PAECTER__...).
- [ ] 1.3 (If using Pydantic config) Add a `PaecterConfig` model with defaults and validation.
- [ ] 1.4 Document all keys and env overrides in README/docs.

## 2. Remote Inference Client (Hugging Face Inference API default)
- [ ] 2.1 Implement a thin client wrapper for remote embedding calls:
  - [ ] Accept a list of texts; split into batches of `remote.batch.size`.
  - [ ] Inject auth from `auth.token_env` (Bearer token).
  - [ ] Enforce client-side QPS throttle (`remote.max_qps`).
  - [ ] Use `remote.timeout_seconds` per request.
  - [ ] Retries on 429/5xx/timeouts with jittered exponential backoff (base 0.5s, cap 30s) up to `remote.retry.max_retries`.
  - [ ] Redact payloads on error; do not log raw text.
  - [ ] Return embeddings as list[list[float]]; propagate actionable error messages.
- [ ] 2.2 Add optional local dedupe cache (disabled by default):
  - [ ] Key: SHA256(text); Value: embedding array
  - [ ] Configurable toggle `cache.enable`; pluggable store path (can be extended later).
- [ ] 2.3 Record and return metadata per run (for artifacts): provider, endpoint.type, endpoint host (not full URL), model_id, model_revision (if available), client versions.

## 3. Text Construction Utilities
- [ ] 3.1 Implement text builder for awards:
  - [ ] Concatenate configured `text.award_fields` in order with separator " — ".
  - [ ] Skip missing fields; trim whitespace; preserve casing.
- [ ] 3.2 Implement text builder for patents:
  - [ ] Concatenate configured `text.patent_fields` with separator " — "; abstract optional.
- [ ] 3.3 Enforce token truncation via remote model tokenizer by specifying `max_length` if supported; otherwise ensure safe client behavior.

## 4. Patent Embeddings Asset (remote)
- [ ] 4.1 Create Dagster asset `paecter_embeddings_patents`.
- [ ] 4.2 Inputs: transformed patents (title, abstract if present).
- [ ] 4.3 Use text builder to produce inputs; route to remote inference client in batches.
- [ ] 4.4 Output Parquet `data/processed/paecter_embeddings_patents.parquet` with columns:
  - [ ] patent_id
  - [ ] text_source
  - [ ] embedding (list[float])
  - [ ] model_name = "mpi-inno-comp/paecter"
  - [ ] model_revision (if exposed by provider)
  - [ ] provider (e.g., huggingface)
  - [ ] computed_at (UTC ISO timestamp)
- [ ] 4.5 Emit checks JSON adjacent to output:
  - [ ] { ok, coverage, threshold, total, embedded, reason?, config_snapshot }
- [ ] 4.6 Attach Dagster metadata: counts, coverage, latency stats, retries, throughput (texts/sec).

## 5. Award Embeddings Asset (remote)
- [ ] 5.1 Create Dagster asset `paecter_embeddings_awards`.
- [ ] 5.2 Inputs: enriched awards (`solicitation_title`, `abstract`).
- [ ] 5.3 Use remote inference client with batched requests, throttling, retries.
- [ ] 5.4 Output Parquet `data/processed/paecter_embeddings_awards.parquet` with columns:
  - [ ] award_id
  - [ ] text_source
  - [ ] embedding (list[float])
  - [ ] model_name
  - [ ] model_revision
  - [ ] provider
  - [ ] computed_at
- [ ] 5.5 Emit checks JSON analogous to patents; attach Dagster metadata.

## 6. Award ↔ Patent Similarity Asset
- [ ] 6.1 Create Dagster asset `paecter_award_patent_similarity`.
- [ ] 6.2 Load embeddings parquet for awards and patents; L2-normalize vectors.
- [ ] 6.3 Compute cosine similarity:
  - [ ] Default backend: brute-force matrix multiplication in blocks.
  - [ ] Optional backend: FAISS (IndexFlatIP or suitable index) when configured.
- [ ] 6.4 For each award:
  - [ ] Keep top_k (config) with cosine_sim ≥ min_score (config).
  - [ ] Enforce limit_per_award cap.
- [ ] 6.5 Output Parquet `data/processed/paecter_award_patent_similarity.parquet` with columns:
  - [ ] award_id, patent_id, cosine_sim, rank, threshold_pass (bool), backend, computed_at
- [ ] 6.6 Emit checks JSON (ok, total_pairs, kept_pairs, backend, top_k, min_score, stats: mean/p50/p90, reason?); attach Dagster metadata.

## 7. Classifier Cohesion Metrics Asset
- [ ] 7.1 Create Dagster asset `paecter_classifier_cohesion_metrics`.
- [ ] 7.2 Inputs: CET labels + embeddings (awards and/or patents).
- [ ] 7.3 For each class:
  - [ ] Compute intra_mean (within-class), inter_mean (vs negatives or global), margin = intra_mean − inter_mean.
  - [ ] Exclude classes with size < `validation.cohesion.min_size`.
- [ ] 7.4 Summarize:
  - [ ] Compute share of classes with margin ≥ `validation.cohesion.margin_min`.
  - [ ] List worst classes with counts and margins.
- [ ] 7.5 Output JSON `data/processed/paecter_classifier_cohesion.json`; attach Dagster metadata.
- [ ] 7.6 Gate: fail with ERROR if share < `validation.cohesion.min_share`.

## 8. Asset Checks and Validation Gates
- [ ] 8.1 Add asset checks for embedding coverage:
  - [ ] Patents coverage ≥ 0.98
  - [ ] Awards coverage ≥ 0.95
- [ ] 8.2 Add similarity quality checks:
  - [ ] Negative-pair mean ≤ `validation.similarity.neg_mean_max` (default 0.30) → ERROR on violation.
  - [ ] Heuristic positive-pair mean ≥ `validation.similarity.pos_mean_min` (default 0.55) → WARNING by default (configurable to ERROR).
- [ ] 8.3 Add cohesion gate (from §7.6).
- [ ] 8.4 On any ERROR gate failure, block downstream similarity consumption and optional Neo4j loader.

## 9. Optional Neo4j Loader
- [ ] 9.1 Create Dagster asset `neo4j_award_patent_similarity` (skipped unless `enable_neo4j_edges=true`).
- [ ] 9.2 Ingest only `threshold_pass=true` rows; MERGE (Award)-[:SIMILAR_TO {method:"paecter"}]->(Patent).
- [ ] 9.3 Update properties: score, rank, computed_at, model, revision, last_updated; no vectors in Neo4j.
- [ ] 9.4 Pruning/mark_current behavior per config (mutually exclusive; prune takes precedence).
- [ ] 9.5 Validate constraints on Award(award_id) and Patent(patent_id) or auto-create if configured; skip missing nodes.
- [ ] 9.6 Fail if skip_rate > 1% (configurable); batch writes with retries; attach loader metrics and checks JSON.

## 10. Performance, Baselines, and Alerts
- [ ] 10.1 Instrument assets with telemetry:
  - [ ] Embeddings (remote): latency distribution, retries, throughput (texts/sec).
  - [ ] Similarity: throughput, memory footprint (where applicable).
- [ ] 10.2 Persist baselines:
  - [ ] `reports/benchmarks/paecter_embeddings.json`
  - [ ] `reports/benchmarks/paecter_validation_baseline.json`
- [ ] 10.3 Compare and alert on drift/regressions:
  - [ ] Write alerts to `reports/alerts/paecter_*.json`.
- [ ] 10.4 CI mode: sample to ≤ 2k items to target < 5 min runtime (toggleable via env).

## 11. Tests
- [ ] 11.1 Unit: text builder (field selection, separator, trimming).
- [ ] 11.2 Unit: remote client batching, QPS throttle, retry backoff, timeout behavior (stub responses).
- [ ] 11.3 Unit: cache behavior (if enabled) with SHA256 keys; duplicate avoidance.
- [ ] 11.4 Unit: cosine similarity and top‑k selection; FAISS fallback path (if included).
- [ ] 11.5 Unit: cohesion metric calculations; small-class exclusion; margin/share logic.
- [ ] 11.6 Unit: checks JSON writers; threshold evaluation paths.
- [ ] 11.7 Integration: end-to-end small fixture (patents + awards) exercising remote client stubs to produce embeddings, similarity, metrics.
- [ ] 11.8 Integration (optional): Neo4j loader with ephemeral DB; verify MERGE upsert, prune/mark_current semantics.
- [ ] 11.9 Performance smoke: ensure telemetry captured; CI sampling respected; no excessive runtime.

## 12. Documentation
- [ ] 12.1 Add `docs/data/paecter.md`:
  - [ ] Model overview; licensing; usage patterns; limits; calibration approach.
  - [ ] Remote inference specifics; rate limits; retries; data handling.
- [ ] 12.2 Update `docs/deployment/containerization.md`:
  - [ ] HF Inference API setup; required env var for token.
  - [ ] Later option: Inference Endpoint creation and URL wiring.
- [ ] 12.3 Update `docs/schemas/` if enabling Neo4j SIMILAR_TO edges.
- [ ] 12.4 Update README with new assets and how to enable/disable.

## 13. Security & Governance
- [ ] 13.1 Ensure token via environment variable; no secrets in code or logs.
- [ ] 13.2 Redact all payloads from logs and errors; log only hashed IDs or counts.
- [ ] 13.3 Record model_id and model_revision in outputs for reproducibility.
- [ ] 13.4 Confirm policy approval for sending text to Hugging Face (already approved).

## 14. Inference Endpoint (Later Option)
- [ ] 14.1 Extend client to support `endpoint.type=endpoint` with `endpoint.url`.
- [ ] 14.2 Implement a readiness check that verifies endpoint health and (if available) model revision.
- [ ] 14.3 Add configuration for endpoint-specific batch sizes/QPS based on capacity.
- [ ] 14.4 Add tests for endpoint mode (stubbed responses).
- [ ] 14.5 Document when to prefer Endpoints (throughput, stability, cost predictability).

## 15. Orchestration & CI
- [ ] 15.1 Register new Dagster assets; integrate with lazy import mapping.
- [ ] 15.2 Ensure materialization plan includes embeddings → similarity → metrics; Neo4j loader stays disabled in CI.
- [ ] 15.3 Add CI secrets management guideline for HF token if needed (avoid real network calls in tests; prefer stubs).

## 16. Rollout & Safety
- [ ] 16.1 Default `provider=huggingface`, `endpoint.type=inference_api`, `enable_neo4j_edges=false`.
- [ ] 16.2 Deploy to dev; validate coverage/quality gates; set baselines.
- [ ] 16.3 Deploy to staging; monitor latency, retries, and costs; tune batch/QPS.
- [ ] 16.4 Deploy to prod; enable Neo4j loader selectively; monitor alerts.
- [ ] 16.5 Document rollback plan (disable assets; prune edges if needed).

## 17. Acceptance Criteria
- [ ] 17.1 Patents embedding coverage ≥ 0.98; awards embedding coverage ≥ 0.95.
- [ ] 17.2 Similarity checks: negatives mean ≤ 0.30 (ERROR otherwise); heuristic positives mean ≥ 0.55 (WARN default).
- [ ] 17.3 Cohesion: share of classes meeting margin ≥ 0.05 is ≥ 0.70 with size ≥ 50.
- [ ] 17.4 Similarity artifact schema valid; integrity checks pass; per-award caps honored.
- [ ] 17.5 Performance telemetry present; baselines persisted; alerts written on significant drift.
- [ ] 17.6 All new assets and checks pass in CI (with stubs); OpenSpec validate passes; coverage targets met (≥80% across new code).