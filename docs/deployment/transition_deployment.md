# Transition Detection System - Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the Transition Detection system to development, staging, and production environments.

**Deployment Environments**:
- **Development (Local)**: Single-machine setup for testing
- **Staging**: Full-scale testing environment with production-like data
- **Production**: Live deployment with monitoring and alerts

## Pre-Deployment Requirements

### System Requirements

**Minimum Hardware**:
- **CPU**: 4+ cores
- **Memory**: 16 GB RAM (32 GB recommended for production)
- **Disk**: 100 GB free space (for contracts data, processed output, Neo4j)
- **Network**: 100 Mbps minimum (1 Gbps recommended for large datasets)

**Software**:
- Python 3.11 or 3.12
- Poetry (dependency management)
- Docker & Docker Compose (for containerized deployment)
- Neo4j 5.x (database)
- PostgreSQL 13+ (optional, for airflow metadata store)

### Access Requirements

Before deployment, ensure you have:
- Access to source data systems (SBIR.gov API, USAspending.gov, USPTO)
- Neo4j connection credentials
- AWS/cloud credentials (if deploying to cloud)
- VPN access (if applicable)

### Data Requirements

**Minimum Dataset Size**:
- 100K+ SBIR awards (full scope: 252K)
- 1M+ federal contracts (full scope: 6.7M)
- Patent data (optional, for patent signal enrichment)

**Data Formats**:
- SBIR awards: CSV or Parquet
- Federal contracts: PostgreSQL dump (.dat.gz) or CSV
- Patents: CSV or Parquet (optional)

## Environment Configuration

### Development Environment

**Setup**:
```bash
# 1. Install dependencies
poetry install

# 2. Create development data directories
mkdir -p data/raw data/processed reports

# 3. Set development environment variables
export SBIR_ETL_ENV=development
export SBIR_ETL_CONFIG_PATH=config/dev.yaml
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=password

# 4. Start Neo4j (via Docker Compose)
docker-compose up -d neo4j

# 5. Verify Neo4j connection
poetry run python -c "from neo4j import GraphDatabase; driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password')); print('Connected:', driver.verify_connectivity())"
```

**Configuration** (`config/dev.yaml`):
```yaml
transition:
  enabled: true
  preset: balanced  # Options: high_precision, balanced, broad_discovery
  
  # Smaller dataset for faster iteration
  sample_size: 5000
  vendor_resolution:
    fuzzy_threshold: 0.85
  
  # Dev-specific performance tuning
  batch_size: 1000
  workers: 1
  
  # More verbose logging
  log_level: DEBUG

neo4j:
  uri: bolt://localhost:7687
  username: neo4j
  password: password
  driver_config:
    connection_pool_size: 50
    max_transaction_retry_time: 30
```

### Staging Environment

**Setup**:
```bash
# 1. Use docker-compose with staging overrides
docker-compose -f docker-compose.yml -f docker-compose.staging.yml up -d

# 2. Set staging environment variables
export SBIR_ETL_ENV=staging
export SBIR_ETL_CONFIG_PATH=config/staging.yaml
export NEO4J_URI=bolt://neo4j-staging:7687
export NEO4J_USERNAME=neo4j_staging
export NEO4J_PASSWORD=${STAGING_NEO4J_PASSWORD}

# 3. Run database migrations
poetry run python scripts/migrate_neo4j.py --environment staging

# 4. Verify staging setup
poetry run pytest tests/integration/ -v --environment staging
```

**Configuration** (`config/staging.yaml`):
```yaml
transition:
  enabled: true
  preset: balanced
  
  # Full dataset for realistic testing
  sample_size: null  # Use all data
  
  vendor_resolution:
    fuzzy_threshold: 0.82
    cache_enabled: true
  
  batch_size: 5000
  workers: 4
  
  log_level: INFO

neo4j:
  uri: bolt://neo4j-staging:7687
  username: neo4j_staging
  password: ${NEO4J_STAGING_PASSWORD}
  driver_config:
    connection_pool_size: 100
    max_transaction_retry_time: 60
```

### Production Environment

