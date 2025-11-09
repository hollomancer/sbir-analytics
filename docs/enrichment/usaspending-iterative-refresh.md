# USAspending Iterative Enrichment Refresh

## Overview

The USAspending iterative enrichment system automatically refreshes enrichment data for SBIR awards on a configurable cadence, tracking freshness metadata and detecting changes via payload hashing. This ensures that enrichment data stays current without requiring full pipeline re-runs.

**Phase 1: USAspending API only.** Other APIs (SAM.gov, NIH RePORTER, PatentsView, etc.) will be evaluated in Phase 2+.

## Architecture

### Components

1. **USAspending API Client** (`src/enrichers/usaspending_api_client.py`)
   - Async HTTP client with rate limiting and retry logic
   - Delta detection via payload hashing
   - State management for cursors/ETags

2. **Freshness Store** (`src/utils/enrichment_freshness.py`)
   - Persists enrichment freshness records to Parquet
   - Tracks `last_attempt_at`, `last_success_at`, `payload_hash`, and `status` per award/source
   - Identifies stale records based on SLA thresholds

3. **Checkpoint Store** (`src/utils/enrichment_checkpoints.py`)
   - Enables resume functionality for interrupted refresh runs
   - Tracks partition progress and last processed award ID

4. **Metrics Collector** (`src/utils/enrichment_metrics.py`)
   - Emits freshness coverage metrics
   - Tracks success rates, error rates, and SLA compliance
   - Logs to `reports/metrics/enrichment_freshness.json`

5. **Dagster Assets** (`src/assets/usaspending_iterative_enrichment.py`)
   - `usaspending_freshness_ledger`: Tracks all freshness records
   - `stale_usaspending_awards`: Identifies awards needing refresh
   - `usaspending_refresh_batch`: Performs refresh operations

6. **Dagster Sensor** (`src/assets/sensors/usaspending_refresh_sensor.py`)
   - Triggers refresh job after bulk enrichment completes
   - Checks for stale awards before triggering

## Configuration

Configuration is defined in `config/base.yaml` under `enrichment_refresh.usaspending`:

```yaml
enrichment_refresh:
  usaspending:
    cadence_days: 1  # Daily refresh
    sla_staleness_days: 1  # Max 24 hours old before considered stale
    batch_size: 100  # Awards per batch
    max_concurrent_requests: 5
    rate_limit_per_minute: 120
    enable_delta_detection: true
    hash_algorithm: "sha256"
    retry_attempts: 3
    retry_backoff_seconds: 2.0
    retry_backoff_multiplier: 2.0
    timeout_seconds: 30
    connection_timeout_seconds: 10
    checkpoint_interval: 50
    state_file: "data/state/enrichment_refresh_state.json"
    enable_metrics: true
    metrics_file: "reports/metrics/enrichment_freshness.json"
```

## Workflow

### Automatic Refresh (Sensor-Driven)

1. Bulk enrichment completes (`enriched_sbir_awards` asset materialized)
2. Sensor checks freshness ledger for stale awards
3. If stale awards found, triggers `usaspending_iterative_enrichment_job`
4. Job processes awards in batches:
   - Loads stale awards
   - For each award:
     - Checks existing freshness record for delta detection
     - Calls USAspending API if delta detected or no record exists
     - Updates freshness ledger with result
     - Records API calls for metrics
5. Emits freshness metrics

### Manual Refresh (CLI)

Use the `refresh_enrichment.py` script for ad-hoc refreshes:

```bash

## Refresh specific awards

python scripts/refresh_enrichment.py refresh-usaspending --award-ids "AWARD-001,AWARD-002"

## Refresh all stale awards

python scripts/refresh_enrichment.py refresh-usaspending --stale-only

## Refresh awards from 2023

python scripts/refresh_enrichment.py refresh-usaspending --cohort 2023

## Force refresh (ignores staleness)

python scripts/refresh_enrichment.py refresh-usaspending --cohort 2023 --force

## List stale awards

python scripts/refresh_enrichment.py list-stale --source usaspending

## View freshness statistics

python scripts/refresh_enrichment.py stats --source usaspending
```

### Backfilling Freshness Records

For existing enriched awards, run the backfill script:

```bash
python scripts/backfill_enrichment_freshness.py
```

This creates freshness records for awards that were enriched before the iterative refresh system was implemented.

## Credentials and Setup

### USAspending API

The USAspending API is public and does not require authentication. However, rate limits apply:

- **Rate Limit**: 120 requests per minute (configurable)
- **Base URL**: `https://api.usaspending.gov/api/v2` (configured in `config/base.yaml`)

