# Transition Detection Deployment Checklist

## Pre-Deployment Phase (48 hours before)

### Code & Quality Assurance
- [ ] All tests passing locally
  ```bash
  poetry run pytest tests/unit/test_transition*.py -v
  poetry run pytest tests/integration/test_transition_integration.py -v
  poetry run pytest tests/e2e/test_transition_e2e.py -v
  ```
- [ ] Code review completed and approved
  - [ ] 2+ reviewers sign-off
  - [ ] No outstanding comments
  - [ ] Security review complete

- [ ] Static analysis passing
  ```bash
  poetry run mypy src/transition/
  poetry run pylint src/transition/
  ```

- [ ] Coverage requirements met (≥80% on new code)
  ```bash
  poetry run coverage run -m pytest tests/unit/
  poetry run coverage report --minimum-coverage=80
  ```

### Documentation & Configuration
- [ ] All documentation updated
  - [ ] docs/transition/detection_algorithm.md current
  - [ ] docs/transition/scoring_guide.md current
  - [ ] docs/transition/vendor_matching.md current
  - [ ] docs/transition/evidence_bundles.md current
  - [ ] docs/schemas/transition-graph-schema.md current
  - [ ] docs/transition/cet_integration.md current
  - [ ] docs/data-dictionaries/transition_fields_dictionary.md current
  - [ ] docs/deployment/transition_deployment.md current

- [ ] Configuration files validated
  ```bash
  poetry run python -c "import yaml; yaml.safe_load(open('config/transition/detection.yaml'))"
  poetry run python -c "import yaml; yaml.safe_load(open('config/transition/presets.yaml'))"
  poetry run python -c "import yaml; yaml.safe_load(open('config/dev.yaml'))"
  poetry run python -c "import yaml; yaml.safe_load(open('config/staging.yaml'))"
  poetry run python -c "import yaml; yaml.safe_load(open('config/prod.yaml'))"
  ```

- [ ] README updated with transition detection section
- [ ] CHANGELOG updated with version notes

### Environment Preparation
- [ ] Development environment ready
  ```bash
  make clean
  poetry install
  docker-compose down
  docker-compose up -d neo4j postgres
  ```

- [ ] Staging environment prepared
  - [ ] Database backup taken
  - [ ] All services available
  - [ ] Network connectivity verified

- [ ] Production environment prepared (if applicable)
  - [ ] All secrets configured in secrets manager
  - [ ] Database backup taken
  - [ ] Monitoring/alerting configured
  - [ ] Runbooks available

### Data Validation
- [ ] Source data quality verified
  ```bash
  poetry run python scripts/validate_source_data.py \
    --awards data/raw/sbir_awards.parquet \
    --contracts data/processed/contracts.parquet
  ```

- [ ] Data volume acceptable
  - [ ] SBIR awards: ≥100K records
  - [ ] Federal contracts: ≥1M records
  - [ ] Disk space: ≥100GB free

- [ ] Data freshness verified
  - [ ] Awards data < 1 week old
  - [ ] Contracts data < 1 week old
  - [ ] Patents data < 2 weeks old (if using)

### Access & Credentials
- [ ] Neo4j credentials available
  ```bash
  echo $NEO4J_PASSWORD | wc -c  # Should be > 0
  ```

- [ ] AWS credentials configured (if cloud deployment)
  ```bash
  aws sts get-caller-identity  # Should succeed
  ```

- [ ] VPN access verified (if applicable)
  ```bash
  ping neo4j-staging  # Should respond
  ```

### Stakeholder Notification
- [ ] Operations team notified of planned deployment
- [ ] On-call engineer assigned
- [ ] Maintenance window scheduled (if needed)
- [ ] Stakeholder approval obtained

---

## Development Deployment Phase

### Pre-Materialization
- [ ] Development environment started
  ```bash
  docker-compose up -d neo4j postgres
  sleep 10
  curl http://localhost:7687  # Verify Neo4j
  ```

- [ ] Database initialized
  ```bash
  poetry run python scripts/init_transition_system.py --environment development
  ```

- [ ] Source data ingested
  ```bash
  poetry run python scripts/extract_sbir_awards.py --output data/raw/sbir_awards.parquet
  poetry run python scripts/extract_federal_contracts.py --output data/processed/contracts.parquet
  ```

### Asset Materialization
- [ ] Dagster UI accessible
  ```bash
  dagster dev  # http://localhost:3000
  ```

- [ ] Asset dependencies defined
  ```bash
  poetry run python -c "from src.definitions import *; print('Dependencies OK')"
  ```

