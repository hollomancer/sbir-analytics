# SBIR CLI Reference Guide

The SBIR CLI provides a comprehensive command-line interface for monitoring and operating the SBIR analytics pipeline using Rich terminal UI.

## Installation

The CLI is installed automatically with the project:

```bash
poetry install
```

The `sbir-cli` command will be available after installation.

## Quick Start

```bash

## Show all available commands

sbir-cli --help

## Check pipeline status

sbir-cli status summary

## View asset status

sbir-cli status assets

## Check Neo4j health

sbir-cli status neo4j --detailed

## View latest metrics

sbir-cli metrics latest

## Start interactive dashboard

sbir-cli dashboard start
```

## Commands

### Status Commands

#### `status summary`

Display a summary of pipeline status including asset counts and Neo4j connectivity.

```bash
sbir-cli status summary
```

#### `status assets`

Display materialization status for all assets.

```bash

## Show all assets

sbir-cli status assets

## Filter by asset group

sbir-cli status assets --group sbir_ingestion
```

###`status neo4j`

Check Neo4j connection health and display database statistics.

```bash

## Basic health check

sbir-cli status neo4j

## Detailed statistics

sbir-cli status neo4j --detailed
```

### Metrics Commands

#### `metrics show`

Display performance metrics with optional filtering.

```bash

## Show recent metrics (default: last 20)

sbir-cli metrics show

## Filter by date range

sbir-cli metrics show --start-date 2024-01-01 --end-date 2024-12-31

## Filter by asset group

sbir-cli metrics show --group enrichment

## Limit results

sbir-cli metrics show --limit 50
```

###`metrics latest`

Display latest aggregated pipeline metrics.

```bash
sbir-cli metrics latest
```

###`metrics export`

Export metrics to JSON or CSV.

```bash

## Export to JSON

sbir-cli metrics export --format json --output metrics.json

## Export to CSV

sbir-cli metrics export --format csv --output metrics.csv

## Export with date filter

sbir-cli metrics export --start-date 2024-01-01 --format json --output jan_metrics.json
```

### Ingest Commands

#### `ingest run`

Trigger data ingestion operations.

```bash

## Dry run (preview)

sbir-cli ingest run --dry-run

## Materialize specific asset groups

sbir-cli ingest run --groups sbir_ingestion,usaspending_ingestion

## Force refresh (skip cache)

sbir-cli ingest run --groups sbir_ingestion --force
```

###`ingest status`

Check status of ingestion runs.

```bash

## Check specific run

sbir-cli ingest status --run-id <run_id>
```

### Enrich Commands

#### `enrich run`

Execute enrichment workflows.

```bash

## Enrich with all sources

sbir-cli enrich run

## Enrich with specific sources

sbir-cli enrich run --sources sam_gov,usaspending

## Set batch size

sbir-cli enrich run --sources usaspending --batch-size 1000

## Set confidence threshold

sbir-cli enrich run --sources sam_gov --confidence 0.8
```

###`enrich stats`

Display enrichment statistics and success rates.

```bash

## All sources

sbir-cli enrich stats

## Specific source

sbir-cli enrich stats --source sam_gov
```

### Dashboard

#### `dashboard start`

Start interactive real-time monitoring dashboard.

```bash

## Start with default 10-second refresh

sbir-cli dashboard start

## Custom refresh interval

sbir-cli dashboard start --refresh 5
```

The dashboard provides:

- Real-time asset status updates
- Performance metrics panel
- Neo4j health monitoring
- System information

Press `Ctrl+C` to exit the dashboard.

## Configuration

CLI settings can be configured in `config/base.yaml`:

```yaml
cli:
  theme: "default"  # "default", "dark", "light"
  progress_refresh_rate: 0.1  # seconds
  dashboard_refresh_rate: 10  # seconds
  max_table_rows: 50
  truncate_long_text: true
  show_timestamps: true
  api_timeout_seconds: 30
  max_concurrent_operations: 4
  cache_metrics_seconds: 60
```

Or via environment variables:

```bash
export SBIR_ETL__CLI__THEME=dark
export SBIR_ETL__CLI__DASHBOARD_REFRESH_RATE=5
```

## Exit Codes

- `0` - Success
- `1` - General error
- `2` - Configuration error

## Troubleshooting

### CLI Command Not Found

```bash

## Reinstall package to register entry point

poetry install

## Or run directly

poetry run python -m src.cli.main
```

### Import Errors

```bash

## Ensure dependencies are installed

poetry install

## Check Rich is available

poetry run python -c "import rich; print('OK')"
```

### Dagster Connection Issues

- Verify Dagster is running: `poetry run dagster dev`
- Check Dagster port (default: 3000)
- Verify workspace configuration in `workspace.yaml`

### Neo4j Connection Issues

- Verify Neo4j is running: `docker compose ps neo4j`
- Check connection settings in `config/base.yaml`
- Verify credentials in `.env` file

## Examples

### Monitor Pipeline During Execution

```bash

## Terminal 1: Start dashboard

sbir-cli dashboard start

## Terminal 2: Trigger ingestion

sbir-cli ingest run --groups sbir_ingestion
```

### Export Metrics for Analysis

```bash

## Export last 30 days

sbir-cli metrics export \

  --start-date $(date -v-30d +%Y-%m-%d) \
  --format json \
  --output metrics_30days.json
```

### Check Status Before Running Operations

```bash

## Quick status check

sbir-cli status summary

## Detailed asset status

sbir-cli status assets --group enrichment

## Neo4j health

sbir-cli status neo4j --detailed
```

## Advanced Usage

### Verbose Logging

Enable detailed logging with the `--verbose` flag:

```bash
sbir-cli --verbose status assets
```

### Scripting Integration

The CLI uses standard exit codes for scripting:

```bash
#!/bin/bash
if sbir-cli status summary; then
    echo "Pipeline is healthy"
    sbir-cli ingest run --groups sbir_ingestion
else
    echo "Pipeline has issues - check status"
    exit 1
fi
```

## Testing

See [CLI Testing Guide](TESTING.md) for comprehensive testing instructions.

Quick test:

```bash

## Validation script

poetry run python scripts/test_cli.py

## Unit tests

poetry run pytest tests/unit/cli/ -v

## Integration tests

poetry run pytest tests/integration/cli/ -v
```

## See Also

- Main project README: `README.md`
- Configuration reference: `config/base.yaml`
- Dagster documentation: `QUICK_START.md`
- CLI Testing Guide: `docs/cli/TESTING.md`