**Setup**:
```bash
# 1. Use production docker-compose
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 2. Set production environment variables (from secrets manager)
export SBIR_ETL_ENV=production
export SBIR_ETL_CONFIG_PATH=config/prod.yaml
export NEO4J_URI=${PROD_NEO4J_URI}
export NEO4J_USERNAME=${PROD_NEO4J_USERNAME}
export NEO4J_PASSWORD=${PROD_NEO4J_PASSWORD}
export AWS_ACCESS_KEY_ID=${PROD_AWS_KEY}
export AWS_SECRET_ACCESS_KEY=${PROD_AWS_SECRET}

# 3. Run database migrations
poetry run python scripts/migrate_neo4j.py --environment production

# 4. Run pre-deployment validation
poetry run python scripts/validate_deployment.py --environment production

# 5. Start services
systemctl start sbir-etl-transition
systemctl start sbir-etl-dagster
```

**Configuration** (`config/prod.yaml`):
```yaml
transition:
  enabled: true
  preset: balanced  # Or custom for production
  
  # Full production dataset
  sample_size: null
  
  vendor_resolution:
    fuzzy_threshold: 0.80
    cache_enabled: true
    cache_ttl_hours: 24
  
  batch_size: 10000
  workers: 8
  
  # Production logging: JSON for log aggregation
  log_level: INFO
  log_format: json
  
  # Enhanced monitoring
  metrics_enabled: true
  metrics_interval_seconds: 60

neo4j:
  uri: ${PROD_NEO4J_URI}
  username: ${PROD_NEO4J_USERNAME}
  password: ${PROD_NEO4J_PASSWORD}
  driver_config:
    connection_pool_size: 200
    max_transaction_retry_time: 120
    encrypted: true
    trust: TRUST_SYSTEM_CA_SIGNED_CERTIFICATES

monitoring:
  datadog_enabled: true
  datadog_api_key: ${DATADOG_API_KEY}
  error_alerting: true
  alert_email: operations@example.com
```

## Database Setup

### Neo4j Initialization

**For All Environments**:

```bash
# 1. Create transition-specific indexes
poetry run python -c "
from src.loaders.transition_loader import TransitionLoader
loader = TransitionLoader(uri='${NEO4J_URI}', user='${NEO4J_USERNAME}', password='${NEO4J_PASSWORD}')
loader.ensure_indexes()
print('Indexes created successfully')
"

# 2. Verify indexes
poetry run cypher-shell -u ${NEO4J_USERNAME} -p ${NEO4J_PASSWORD} -a ${NEO4J_URI} \
  "SHOW INDEXES WHERE name CONTAINS 'transition' RETURN *;"

# 3. Set database constraints
poetry run cypher-shell -u ${NEO4J_USERNAME} -p ${NEO4J_PASSWORD} -a ${NEO4J_URI} << 'EOF'
CREATE CONSTRAINT transition_id_unique IF NOT EXISTS 
  ON (t:Transition) ASSERT t.transition_id IS UNIQUE;
CREATE CONSTRAINT award_id_unique IF NOT EXISTS 
  ON (a:Award) ASSERT a.award_id IS UNIQUE;
CREATE CONSTRAINT contract_id_unique IF NOT EXISTS 
  ON (c:Contract) ASSERT c.contract_id IS UNIQUE;
EOF
```

### Data Preparation

**Download and Process Source Data**:

```bash
# 1. Extract SBIR awards
poetry run python scripts/extract_sbir_awards.py \
  --source sbir.gov \
  --output data/raw/sbir_awards.parquet \
  --years 2020-2024

# 2. Extract federal contracts
poetry run python scripts/extract_federal_contracts.py \
  --source usaspending \
  --output data/processed/contracts.parquet \
  --years 2020-2024

# 3. Validate data quality
poetry run python scripts/validate_source_data.py \
  --awards data/raw/sbir_awards.parquet \
  --contracts data/processed/contracts.parquet
```

## Deployment Steps

### Development Deployment

```bash
# Step 1: Start services
make start-dev

# Step 2: Run initialization
poetry run python scripts/init_transition_system.py --environment development

# Step 3: Run Dagster asset materialization
poetry run dagster job execute -f src/definitions.py -j transition_full_pipeline_job

# Step 4: Validate outputs
poetry run python scripts/validate_outputs.py \
  --environment development \
  --check_files data/processed/transitions.parquet

# Step 5: Review logs
tail -f logs/transition_detection.log
```

