# PaECTER Analysis Layer — Design

## Context

We currently classify SBIR awards and patents into CET areas and attach evidence for explainability. To improve discovery, validation, and analytics, we will add an embedding-driven analysis layer built on PaECTER (Patent Embeddings using Citation-informed TransformERs). This will enable:

- Dense vector embeddings for patents and awards
- Award↔patent semantic similarity (top‑k with thresholds)
- Embedding-space diagnostics for classifier cohesion/separation
- Quality gates, drift detection, and performance telemetry

Provider strategy:

- Default: Hugging Face Inference API (serverless; no local GPU required)
- Later option: Hugging Face Inference Endpoints (dedicated capacity, TEI-backed)
- Local CPU/GPU: non-default, explicit fallback only when required

Reference model: mpi-inno-comp/paecter (Apache-2.0), 1024-d embeddings, optimized for patents.

## Goals / Non-Goals

- Goals:
  - Deterministic, configurable remote embedding generation for patents and awards
  - Top‑k award↔patent semantic similarity with thresholds and per-award caps
  - Embedding-based CET classifier cohesion/separation metrics
  - Coverage/quality gates, distribution drift checks, and performance baselines
  - Optional Neo4j similarity edges (no vector storage in graph)

- Non-Goals:
  - Changing existing CET classifier semantics
  - Storing raw vectors in Neo4j
  - Real-time vector search service (batch-only in this phase)
  - Introducing, deploying, or maintaining a separate vector DB service

## Architecture

- New Dagster assets (additive):
  - paecter_embeddings_patents → data/processed/paecter_embeddings_patents.parquet
  - paecter_embeddings_awards → data/processed/paecter_embeddings_awards.parquet
  - paecter_award_patent_similarity → data/processed/paecter_award_patent_similarity.parquet
  - paecter_classifier_cohesion_metrics → data/processed/paecter_classifier_cohesion.json
  - neo4j_award_patent_similarity (optional; off by default)

- Data Flow:

  1) Transform patents → build text (title [+ abstract]) → remote embeddings
  2) Enriched awards → build text (solicitation_title [+ abstract]) → remote embeddings
  3) Similarity: compute award→patent top‑k cosine (brute-force; FAISS optional later)
  4) Cohesion: compute intra-/inter-class metrics per CET label
  5) Optional: load thresholded similarity edges to Neo4j

- Outputs and Observability:
  - Parquet for embeddings and similarity; JSON for metrics and checks
  - Checks JSON adjacent to primary artifacts for asset gating
  - Performance baselines and alerts under reports/{benchmarks,alerts}/

## Configuration (YAML + environment overrides)

Prefix: paecter.*

- Provider and Endpointing
  - provider: huggingface (default) | local (explicit fallback only)
  - endpoint.type: inference_api (default) | endpoint (later option)
  - endpoint.url: required only when endpoint.type=endpoint
  - auth.token_env: HF_API_TOKEN (default)

- Remote Inference Behavior
  - remote.batch.size: 64 (tune by payload size and rate limits)
  - remote.max_qps: 10 (client-side throttle)
  - remote.timeout_seconds: 60
  - remote.retry.max_retries: 5
  - remote.retry.backoff_seconds: jittered exponential, base 0.5, cap 30
  - max_length: 512 (token truncation)
  - cache.enable: false (local dedupe cache by SHA256(text), optional)

- Text Sources
  - text.award_fields: ["solicitation_title", "abstract"]
  - text.patent_fields: ["title", "abstract"] (abstract optional)

- Similarity
  - similarity.top_k: 10
  - similarity.min_score: 0.60
  - join.limit_per_award: 50
  - index.backend: bruteforce (default) | faiss (optional at scale)
  - index.path: artifacts/indexes/paecter/awards_patents.faiss

- Validation and Quality Gates
  - validation.coverage.patents: 0.98
  - validation.coverage.awards: 0.95
  - validation.similarity.neg_mean_max: 0.30
  - validation.similarity.pos_mean_min: 0.55
  - validation.cohesion.margin_min: 0.05
  - validation.cohesion.min_share: 0.70
  - validation.cohesion.min_size: 50

