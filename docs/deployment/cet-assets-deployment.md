# CET Assets Deployment Guide (Staging and Production)

This guide explains how to deploy and operate the CET (Critical & Emerging Technologies) assets in staging and production for the SBIR ETL pipeline. It covers environment setup, secrets, model artifacts, run configs, Docker Compose, job execution, and validation steps.

Contents
- Overview
- Prerequisites
- Secrets and Environment Variables
- Configuration Layout (base + prod overrides)
- Model Artifacts
- Docker Compose (staging/prod)
- Dagster Run Config Examples
- Execution: Staging and Production
- Validation and Health Checks
- Monitoring and Alerts
- Troubleshooting
- Rollback and Change Management
- Appendix: Sample Compose File

---

## Overview

The CET pipeline runs as a set of Dagster assets and a composed Dagster job:

- Core assets:
  - CET taxonomy: `cet_taxonomy`
  - Award classification with evidence: `cet_award_classifications`
  - Company aggregation: `cet_company_profiles`
- Neo4j loaders and relationships:
  - `neo4j_cetarea_nodes`
  - `neo4j_award_cet_enrichment`
  - `neo4j_company_cet_enrichment`
  - `neo4j_award_cet_relationships`
  - `neo4j_company_cet_relationships`
- Orchestrated job:
  - `cet_full_pipeline_job` (taxonomy → classification → aggregation → Neo4j)

Artifacts and checks are written under:
- Processed data: `data/processed/`
- Neo4j load summaries: `data/loaded/neo4j/`
- Alerts and analytics: `reports/alerts/`, `reports/analytics/`

CET model artifacts default to `artifacts/models/cet_classifier_v1.pkl` (overridable via `CET_MODEL_PATH`).

---

## Prerequisites

- Docker and Docker Compose
- A running or containerized Neo4j 5.x instance reachable from the pipeline
- Python 3.11+ (for local runs) or container runtime environment
- The CET configuration files:
  - `config/cet/taxonomy.yaml`
  - `config/cet/classification.yaml`
- The CET model artifact (recommended for prod):
  - Default: `artifacts/models/cet_classifier_v1.pkl`
  - Without a model, `cet_award_classifications` will write a placeholder output and a checks JSON indicating the artifact is missing.

---

## Secrets and Environment Variables

Do not commit secrets. Provide them via environment variables or a secrets manager.