### Staging Deployment

```bash
# Step 1: Stop existing staging services
docker-compose -f docker-compose.staging.yml down

# Step 2: Pull latest code and dependencies
git pull origin main
poetry install --no-dev

# Step 3: Start services
docker-compose -f docker-compose.yml -f docker-compose.staging.yml up -d

# Step 4: Wait for services to be healthy
sleep 30
curl -f http://localhost:8000/api/health || exit 1

# Step 5: Run data pipeline
poetry run dagster job execute -f src/definitions.py -j transition_full_pipeline_job

# Step 6: Run staging validation tests
poetry run pytest tests/integration/ -v --environment staging --tb=short

# Step 7: Generate validation report
poetry run python scripts/generate_deployment_report.py --environment staging
```

### Production Deployment

```bash
# Step 1: Pre-deployment checks
poetry run python scripts/validate_deployment.py --environment production || exit 1

# Step 2: Backup current database
poetry run python scripts/backup_neo4j.py --environment production --location s3://backups/

# Step 3: Deploy new version
docker-compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Step 4: Run migrations
poetry run python scripts/migrate_neo4j.py --environment production --confirm

# Step 5: Health checks
./scripts/health_check.sh production
if [ $? -ne 0 ]; then
  echo "Health checks failed! Rolling back..."
  ./scripts/rollback.sh production
  exit 1
fi

# Step 6: Notify operations
curl -X POST https://alerts.example.com/deployments \
  -H "Content-Type: application/json" \
  -d '{"status": "deployed", "version": "'$(git describe --tags)'", "environment": "production"}'

echo "Production deployment complete!"
```

## Verification & Validation

### Post-Deployment Checklist

```bash
#!/bin/bash
# scripts/post_deployment_checklist.sh

ENVIRONMENT=$1

echo "Post-Deployment Validation for $ENVIRONMENT"

# 1. Check service health
echo "Checking services..."
curl -f http://localhost:8000/api/health || { echo "Dagster unhealthy"; exit 1; }
poetry run python -c "from neo4j import GraphDatabase; GraphDatabase.driver('${NEO4J_URI}', auth=('${NEO4J_USERNAME}', '${NEO4J_PASSWORD}')).verify_connectivity()" || { echo "Neo4j unhealthy"; exit 1; }

# 2. Verify data availability
echo "Checking data..."
[ -f data/processed/transitions.parquet ] || { echo "Transitions parquet missing"; exit 1; }
[ -f data/processed/transitions_evidence.ndjson ] || { echo "Evidence NDJSON missing"; exit 1; }

# 3. Validate data quality
echo "Validating data quality..."
poetry run python scripts/validate_outputs.py --environment $ENVIRONMENT || exit 1

# 4. Check Neo4j indexes
echo "Verifying Neo4j indexes..."
poetry run cypher-shell -u ${NEO4J_USERNAME} -p ${NEO4J_PASSWORD} -a ${NEO4J_URI} \
  "SHOW INDEXES WHERE type = 'RANGE' RETURN count(*) as index_count;" || exit 1

# 5. Run smoke tests
echo "Running smoke tests..."
poetry run pytest tests/e2e/test_transition_deployment.py -v -m smoke || exit 1

# 6. Performance baseline
echo "Establishing performance baseline..."
poetry run python scripts/benchmark_performance.py --environment $ENVIRONMENT

echo "✓ All post-deployment checks passed!"
```

### Validation Tests

```bash
# Run comprehensive validation suite
poetry run pytest tests/deployment/ -v --environment production

# Expected output:
# - test_transitions_parquet_exists: PASSED
# - test_transitions_schema_valid: PASSED
# - test_evidence_ndjson_readable: PASSED
# - test_neo4j_transition_nodes_loaded: PASSED
# - test_neo4j_relationships_created: PASSED
# - test_analytics_json_valid: PASSED
# - test_query_performance_acceptable: PASSED
```

