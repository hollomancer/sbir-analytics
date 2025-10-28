## ADDED Requirements

### Requirement: PaECTER Patent Embeddings
The system SHALL compute and persist dense embeddings for transformed patent records using the PaECTER model.

#### Scenario: Compute patent embeddings with configurable text source
- WHEN transformed patent records are available
- THEN the system SHALL build the input text from configured fields (default: title; optionally include abstract)
- AND the text fields SHALL be concatenated with a separator (e.g., " — ") and whitespace trimmed
- AND inputs SHALL be truncated to the configured token limit (default: 512)

#### Scenario: Provider and remote inference configuration
- WHEN the embedding asset initializes
- THEN the system SHALL support provider selection with Hugging Face Inference API as the default (provider=huggingface, endpoint.type=inference_api)
- AND the system SHALL support configuration for `remote.batch.size`, `remote.max_qps`, `remote.timeout_seconds`, and retry policy (jittered exponential backoff)
- AND the system SHALL source authentication via an environment variable (e.g., HF_API_TOKEN) without logging raw secrets or text payloads

#### Scenario: Persist patent embeddings with reproducibility metadata
- WHEN embeddings are computed
- THEN the system SHALL persist a parquet artifact at data/processed/paecter_embeddings_patents.parquet
- AND each row SHALL include at minimum: patent_id, text_source, embedding (list[float]), model_name (e.g., "mpi-inno-comp/paecter"), model_revision (if exposed), provider, computed_at (UTC)

#### Scenario: Coverage metric emission
- WHEN the embedding run completes
- THEN the system SHALL emit coverage metrics (embedded/eligible) to Dagster asset metadata
- AND the system SHALL write a checks JSON adjacent to the artifact containing: ok, coverage, threshold (for reference), total, embedded, reason (if failed), and a snapshot of effective configuration

---

### Requirement: PaECTER Award Embeddings
The system SHALL compute and persist dense embeddings for enriched SBIR awards using the PaECTER model.

#### Scenario: Compute award embeddings with configurable text source
- WHEN enriched awards are available
- THEN the system SHALL build input text from configured fields (default: solicitation_title + abstract when available)
- AND the text fields SHALL be concatenated with a separator (e.g., " — ") and whitespace trimmed
- AND inputs SHALL be truncated to the configured token limit (default: 512)

#### Scenario: Remote inference behavior and safety
- WHEN using the Hugging Face Inference API
- THEN the system SHALL batch requests up to the configured remote.batch.size and throttle to remote.max_qps
- AND the system SHALL implement retries on 429/5xx/timeouts up to remote.retry.max_retries with jittered exponential backoff
- AND the system SHALL never log raw award text; errors SHALL redact payloads

#### Scenario: Persist award embeddings with reproducibility metadata
- WHEN embeddings are computed
- THEN the system SHALL persist a parquet artifact at data/processed/paecter_embeddings_awards.parquet
- AND each row SHALL include at minimum: award_id, text_source, embedding (list[float]), model_name, model_revision (if exposed), provider, computed_at (UTC)

#### Scenario: Coverage metric emission
- WHEN the embedding run completes
- THEN the system SHALL emit coverage metrics (embedded/eligible) to Dagster asset metadata
- AND the system SHALL write a checks JSON adjacent to the artifact containing: ok, coverage, threshold (for reference), total, embedded, reason (if failed), and a snapshot of effective configuration

---

### Requirement: Award–Patent Semantic Similarity Join
The system SHALL compute semantic similarity between embedded awards and patents and persist top‑k matches with thresholds.

#### Scenario: Top‑k similarity with thresholding
- WHEN award and patent embeddings are available
- THEN the system SHALL compute cosine similarity and persist the top‑k patent matches per award (default k=10)
- AND matches with cosine similarity below the configured min_score (default 0.60) SHALL be excluded

#### Scenario: Output persistence and schema
- WHEN similarity pairs are produced
- THEN the system SHALL persist a parquet artifact at data/processed/paecter_award_patent_similarity.parquet
- AND each row SHALL include at minimum: award_id, patent_id, cosine_sim, rank, threshold_pass (boolean), backend ("bruteforce" or "faiss"), computed_at (UTC)

#### Scenario: Compute backend selection
- WHEN the scale of comparisons exceeds configured thresholds
- THEN the system SHALL support a configurable backend (bruteforce|faiss) for similarity search
- AND in the absence of FAISS configuration, the system SHALL use brute-force cosine without failure

#### Scenario: Per‑award cap to prevent explosion
- WHEN producing similarity pairs
- THEN the system SHALL enforce a configurable limit_per_award (default 50) to cap the number of retained matches per award

---

### Requirement: Classifier Cohesion Analysis via Embeddings
The system SHALL evaluate the cohesion and separation of CET-based classifiers using embedding-space metrics.

#### Scenario: Intra‑ vs inter‑class metrics
- WHEN embeddings and CET classifications are available for a dataset
- THEN the system SHALL compute per-class intra-class mean cosine and inter-class mean cosine
- AND it SHALL report the margin (intra_mean − inter_mean) and the share of classes with margin ≥ a configured threshold (default 0.05)

#### Scenario: Class size guardrails
- WHEN a class has fewer than the configured minimum items (default 50)
- THEN the system SHALL exclude that class from cohesion reporting
- AND the exclusion count SHALL be captured in the metrics

#### Scenario: Metrics artifact
- WHEN the analysis completes
- THEN the system SHALL persist a JSON artifact at data/processed/paecter_classifier_cohesion.json
- AND metrics SHALL be attached to Dagster asset metadata

---

### Requirement: Calibration and Drift Monitoring for PaECTER
The system SHALL provide calibration checks for similarity distributions and detect drift over time.

#### Scenario: Negative‑pair similarity bound
- WHEN evaluating random negative award–patent pairs
- THEN the system SHALL compute and record the mean cosine similarity
- AND the system SHALL compare the mean to a configured upper bound (default 0.30) and include the result in a checks JSON

#### Scenario: Heuristic positive‑pair calibration
- WHEN evaluating heuristic positive pairs (e.g., shared recipient + temporal proximity)
- THEN the system SHALL compute and record the mean cosine similarity
- AND the system SHALL compare the mean to a configured lower bound (default 0.55) and include the result in a checks JSON

#### Scenario: Drift detection against baselines
- WHEN current distribution metrics are compared to historical baselines
- THEN statistically significant shifts (or ≥ configured absolute deltas) in negative/positive means or embedding coverage SHALL be detected
- AND drift findings SHALL be written to reports/alerts/paecter_drift.json with metric names, current values, baseline values, and deltas