Required (for Neo4j):
- `NEO4J_URI` (e.g., bolt://neo4j:7687)
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE` (optional; defaults to `neo4j`)

Optional/Recommended:
- `CET_MODEL_PATH` (override for the classifier artifact path)
- `SBIR_ETL__CET__SAMPLE_SIZE` / `SBIR_ETL__CET__SAMPLE_SEED` (sampling controls)

Example `.env` (do not commit):
```
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=replace_me
NEO4J_DATABASE=neo4j
CET_MODEL_PATH=/app/artifacts/models/cet_classifier_v1.pkl
```

---

## Configuration Layout (base + prod overrides)

- Default settings: `config/base.yaml`
- CET configs: `config/cet/taxonomy.yaml`, `config/cet/classification.yaml`
- Production overrides (template provided): `config/envs/prod.yaml`

Recommended practice:
- Keep `base.yaml` minimal and generic.
- Layer `config/envs/prod.yaml` for stricter thresholds, batch sizes, and schedule hints.
- Store deployment-specific values in environment variables or your orchestrator’s secret store.

---

## Model Artifacts

- Default classifier path: `artifacts/models/cet_classifier_v1.pkl`
- Override via `CET_MODEL_PATH`
- Versioning: include metadata JSON or a `VERSION` file in `artifacts/models/` to track promoted models
- Promotion flow:
  1) Train/evaluate model offline; save to new path (e.g., `artifacts/models/cet_classifier_v1.1.pkl`)
  2) Update `CET_MODEL_PATH` in staging
  3) Validate in staging (classification coverage, confidence rates, drift checks)
  4) Promote to production by updating the prod environment variable

If the artifact is missing or cannot be loaded, `cet_award_classifications` outputs an empty schema-compatible file and a checks JSON with `"reason": "model_missing"` or `"model_load_failed"`.

---

## Docker Compose (staging/prod)

Run Dagster and Neo4j together for staging, or point Dagster to your managed/prod Neo4j. Persist volumes for `data/`, `artifacts/`, `reports/`, and `logs/`.

Example service outline (see Appendix for full sample):
- `dagster` (webserver + definitions)
- `neo4j` (for staging; omit in prod if using managed Neo4j)
- Bind mounts:
  - `./data:/app/data`
  - `./artifacts:/app/artifacts`
  - `./reports:/app/reports`
  - `./logs:/app/logs`
  - `./config:/app/config`

---

## Dagster Run Config Examples

You can materialize assets via Dagster UI (recommended) or CLI. Below are YAML snippets suitable for a Dagster run config (adjust paths as needed).

1) CET taxonomy (optional: override I/O paths)
```yaml
ops:
  cet_taxonomy:
    config: {}
```

2) Neo4j CETArea nodes (read taxonomy from processed)
```yaml
ops:
  neo4j_cetarea_nodes:
    config:
      taxonomy_parquet: "data/processed/cet_taxonomy.parquet"
      taxonomy_json: "data/processed/cet_taxonomy.json"
      create_constraints: true
      create_indexes: true
      batch_size: 2000
```

3) Award classifications (ensure `CET_MODEL_PATH` is set or artifact exists at default path)
```yaml
ops:
  cet_award_classifications:
    config: {}
```

4) Company profiles
```yaml
ops:
  cet_company_profiles:
    config: {}
```

5) Award/Company enrichment + relationships (Neo4j)
```yaml
ops:
  neo4j_award_cet_enrichment:
    config:
      classifications_parquet: "data/processed/cet_award_classifications.parquet"
      classifications_json: "data/processed/cet_award_classifications.json"
      batch_size: 2000

  neo4j_company_cet_enrichment:
    config:
      profiles_parquet: "data/processed/cet_company_profiles.parquet"
      profiles_json: "data/processed/cet_company_profiles.json"
      key_property: "uei"
      batch_size: 2000

  neo4j_award_cet_relationships:
    config:
      classifications_parquet: "data/processed/cet_award_classifications.parquet"
      classifications_json: "data/processed/cet_award_classifications.json"
      rel_type: "APPLICABLE_TO"
      batch_size: 2000

  neo4j_company_cet_relationships:
    config:
      profiles_parquet: "data/processed/cet_company_profiles.parquet"
      profiles_json: "data/processed/cet_company_profiles.json"
      key_property: "uei"
      rel_type: "SPECIALIZES_IN"
      batch_size: 2000
```

`cet_full_pipeline_job` bundles these assets; you can provide a single run config with the relevant `ops` sections.

---

## Execution: Staging and Production

Staging (recommended flow)
1) Bring up the stack (Neo4j + Dagster) via Compose
2) Ensure configs and model artifact are mounted
3) Materialize:
   - `cet_taxonomy`
   - `cet_award_classifications`
   - `cet_company_profiles`
   - `neo4j_cetarea_nodes`
   - `neo4j_award_cet_enrichment`
   - `neo4j_company_cet_enrichment`
   - `neo4j_award_cet_relationships`
   - `neo4j_company_cet_relationships`
4) Review checks/alerts and run Cypher spot checks (see Validation)

Production
- Point Dagster to managed Neo4j via `NEO4J_URI`
- Use stricter config via `config/envs/prod.yaml`
- Enable schedules:
  - Daily `cet_full_pipeline_job`
  - Daily `cet_drift_job` for monitoring
- Follow change management for model promotions and taxonomy changes (OpenSpec)

---

## Validation and Health Checks

File-based checks (written by assets)
- Taxonomy: `data/processed/cet_taxonomy.checks.json`
- Award classifications: `data/processed/cet_award_classifications.checks.json`
  - Keys: `num_awards`, `num_classified`, `high_conf_rate`, `evidence_coverage_rate`
- Company profiles: `data/processed/cet_company_profiles.checks.json`
- Neo4j loaders: `data/loaded/neo4j/*checks.json`
- Analytics/drift: `reports/alerts/cet_analytics.alerts.json`, `reports/alerts/cet_drift_detection.alerts.json`

Neo4j spot checks (Cypher)
```cypher
// Count CETArea nodes
MATCH (c:CETArea) RETURN count(c);

// Sample Award CET enrichment properties
MATCH (a:Award)
WHERE a.cet_primary_id IS NOT NULL
RETURN a.award_id, a.cet_primary_id, a.cet_primary_score
LIMIT 5;

// Award -> CET relationships
MATCH (a:Award)-[r:APPLICABLE_TO]->(c:CETArea)
RETURN a.award_id, c.cet_id, r.primary, r.score
LIMIT 10;

// Company dominant CET
MATCH (c:Company)-[r:SPECIALIZES_IN]->(a:CETArea)
WHERE r.primary = true
RETURN c.uei, a.cet_id, r.score, r.specialization_score
LIMIT 10;
```

Validation criteria (prod)
- Award classification coverage: primary CET present on majority of awards
- High confidence rate: meets or exceeds target in `config/cet/classification.yaml`
- Evidence coverage: a large fraction of awards carry evidence excerpts
- Neo4j load success: near 100% and no constraint violations
- Drift/analytics alerts: no regressions over baselines

---

## Monitoring and Alerts

- Logs: `logs/sbir-etl.log` (JSON recommended)
- Metrics: `logs/metrics.json`
- Alerts:
  - Portfolio analytics alerts in `reports/alerts/`
  - Drift detection alerts in `reports/alerts/`
- Thresholds:
  - Tightened in `config/envs/prod.yaml`
  - Model quality thresholds in `config/cet/classification.yaml`

---

## Troubleshooting

Common issues
- Missing model artifact
  - `cet_award_classifications.checks.json` shows `"reason": "model_missing"`
  - Provide `artifacts/models/cet_classifier_v1.pkl` or set `CET_MODEL_PATH`
- Parquet engine not available
  - Assets fall back to NDJSON (`.json`), touch `.parquet` placeholder
  - Install a parquet engine if parquet outputs are required (e.g., `pyarrow`)
- spaCy model not available
  - Evidence extraction degrades to simple mode; install `en_core_web_sm` if needed
- Neo4j connectivity
  - Verify `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
  - Confirm port reachability and database selection (`NEO4J_DATABASE`)

Data sanity
- Check processed outputs in `data/processed/` (parquet or NDJSON)
- Inspect checks JSON for counts/coverage

---

## Rollback and Change Management

- Taxonomy updates:
  - Commit updates to `config/cet/taxonomy.yaml`
  - Run taxonomy checks (CI does this automatically)
  - Document version string changes and effective date
- Model rollbacks:
  - Re-point `CET_MODEL_PATH` to prior artifact
  - Re-materialize award classifications and downstream assets
- Neo4j changes:
  - Assets use idempotent MERGE semantics and constraints
  - If schema evolves, update loaders and document in `docs/schemas/`

---

## Appendix: Sample Compose File (Staging)

This example starts Neo4j and the ETL runtime with bind-mounted volumes. Adjust to your environment and do not embed secrets in the file.

```yaml
version: "3.9"

services:
  neo4j:
    image: neo4j:5
    container_name: cet-neo4j
    ports:
      - "7474:7474"   # Browser (optional)
      - "7687:7687"   # Bolt
    environment:
      NEO4J_AUTH: "neo4j/replace_me"
      NEO4J_dbms_memory_heap_max__size: 1G
      NEO4J_dbms_memory_pagecache_size: 512M
    volumes:
      - neo4j-data:/data
      - neo4j-logs:/logs
    restart: unless-stopped

  etl:
    image: sbir-etl:latest
    container_name: cet-etl
    depends_on:
      - neo4j
    env_file:
      - ./.env        # provides NEO4J_* and optional CET_MODEL_PATH
    environment:
      # Optional overrides for CET batch sizes at runtime
      SBIR_ETL__CET__SAMPLE_SIZE: "50"
      SBIR_ETL__CET__SAMPLE_SEED: "42"
    volumes:
      - ./config:/app/config
      - ./data:/app/data
      - ./artifacts:/app/artifacts
      - ./reports:/app/reports
      - ./logs:/app/logs
    ports:
      - "3000:3000"   # Dagster UI
    restart: unless-stopped
    # Entrypoint provided in image: starts Dagster webserver and loads definitions

volumes:
  neo4j-data:
  neo4j-logs:
```

Deployment checklist (quick)
- [ ] Copy `.env.example.staging` to `.env` and set Neo4j credentials (and optional `CET_MODEL_PATH`)
- [ ] Start staging stack with `docker-compose.cet-staging.yml` (or set `NEO4J_URI` to use external Neo4j)
- [ ] Volumes present and writable: `data/`, `artifacts/`, `reports/`, `logs/`
- [ ] `config/cet/taxonomy.yaml` and `config/cet/classification.yaml` present
- [ ] `artifacts/models/cet_classifier_v1.pkl` available or override path
- [ ] Materialize `cet_taxonomy` and then `cet_full_pipeline_job`
- [ ] Validate checks and run Cypher spot checks
- [ ] Configure schedule crons via env (optional overrides):
      `SBIR_ETL__DAGSTER__SCHEDULES__ETL_JOB` (default `0 2 * * *`),
      `SBIR_ETL__DAGSTER__SCHEDULES__CET_FULL_PIPELINE_JOB` (default `0 2 * * *`),
      `SBIR_ETL__DAGSTER__SCHEDULES__CET_DRIFT_JOB` (default `0 6 * * *`)
- [ ] Enable schedules (prod), monitor alerts and drift daily

---