- Neo4j (optional)
  - enable_neo4j_edges: false
  - neo4j.prune_previous: false
  - neo4j.mark_current: false
  - neo4j.max_concurrency: 1
  - neo4j.txn_batch_size: 5000
  - neo4j.dry_run: false

All keys are overrideable via environment variables (e.g., SBIR_ETL__PAECTER__REMOTE__BATCH__SIZE).

## Key Decisions

1) Default Provider: Inference API

- Why: Quickest path to production without local GPUs; fully managed scaling
- Impact: Client implements batching, throttling, retries; records model_id and revision in outputs

2) Endpoint Option (Later)

- Why: Dedicated capacity, stable performance SLOs; TEI-backed for embeddings
- Impact: Add endpoint.url and ensure request compatibility; same client abstractions

3) Local Fallback (Explicit)

- Why: Allow offline dev or disaster recovery; not default to avoid dependency sprawl
- Impact: Optional installation of transformers/torch; maintain feature parity but accept slower performance

4) Similarity Backend

- Default: Brute-force cosine (normalize vectors, then dot product)
- Optional: FAISS for large-scale search (switch threshold configurable)

5) Graph Storage

- No vectors in Neo4j; only SIMILAR_TO edges with score and metadata
- Keep graph lean and governance simple

## Detailed Design

### Text Construction

- Awards: concatenate configured fields in order (default: solicitation_title, abstract if present) with separator " — "
- Patents: default title; append abstract if present with separator
- Trim whitespace; skip missing fields
- Preserve casing by default
- Truncate to max_length tokens at tokenizer level

### Remote Embedding Inference

- Request batching:
  - Group texts up to remote.batch.size, respecting payload size constraints
  - Client-side throttle to remote.max_qps across batches
- Retries and backoff:
  - Retry on 429/5xx/timeouts up to remote.retry.max_retries
  - Jittered exponential backoff; cap 30s
- Determinism and metadata:
  - Record model_id="mpi-inno-comp/paecter" and pinned revision (if exposed by provider)
  - Record provider, endpoint.type, endpoint.url (only domain), client library versions
- Caching (optional):
  - Local content-addressed cache (SHA256(text) → embedding array) to reduce repeated calls across runs
  - Disabled by default; configurable path and TTL can be added later
- Safety and privacy:
  - Do not log raw text; only counts and hashed identifiers
  - Redact payloads in error logs

Outputs (Parquet):

- patents: patent_id, text_source, embedding (list[float]), model_name, model_revision, provider, computed_at
- awards: award_id, text_source, embedding, model_name, model_revision, provider, computed_at

Checks JSON (adjacent to outputs):

- { ok, coverage, threshold, total, embedded, reason?, config_snapshot }

### Similarity Computation

- Inputs: award and patent embeddings
- Normalization: L2-normalize vectors; cosine_sim = dot(normalized_award, normalized_patent)
- Backend:
  - bruteforce (default): matrix multiplication in blocks
  - faiss (optional): IndexFlatIP (or appropriate index); normalize and search
- Top‑k + threshold:
  - For each award, keep top_k patents with cosine_sim ≥ min_score
  - Enforce join.limit_per_award cap (guards against explosion)
- Outputs (Parquet):
  - award_id, patent_id, cosine_sim, rank, threshold_pass (bool), backend, computed_at
- Checks JSON:
  - { ok, total_pairs, kept_pairs, backend, top_k, min_score, stats: {mean, p50, p90}, reason? }

### Classifier Cohesion Metrics

- Inputs: CET labels + embeddings (awards and/or patents)
- Per-class metrics:
  - intra_mean: mean cosine within class
  - inter_mean: mean cosine vs negatives (sampled or global mean)
  - margin: intra_mean − inter_mean
- Exclude small classes (size < validation.cohesion.min_size)
- Summary:
  - share of classes with margin ≥ validation.cohesion.margin_min
  - list of worst classes with counts and margins