## Configuration Override via Environment Variables

### Common Overrides

```bash
# Scoring thresholds
export SBIR_ETL__TRANSITION__DETECTION__HIGH_CONFIDENCE_THRESHOLD=0.88
export SBIR_ETL__TRANSITION__DETECTION__LIKELY_CONFIDENCE_THRESHOLD=0.70

# Timing window (days)
export SBIR_ETL__TRANSITION__DETECTION__MIN_DAYS=0
export SBIR_ETL__TRANSITION__DETECTION__MAX_DAYS=730

# Signal weights (must sum to 1.0)
export SBIR_ETL__TRANSITION__DETECTION__AGENCY_WEIGHT=0.25
export SBIR_ETL__TRANSITION__DETECTION__TIMING_WEIGHT=0.20
export SBIR_ETL__TRANSITION__DETECTION__COMPETITION_WEIGHT=0.20
export SBIR_ETL__TRANSITION__DETECTION__PATENT_WEIGHT=0.15
export SBIR_ETL__TRANSITION__DETECTION__CET_WEIGHT=0.10

# Vendor resolution
export SBIR_ETL__TRANSITION__VENDOR_RESOLUTION__FUZZY_PRIMARY_THRESHOLD=0.85
export SBIR_ETL__TRANSITION__VENDOR_RESOLUTION__FUZZY_SECONDARY_THRESHOLD=0.70

# Performance tuning
export SBIR_ETL__TRANSITION__DETECTION__BATCH_SIZE=10000
export SBIR_ETL__TRANSITION__DETECTION__WORKERS=8
```

## Monitoring & Alerting

### Metrics to Monitor

```yaml
# Key metrics for production monitoring

Performance:
  - detection_throughput: Detections per minute (target: ≥10K)
  - vendor_resolution_duration: Resolution time (target: <100ms per resolution)
  - neo4j_load_duration: Loading time (target: <50ms per node)
  - memory_usage: Peak memory (alert if >80% utilization)

Quality:
  - vendor_match_rate: % of awards resolved (target: ≥80%)
  - detection_success_rate: % complete without errors (target: ≥99%)
  - evidence_bundle_completeness: % with full evidence (target: 100%)
  - neo4j_load_success_rate: % successful node creations (target: ≥99%)

Data:
  - total_transitions_detected: Count of detections
  - confidence_distribution: % HIGH/LIKELY/POSSIBLE
  - avg_likelihood_score: Mean transition score
  - patent_backed_rate: % with patent backing

Error Rates:
  - vendor_resolution_errors: Failed resolutions (target: <1%)
  - scoring_errors: Scoring failures (target: 0%)
  - neo4j_load_errors: DB write failures (target: <1%)
  - data_quality_gate_failures: Failed gates (alert immediately)
```

### Alerting Rules

```yaml
alerts:
  - name: DetectionThroughputDegraded
    condition: detection_throughput < 5000  # Below 50% of target
    severity: WARNING
    action: Check worker availability and system resources

  - name: VendorResolutionFailed
    condition: vendor_match_rate < 70
    severity: CRITICAL
    action: Investigate vendor data quality, may require re-ingestion

  - name: Neo4jLoadFailures
    condition: neo4j_load_success_rate < 95
    severity: CRITICAL
    action: Check Neo4j health, connection pool, disk space

  - name: MemoryUsageHigh
    condition: memory_usage > 0.85
    severity: WARNING
    action: Investigate memory leaks, increase resource allocation

  - name: PipelineFailed
    condition: pipeline_exit_code != 0
    severity: CRITICAL
    action: Immediate investigation, check logs, may need rollback
```

## Troubleshooting

### Common Issues

**Issue: Vendor Resolution Slow**
- Cause: Large dataset, inefficient matching
- Solution:
  ```bash
  # Enable caching
  export SBIR_ETL__VENDOR_RESOLUTION__CACHE_ENABLED=true
  
  # Reduce fuzzy matching scope
  export SBIR_ETL__VENDOR_RESOLUTION__FUZZY_THRESHOLD=0.90
  
  # Increase workers
  export SBIR_ETL__TRANSITION__WORKERS=8
  ```

