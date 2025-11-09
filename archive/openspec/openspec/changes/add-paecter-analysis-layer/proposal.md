#Why

We want a robust, explainable, and retrieval-friendly analysis layer that complements our existing CET-based patent and award classifiers. PaECTER provides high-quality patent embeddings that enable semantic search, prior-art style similarity, cohort cohesion checks, and award↔patent cross-linking to improve discovery, validation, and downstream analytics.

We will use Hugging Face’s hosted Inference API by default (no local GPU required) to accelerate adoption. As a later option, we will support Hugging Face Inference Endpoints for dedicated capacity and tighter performance SLOs.

## What Changes

- Add a PaECTER-powered analysis layer that is strictly additive to current classifiers (no breaking behavioral changes):
  - Compute dense embeddings for patents and awards using `mpi-inno-comp/paecter` via Hugging Face Inference API.
  - Produce award↔patent semantic similarity pairs (top-k with thresholds).
  - Assess classifier cohesion/separation using embedding-space metrics (e.g., intra-/inter-class cosine).
  - Emit quality/performance checks with gating aligned to project standards.

- New Dagster assets and outputs:
  - `paecter_embeddings_patents` → `data/processed/paecter_embeddings_patents.parquet`
    - Columns (minimum): `patent_id`, `text_source`, `embedding` (list[float]), `model_name`, `model_revision`, `provider`, `computed_at`
    - `text_source` defaults to patent title; can include abstract (configurable concatenation)
  - `paecter_embeddings_awards` → `data/processed/paecter_embeddings_awards.parquet`
    - Columns (minimum): `award_id`, `text_source`, `embedding`, `model_name`, `model_revision`, `provider`, `computed_at`
    - `text_source` defaults to `solicitation_title` + `abstract` where available
  - `paecter_award_patent_similarity` → `data/processed/paecter_award_patent_similarity.parquet`
    - Columns (minimum): `award_id`, `patent_id`, `cosine_sim`, `rank`, `threshold_pass`, `backend`, `computed_at`
    - Backend is brute-force cosine for small N; FAISS option for larger N (local compute; still additive/optional)
  - `paecter_classifier_cohesion_metrics` → `data/processed/paecter_classifier_cohesion.json`
    - Per-CET class: mean intra-class cosine, inter-class separation, margin (intra − inter), share above thresholds
    - Supports both award and patent CET outputs

- Optional Neo4j loading (additive, off by default):
  - `neo4j_award_patent_similarity` writes relationships:
    - `(Award)-[:SIMILAR_TO {score, method: "paecter", model, revision, computed_at, rank}]->(Patent)`
    - Idempotent MERGE; only thresholded top-k per award; no raw vectors in Neo4j

- Configuration (YAML + env overrides) — Inference API default with later Endpoint option:
  - Provider and endpointing
    - `paecter.provider`: `huggingface` (default) | `local` (explicit fallback only)
    - `paecter.endpoint.type`: `inference_api` (default) | `endpoint` (later option)
    - `paecter.endpoint.url`: required only for `endpoint` mode
    - `paecter.auth.token_env`: default `HF_API_TOKEN`
  - Inference behavior (remote)
    - `paecter.remote.batch.size`: default 64 (payload-size aware)
    - `paecter.remote.max_qps`: default 10 (client throttle)
    - `paecter.remote.timeout_seconds`: default 60
    - `paecter.remote.retry.max_retries`: default 5
    - `paecter.remote.retry.backoff_seconds`: jittered exponential; base 0.5s, cap 30s
    - `paecter.max_length`: default 512 tokens
    - `paecter.cache.enable`: default false (optional local dedupe cache by SHA256(text))
  - Text sources
    - `paecter.text.award_fields`: default `["solicitation_title", "abstract"]`
    - `paecter.text.patent_fields`: default `["title", "abstract"]` (abstract optional)
  - Similarity
    - `paecter.similarity.top_k`: default 10
    - `paecter.similarity.min_score`: default 0.60
    - `paecter.join.limit_per_award`: default 50 (cap retained matches per award)
    - `paecter.index.backend`: `bruteforce` (default if small) | `faiss` (optional for scale)
    - `paecter.index.path`: `artifacts/indexes/paecter/awards_patents.faiss`
  - Neo4j (optional)
    - `paecter.enable_neo4j_edges`: default false
    - `paecter.neo4j.prune_previous`: default false
    - `paecter.neo4j.mark_current`: default false
    - `paecter.neo4j.max_concurrency`: default 1
    - `paecter.neo4j.txn_batch_size`: default 5000
    - `paecter.neo4j.dry_run`: default false
  - Validation and quality gates
    - Coverage thresholds:
      - `paecter.validation.coverage.patents`: default 0.98
      - `paecter.validation.coverage.awards`: default 0.95
    - Similarity distribution bounds:
      - `paecter.validation.similarity.neg_mean_max`: default 0.30
      - `paecter.validation.similarity.pos_mean_min`: default 0.55
    - Cohesion thresholds:
      - `paecter.validation.cohesion.margin_min`: default 0.05
      - `paecter.validation.cohesion.min_share`: default 0.70
      - `paecter.validation.cohesion.min_size`: default 50