- [ ] Materialize core assets in order
  - [ ] contracts_ingestion
  - [ ] vendor_resolution
  - [ ] transition_detections
  - [ ] transition_analytics
  - [ ] neo4j_transitions
  - [ ] neo4j_transition_relationships
  - [ ] neo4j_transition_profiles

### Post-Materialization Validation
- [ ] All parquet files generated
  ```bash
  ls -lh data/processed/transitions*
  ls -lh data/processed/vendor_resolution*
  ls -lh data/processed/transition_analytics*
  ```

- [ ] Evidence bundles generated
  ```bash
  wc -l data/processed/transitions_evidence.ndjson
  ```

- [ ] Validation checks passed
  ```bash
  cat data/processed/transitions.checks.json | jq '.status'
  ```

- [ ] Neo4j nodes created
  ```bash
  poetry run cypher-shell -u neo4j -p password -a bolt://localhost:7687 \
    "MATCH (t:Transition) RETURN COUNT(t) as count;"
  ```

---

## Staging Deployment Phase

### Pre-Deployment Staging
- [ ] Code deployed to staging
  ```bash
  git pull origin main
  poetry install --no-dev
  ```

- [ ] Services started
  ```bash
  docker-compose -f docker-compose.yml -f docker-compose.staging.yml up -d
  sleep 30
  curl -f http://staging.example.com/api/health
  ```

- [ ] Database migrations run
  ```bash
  poetry run python scripts/migrate_neo4j.py --environment staging
  ```

### Staging Materialization
- [ ] Full dataset staged
  - [ ] ~252K SBIR awards loaded
  - [ ] ~6.7M federal contracts loaded
  - [ ] Patent data available (if using)

- [ ] Assets materialized
  ```bash
  poetry run dagster job execute -f src/definitions.py \
    -j transition_full_pipeline_job --tags environment=staging
  ```

### Staging Validation
- [ ] Integration tests passing
  ```bash
  poetry run pytest tests/integration/ -v --environment staging
  ```

- [ ] E2E tests passing
  ```bash
  poetry run pytest tests/e2e/ -v --environment staging
  ```

- [ ] Data quality gates passing
  ```bash
  cat data/processed/transition_analytics.checks.json | jq '.'
  ```

- [ ] Performance benchmarks acceptable
  - [ ] Throughput: ≥10K detections/minute
  - [ ] Memory: <30GB peak
  - [ ] Pipeline duration: <60 minutes

- [ ] Neo4j queries responsive
  ```bash
  poetry run cypher-shell -u neo4j -p $NEO4J_PASSWORD -a ${NEO4J_URI} \
    "MATCH (t:Transition) WHERE t.confidence = 'HIGH' RETURN COUNT(t);"
  ```

### Staging Sign-Off
- [ ] QA team sign-off obtained
- [ ] Performance metrics documented
- [ ] Known issues logged (if any)

---

## Production Deployment Phase (if applicable)

### Pre-Production Checks
- [ ] Production backup taken
  ```bash
  poetry run python scripts/backup_neo4j.py \
    --environment production \
    --location s3://backups/pre-deployment-$(date +%Y%m%d)
  ```

- [ ] Rollback plan verified
  - [ ] Previous version documented
  - [ ] Backup restoration tested in staging
  - [ ] Rollback SOP reviewed with ops team

- [ ] Monitoring configured
  - [ ] Datadog dashboards ready
  - [ ] Alert rules enabled
  - [ ] Notification channels tested

### Production Deployment
- [ ] Code deployed to production
  ```bash
  git pull origin main
  poetry install --no-dev
  ```

- [ ] Services started in order
  ```bash
  docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
  sleep 60  # Wait for services to stabilize
  ```

- [ ] Health checks passing
  ```bash
  ./scripts/health_check.sh production
  ```

- [ ] Database migrations run
  ```bash
  poetry run python scripts/migrate_neo4j.py --environment production
  ```

### Production Materialization
- [ ] Full production pipeline started
  ```bash
  poetry run dagster job execute -f src/definitions.py \
    -j transition_full_pipeline_job --tags environment=production
  ```

- [ ] Real-time monitoring dashboard active
  ```bash
  open https://datadog.example.com/sbir-etl/transition
  ```

- [ ] On-call engineer monitoring execution
  - [ ] Watching logs in real-time
  - [ ] Ready to rollback if needed
  - [ ] Alert channels active

---

## Post-Deployment Validation

### Immediate Post-Deployment (First Hour)
- [ ] All services healthy
  ```bash
  curl -f http://example.com/api/health
  curl -f http://dagster.example.com/api/health
  ```

- [ ] No error spikes in logs
  ```bash
  grep -c ERROR logs/transition_detection.log  # Should be 0-5
  ```

