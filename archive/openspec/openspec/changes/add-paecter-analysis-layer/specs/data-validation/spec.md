#ADDED Requirements

##Requirement: PaECTER Embedding Coverage Validation

The system SHALL validate that PaECTER embeddings are present for a minimum share of eligible records and block downstream steps when coverage is insufficient.

###Scenario: Patent embedding coverage threshold

- WHEN the patent embedding artifact at data/processed/paecter_embeddings_patents.parquet is produced
- THEN the system SHALL compute coverage = embedded_patents / eligible_patents
- AND the coverage threshold SHALL default to 0.98 and be configurable via paecter.validation.coverage.patents
- AND if coverage < threshold, an ERROR severity validation failure SHALL be raised and downstream similarity and cohesion assets SHALL be blocked

#### Scenario: Award embedding coverage threshold

- WHEN the award embedding artifact at data/processed/paecter_embeddings_awards.parquet is produced
- THEN the system SHALL compute coverage = embedded_awards / eligible_awards
- AND the coverage threshold SHALL default to 0.95 and be configurable via paecter.validation.coverage.awards
- AND if coverage < threshold, an ERROR severity validation failure SHALL be raised and downstream similarity and cohesion assets SHALL be blocked

#### Scenario: Coverage metrics reporting

- WHEN coverage is computed
- THEN the system SHALL emit coverage metrics to Dagster asset metadata
- AND the system SHALL write a checks JSON adjacent to each artifact with fields: ok, coverage, threshold, total, embedded, and reason (if failed)

---

### Requirement: PaECTER Similarity Quality Gates

The system SHALL validate the quality of award–patent similarity scores using calibrated bounds for negative and heuristic positive pairs and prevent consumption on failure.

#### Scenario: Negative-pair similarity bound

- WHEN random negative award–patent pairs are sampled (without shared recipient or known linkage)
- THEN the mean cosine similarity SHALL be ≤ the configured upper bound (default 0.30, paecter.validation.similarity.neg_mean_max)
- AND if the bound is violated, an ERROR severity validation failure SHALL be raised and logged with sample size and summary statistics

#### Scenario: Heuristic positive-pair calibration

- WHEN heuristic positive award–patent pairs are sampled (e.g., shared recipient and temporal proximity)
- THEN the mean cosine similarity SHALL be ≥ the configured lower bound (default 0.55, paecter.validation.similarity.pos_mean_min)
- AND if the bound is violated, a WARNING severity issue SHALL be raised by default and MAY be configured to ERROR for strict environments

#### Scenario: Similarity artifact integrity

- WHEN validating similarity output at data/processed/paecter_award_patent_similarity.parquet
- THEN all records SHALL have award_id, patent_id, cosine_sim ∈ [0,1], rank ≥ 1, and threshold_pass ∈ {true,false}
- AND invalid records SHALL be counted and reported; if invalid_rate > 0.01 (configurable at paecter.validation.similarity.invalid_rate_max), validation SHALL fail with ERROR

---

### Requirement: PaECTER Classifier Cohesion Gate

The system SHALL validate that CET-based classes exhibit sufficient cohesion in embedding space relative to separation from other classes.

#### Scenario: Margin-based cohesion threshold

- WHEN per-class intra-class mean cosine and inter-class mean cosine are computed from data/processed/paecter_classifier_cohesion.json
- THEN the margin = intra_mean − inter_mean SHALL meet or exceed the configured threshold (default 0.05, paecter.validation.cohesion.margin_min)
- AND at least the configured share of classes (default 0.70, paecter.validation.cohesion.min_share) with size ≥ 50 (paecter.validation.cohesion.min_size) SHALL satisfy the margin threshold
- AND if the share falls below the threshold, validation SHALL fail with ERROR and include a list of worst offending classes

#### Scenario: Small-class handling

- WHEN a class has fewer than the configured minimum members (default 50, paecter.validation.cohesion.min_size)
- THEN that class SHALL be excluded from cohesion checks
- AND the excluded count and reasons SHALL be reported in the metrics and validation output

---

### Requirement: PaECTER Drift Detection and Baseline Comparison

The system SHALL detect distribution drift in similarity and coverage metrics relative to historical baselines and surface actionable alerts.

#### Scenario: Baseline comparison and alerting

- WHEN current metrics are compared to the most recent baseline of similar dataset size
- THEN absolute mean shifts greater than configured deltas SHALL be flagged (defaults: neg_mean +0.05, pos_mean −0.05, coverage −0.02 at paecter.validation.drift.{neg_mean_delta_max,pos_mean_delta_min,coverage_delta_min})
- AND deviations SHALL be written to reports/alerts/paecter_drift.json with metric names, current, baseline, and deltas
- AND WARNING alerts SHALL be emitted for minor deviations; ERROR alerts for major deviations (configurable)

#### Scenario: Baseline persistence

- WHEN a validation run completes successfully
- THEN the system SHALL persist updated baselines for similarity means and coverage in reports/benchmarks/paecter_validation_baseline.json
- AND baseline updates SHALL be gated to controlled environments (e.g., non-PR CI or approved runs) to avoid noise and unintended drift

---

### Requirement: PaECTER Configuration Source of Truth

The system SHALL source all PaECTER validation thresholds from configuration with environment overrides and record the effective values in artifacts.

#### Scenario: Configuration-driven thresholds

- WHEN validation thresholds are loaded
- THEN the system SHALL read from config/base.yaml under paecter.validation.* with environment variable overrides (e.g., SBIR_ETL__PAECTER__VALIDATION__COVERAGE__PATENTS)
- AND the effective threshold values SHALL be recorded in checks JSON and asset metadata for auditability

#### Scenario: Safe defaults and failure modes

- WHEN configuration keys are missing or malformed
- THEN safe defaults specified in this spec SHALL be applied
- AND missing or malformed configuration SHALL be reported as a WARNING with details on the defaulted keys
- AND if critical configuration is invalid and prevents evaluation, the system SHALL raise an ERROR with an actionable remediation message