**Issue: Neo4j Connection Timeouts**
- Cause: Connection pool exhausted
- Solution:
  ```bash
  # Increase pool size
  NEO4J_POOL_SIZE=200
  
  # Increase transaction timeout
  export SBIR_ETL__NEO4J__TRANSACTION_TIMEOUT=120
  
  # Restart Neo4j
  docker-compose restart neo4j
  ```

**Issue: Memory Exhaustion**
- Cause: Large batch size, insufficient RAM
- Solution:
  ```bash
  # Reduce batch size
  export SBIR_ETL__TRANSITION__BATCH_SIZE=1000  # From 10000
  
  # Process in multiple phases
  export SBIR_ETL__TRANSITION__PHASE_SIZE=50000  # 50K awards per run
  
  # Increase swap (temporary)
  sudo fallocate -l 8G /swapfile
  ```

**Issue: Data Quality Validation Fails**
- Cause: Source data issues
- Solution:
  ```bash
  # Run data quality check
  poetry run python scripts/validate_source_data.py --detailed
  
  # Re-extract from source
  poetry run python scripts/extract_federal_contracts.py --force-refresh
  
  # Manual data cleansing
  poetry run python scripts/clean_transition_data.py --environment staging
  ```

## Rollback Procedure

### Immediate Rollback

```bash
#!/bin/bash
# scripts/rollback.sh

ENVIRONMENT=$1

echo "Rolling back $ENVIRONMENT to previous version..."

# Step 1: Stop current services
docker-compose -f docker-compose.yml -f docker-compose.${ENVIRONMENT}.yml down

# Step 2: Restore from backup
poetry run python scripts/restore_neo4j.py --environment $ENVIRONMENT --from-backup

# Step 3: Restore code to previous version
git checkout HEAD~1
poetry install

# Step 4: Restart services
docker-compose -f docker-compose.yml -f docker-compose.${ENVIRONMENT}.yml up -d

# Step 5: Verify health
./scripts/post_deployment_checklist.sh $ENVIRONMENT

echo "Rollback complete!"
```

## Maintenance

### Regular Tasks

**Daily**:
- Check system health metrics
- Review error logs
- Verify data pipeline completeness

**Weekly**:
- Database optimization (Neo4j REINDEX)
- Performance baseline comparison
- Security updates check

**Monthly**:
- Disaster recovery drill
- Capacity planning review
- Performance regression analysis

### Backup & Recovery

```bash
# Weekly backup
poetry run python scripts/backup_neo4j.py \
  --environment production \
  --location s3://backups/ \
  --retention-days 30

# Test recovery
poetry run python scripts/test_neo4j_recovery.py \
  --environment staging \
  --backup-location s3://backups/latest
```

## Support & Escalation

### Contact Information

- **On-Call Engineer**: PagerDuty (production alerts)
- **Operations Team**: operations@example.com
- **Architecture Review**: architecture-review@example.com

### Issue Reporting

```bash
# Generate diagnostic bundle
poetry run python scripts/generate_diagnostics.py --environment production > diagnostics.tar.gz

# Report issue
curl -X POST https://issues.example.com/api/issues \
  -F "environment=production" \
  -F "severity=high" \
  -F "diagnostics=@diagnostics.tar.gz" \
  -F "description=Transition detection pipeline failure"
```

## Success Criteria

After deployment, verify:

✓ All transition detection assets materialized successfully  
✓ Transition nodes loaded into Neo4j (expected: 40K-80K)  
✓ Evidence bundles generated (100% of detections)  
✓ Analytics computed (award-level, company-level, by-CET)  
✓ Validation gates pass (vendor resolution ≥80%, success ≥99%)  
✓ Performance metrics meet targets (throughput ≥10K/min)  
✓ Data quality metrics acceptable (precision ≥85%)  
✓ Monitoring and alerting active  
✓ Documentation and runbooks available  

## References

- Transition Detection Algorithm: `docs/transition/detection_algorithm.md`
- Configuration Guide: `config/transition/README.md`
- Neo4j Schema: `docs/schemas/transition-graph-schema.md`
- Troubleshooting: `docs/transition/mvp.md#troubleshooting`