- [ ] Data assets generated
  ```bash
  [ -f data/processed/transitions.parquet ] && echo "OK"
  [ -f data/processed/transitions_evidence.ndjson ] && echo "OK"
  [ -f data/processed/transition_analytics.json ] && echo "OK"
  ```

- [ ] Neo4j nodes accessible
  ```bash
  poetry run cypher-shell -u neo4j -p $NEO4J_PASSWORD -a ${NEO4J_URI} \
    "MATCH (t:Transition) RETURN COUNT(t) as count, \
            MAX(t.likelihood_score) as max_score, \
            AVG(t.likelihood_score) as avg_score;"
  ```

### Validation Tests (First 2 Hours)
- [ ] Run smoke tests
  ```bash
  poetry run pytest tests/deployment/test_production_smoke.py -v
  ```

- [ ] Validate output files
  ```bash
  poetry run python scripts/validate_outputs.py --environment production
  ```

- [ ] Query performance acceptable
  ```bash
  poetry run python scripts/benchmark_queries.py --environment production
  ```

- [ ] Data quality gates passing
  ```bash
  cat data/processed/transition_analytics.checks.json | jq '.gates[]'
  ```

### Extended Validation (First 24 Hours)
- [ ] Monitor metrics for anomalies
  - [ ] CPU usage normal: <80%
  - [ ] Memory usage normal: <80%
  - [ ] Network I/O normal
  - [ ] Disk I/O normal

- [ ] No alert escalations
  - [ ] Check alert dashboard
  - [ ] Review critical alerts (if any)
  - [ ] All alerts resolved or acknowledged

- [ ] Data pipeline stable
  - [ ] No job failures
  - [ ] No data loss
  - [ ] Quality metrics consistent

- [ ] Stakeholder feedback positive
  - [ ] Check Slack/email for issues
  - [ ] No critical user complaints
  - [ ] Dashboard accessible to consumers

---

## Known Issues & Mitigation

### If Performance Below Target
- [ ] Increase worker count
  ```bash
  export SBIR_ETL__TRANSITION__WORKERS=16
  ```

- [ ] Increase batch size
  ```bash
  export SBIR_ETL__TRANSITION__BATCH_SIZE=10000
  ```

- [ ] Check system resources
  ```bash
  top -b -n 1 | head -20
  ```

### If Data Quality Gates Fail
- [ ] Investigate source data
  ```bash
  poetry run python scripts/validate_source_data.py --detailed
  ```

- [ ] Re-extract if needed
  ```bash
  poetry run python scripts/extract_federal_contracts.py --force-refresh
  ```

- [ ] Review validation rules
  ```bash
  cat data/processed/transition_analytics.checks.json | jq '.errors[]'
  ```

### If Neo4j Connection Issues
- [ ] Verify connectivity
  ```bash
  poetry run cypher-shell -u neo4j -p $NEO4J_PASSWORD -a ${NEO4J_URI} "RETURN 1;"
  ```

- [ ] Check connection pool
  ```bash
  CALL dbms.connectionCount()
  ```

- [ ] Restart Neo4j if needed
  ```bash
  docker-compose restart neo4j
  sleep 30
  ```

---

## Sign-Off

### QA Sign-Off
- [ ] QA Lead: __________________ Date: __________
- [ ] Comments: ________________________________________________________________

### Operations Sign-Off
- [ ] Ops Lead: __________________ Date: __________
- [ ] On-Call Engineer: __________ Date: __________
- [ ] Comments: ________________________________________________________________

### Project Manager Sign-Off
- [ ] PM: _______________________ Date: __________
- [ ] Deployment Approved: YES / NO
- [ ] Comments: ________________________________________________________________

---

## Post-Deployment Documentation

### Deployment Summary
- Deployment Date/Time: ________________________
- Deployed Version: ________________________
- Environment: [ ] DEV [ ] STAGING [ ] PROD
- Duration: ________________________
- Issues Encountered: ________________________________________________________________

### Metrics
- Total Transitions Detected: ________________________
- HIGH Confidence: ________________________
- LIKELY Confidence: ________________________
- POSSIBLE Confidence: ________________________
- Avg Likelihood Score: ________________________
- Execution Time: ________________________

### Rollback Information
- Rollback Required: YES / NO
- Rollback Date/Time: ________________________
- Reason: ________________________________________________________________

---

## Follow-Up Tasks

- [ ] Update deployment log
- [ ] Send deployment summary email to stakeholders
- [ ] Schedule retrospective (if issues occurred)
- [ ] Update runbooks with lessons learned
- [ ] Review monitoring dashboards for first week
- [ ] Schedule next deployment (if applicable)

---

**Deployment Completed**: __________________ (Date/Time)
**Completed By**: ________________________
**Reviewed By**: ________________________