- Output JSON:
  - data/processed/paecter_classifier_cohesion.json (per-class + summary)
- Gate:
  - ERROR if share < validation.cohesion.min_share

### Quality, Calibration, and Drift

- Coverage gates:
  - Patents coverage ≥ 0.98; awards coverage ≥ 0.95 → else ERROR
- Negative-pair bound:
  - Random negatives mean cosine ≤ 0.30 → else ERROR
- Heuristic positive-pair bound:
  - Mean cosine ≥ 0.55 → default WARNING; configurable to ERROR
- Drift:
  - Compare against reports/benchmarks/paecter_validation_baseline.json
  - Flag absolute deltas beyond bounds (neg_mean +0.05, pos_mean −0.05, coverage −0.02)
  - Write alerts to reports/alerts/paecter_drift.json

### Neo4j Optional Loader

- Relationship:
  - (Award)-[:SIMILAR_TO {score, method:"paecter", model, revision, computed_at, rank, current?}]->(Patent)
- Idempotent MERGE by (award_id, patent_id, method="paecter")
- Pruning/mark_current (configurable and mutually exclusive; prune takes precedence)
- Constraints:
  - Validate uniqueness on Award(award_id), Patent(patent_id), or auto-create if configured
- Skips:
  - Skip missing nodes; fail if skip_rate > 1% (configurable)
- Batching:
  - txn_batch_size=5000; limited concurrency; retries with backoff
- Ingest only rows with threshold_pass=true

## Performance and Observability

- Embeddings (remote):
  - Track latency distribution, throughput (texts/sec), retry counts
  - Persist baselines: reports/benchmarks/paecter_embeddings.json
- Similarity:
  - Log backend, throughput, and memory where applicable
- Validation:
  - Persist baseline: reports/benchmarks/paecter_validation_baseline.json
- Alerts:
  - reports/alerts/paecter_*.json for drift and perf regressions
- CI mode:
  - Auto-sample to ≤ 2k items to keep < 5 min runtime (toggleable)

## Security and Compliance

- Data transfer to Hugging Face is acceptable (explicitly confirmed)
- Use environment variable for token; never commit secrets
- Redact payloads in logs/errors; do not log raw text
- Record model_id and revision for reproducibility; include license info in docs

## Risks / Trade-offs

- Remote rate limits and variability:
  - Throttling, batching, retries with backoff; endpoint option for stability
- Outages:
  - Actionable errors, retries; (later) endpoint with higher availability
- Artifact size (embeddings):
  - Parquet with compression; retention policy in docs
- Quality drift:
  - Negative/positive gates, cohesion metrics, baselines, and alerts
- Cost:
  - Client-side QPS caps; batching; consider Endpoints for predictable cost at scale

## Migration Plan

1) Config scaffolding for paecter.* (provider= huggingface; endpoint.type= inference_api)
2) Implement remote embedding assets for patents and awards (Inference API)
3) Add similarity asset (brute-force); add FAISS as optional for scale
4) Implement cohesion metrics and all checks/gates
5) Add performance baselines and alerts
6) Optional Neo4j loader (disabled by default)
7) Documentation (usage, limits, governance, setup)
8) Add tests (unit + integration with stubbed remote responses)

Rollback:

- Disable assets via selection or config; no changes to existing CET behaviors
- Use prune mode in loader to remove similarity edges if needed

## Open Questions

- Positive-pair heuristic: best proxy signals (recipient match + temporal proximity; others?)
- FAISS switch threshold: at what awards×patents size do we flip (default heuristic; make configurable)?
- Caching: default disabled vs enabled with size/time caps; cache location policy
- Endpoint readiness checks: should we verify model revision on startup when using Endpoints?

## References

- Model: mpi-inno-comp/paecter (Apache-2.0)
- Paper: “PaECTER: Patent-level Representation Learning using Citation-informed Transformers” (arXiv:2402.19411)
- Project conventions and validation gates aligned with existing data-enrichment and data-validation specs