### Environment Variables

No special environment variables are required for USAspending. The API is accessed via public endpoints.

## Delta Detection

Delta detection prevents unnecessary API calls and updates by comparing payload hashes:

1. When enriching an award, the API response payload is hashed using SHA-256
2. The hash is compared against the stored hash in the freshness record
3. If hashes match, no update is needed (status: `unchanged`)
4. If hashes differ, the enrichment is updated (status: `success`, `delta_detected: true`)

This allows the system to:

- Skip API calls for unchanged data (when `enable_delta_detection: true`)
- Track which awards have actually changed
- Reduce API load and processing time

## Freshness Metrics

Metrics are emitted to `reports/metrics/enrichment_freshness.json` after each refresh run:

```json
{
  "sources": {
    "usaspending": {
      "source": "usaspending",
      "timestamp": "2024-01-20T10:00:00",
      "sla_days": 1,
      "records": {
        "total": 1000,
        "within_sla": 950,
        "stale": 50
      },
      "enrichments": {
        "attempts": 50,
        "success": 48,
        "failed": 2,
        "unchanged": 0
      },
      "api": {
        "calls": 48,
        "errors": 2
      },
      "rates": {
        "coverage_rate": 0.95,
        "success_rate": 0.96,
        "staleness_rate": 0.05,
        "error_rate": 0.04,
        "unchanged_rate": 0.0
      }
    }
  },
  "last_updated": "2024-01-20T10:05:00"
}
```

### Key Metrics

- **Coverage Rate**: % of records within SLA threshold
- **Success Rate**: % of enrichment attempts that succeeded
- **Staleness Rate**: % of records that are stale
- **Error Rate**: % of API calls that resulted in errors
- **Unchanged Rate**: % of attempts where data was unchanged (delta detection)

## Troubleshooting

### No Awards Are Being Refreshed

1. **Check freshness ledger**:

   ```bash
   python scripts/refresh_enrichment.py list-stale --source usaspending
   ```

2. **Verify SLA threshold**: Awards must be older than `sla_staleness_days` to be considered stale

3. **Check sensor status**: Ensure the sensor is enabled and triggering jobs

4. **Verify bulk enrichment completed**: Sensor only triggers after `enriched_sbir_awards` is materialized

### High Error Rate

1. **Check API status**: USAspending API may be experiencing issues
   - Status page: https://www.usaspending.gov/status

2. **Review rate limiting**: If hitting rate limits, reduce `max_concurrent_requests` or increase `rate_limit_per_minute` (if API allows)

3. **Check network connectivity**: Verify outbound HTTP connections to `api.usaspending.gov`

4. **Review error logs**: Check Dagster run logs for specific error messages

### Metrics Not Being Emitted

1. **Verify metrics file path**: Check `enrichment_refresh.usaspending.metrics_file` in config

2. **Check file permissions**: Ensure write permissions to metrics directory

3. **Review Dagster logs**: Look for warnings about metrics emission failures

### Delta Detection Not Working

1. **Verify delta detection enabled**: Check `enable_delta_detection: true` in config

2. **Check hash algorithm**: Ensure `hash_algorithm` matches what was used for existing records

3. **Verify payload structure**: API response structure changes may affect hash computation

### Resume Functionality Not Working

1. **Check checkpoint interval**: Ensure `checkpoint_interval` is set appropriately (every N records)

2. **Verify checkpoint file exists**: Check `data/state/enrichment_checkpoints.parquet`

3. **Review partition ID**: Ensure same partition ID is used when resuming

## Monitoring

### Key Indicators

- **Freshness Coverage**: Should be >85% within SLA
- **Success Rate**: Should be >90%
- **Error Rate**: Should be <10%
- **Staleness Rate**: Should be <15%

### Alerts

Consider setting up alerts for:

- Freshness coverage drops below threshold
- Success rate drops below threshold
- Error rate exceeds threshold
- No refresh runs in expected timeframe

## Future Enhancements (Phase 2+)

- Multi-source enrichment refresh (SAM.gov, NIH RePORTER, PatentsView, etc.)
- Generic multi-source orchestrator
- More sophisticated delta detection (field-level changes)
- Incremental refresh strategies (date-based partitions)
- Webhook notifications for enrichment updates
- Dashboard for freshness visualization

## References

- USAspending API Documentation: https://api.usaspending.gov/docs
- Dagster Documentation: https://docs.dagster.io
- Configuration: `config/base.yaml`
- Source Code: `src/assets/usaspending_iterative_enrichment.py`