- Quality and validation gates (align to project standards):
  - Embedding coverage:
    - Patents: ≥ 0.98 of transformed patents have embeddings
    - Awards: ≥ 0.95 of enriched awards have embeddings
  - Similarity distributions:
    - Negative pairs mean cosine ≤ 0.30 (drift guard)
    - Heuristic positive pairs mean cosine ≥ 0.55 (calibration)
  - Cohesion checks:
    - For classes with size ≥ 50, within-class mean ≥ inter-class mean + 0.05 for ≥ 70% of classes
  - Gate enforcement:
    - All metrics emitted as checks JSON and Dagster asset checks
    - Failures block similarity consumption and optional Neo4j writes

- Performance and monitoring:
  - Remote inference: record throughput (texts/sec), latency distributions, retry counts
  - Baselines: `reports/benchmarks/paecter_embeddings.json` and `reports/benchmarks/paecter_validation_baseline.json`
  - Alerts: `reports/alerts/paecter_*.json` for drift and performance regressions
  - CI mode: sample to ≤ 2k items for < 5 min runtime target

- Dependency approach (optional/extras; additive):
  - For local fallback paths and offline dev only (not default): `sentence-transformers`, `transformers`, `torch`, optionally `faiss-cpu`
  - Runtime degrades gracefully:
    - No FAISS → brute-force cosine
    - Local fallback disabled by default; enable explicitly if needed

- Security/Governance:
  - OK to send text to Hugging Face (confirmed)
  - Use env var for token; never log raw text; redact error payloads
  - Record `model_id` and pinned `revision` in artifacts for reproducibility

## Impact

- Affected specs:
  - `data-enrichment`: ADDED requirements for remote PaECTER embedding generation, semantic similarity, and classifier cohesion analysis
  - `data-validation`: ADDED requirements for embedding coverage gates, similarity distribution drift checks, and cohesion thresholds
  - `data-loading` (optional): ADDED Neo4j similarity edge write requirements (non-breaking, configuration-gated)

- Affected code (high level; additive):
  - New assets: `src/assets/paecter_assets.py`
    - `paecter_embeddings_patents` (remote inference)
    - `paecter_embeddings_awards` (remote inference)
    - `paecter_award_patent_similarity` (brute-force by default; FAISS optional)
    - `paecter_classifier_cohesion_metrics`
    - Optional: `neo4j_award_patent_similarity`
  - Config: `config/base.yaml` additions under `paecter.*` including endpoint and remote inference settings
  - Performance/quality: Reuse `src/utils/performance_*.py`, `src/utils/quality_*.py`
  - Documentation:
    - `docs/data/` for PaECTER usage and evaluation
    - `docs/deployment/containerization.md` for remote inference setup and Endpoint option
    - `docs/schemas/` if Neo4j similarity edges are enabled

- Risk/mitigation:
  - Remote rate limits/latency: client-side throttling (max_qps), retries with backoff, batch tuning
  - Endpoint outages: actionable errors; retries; (later) Endpoint option for dedicated capacity
  - Artifact size from embeddings: Parquet with compression; no vectors in Neo4j
  - Quality drift: negative/positive checks, cohesion gates, baseline comparisons

- Backward compatibility:
  - Fully additive; no changes to current classifier behavior or existing assets
  - Neo4j edges disabled by default; enable per environment via config

- Open decisions (tracked for implementation):
  - Default negative/positive sampling strategies for calibration (e.g., recipient + temporal proximity)
  - FAISS switch threshold based on corpus size (product of awards × patents)
  - Caching defaults (off vs on with size/time limits) and cache location
