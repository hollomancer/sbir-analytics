# Logging Standards

**Type**: Reference
**Owner**: Engineering Team
**Last-Updated**: 2025-11-05
**Status**: Active

## Overview

The SBIR ETL pipeline uses **loguru** for structured, consistent logging across all components. This guide defines when to use logging vs console output, how to add structured context, and best practices for production observability.

## Table of Contents

- [Quick Reference](#quick-reference)
- [When to Use Logger vs Console](#when-to-use-logger-vs-console)
- [Structured Logging](#structured-logging)
- [Log Levels](#log-levels)
- [Context Variables](#context-variables)
- [CLI Logging](#cli-logging)
- [Performance Considerations](#performance-considerations)
- [Examples](#examples)

---

## Quick Reference

### ✅ Use `logger` for

- Internal application logic and data processing
- Debugging information for developers
- Error tracking and monitoring
- Performance metrics
- Structured data that needs to be parsed
- Production monitoring and alerting

### ✅ Use `console.print()` for

- User-facing CLI output
- Progress bars and status updates
- Formatted tables and panels (Rich console)
- Interactive prompts and responses
- Final command results

### ❌ Never use

- `print()` for application logic (only in CLI utilities writing to stdout)
- `print()` in library code or Dagster assets
- `logging` stdlib (use `loguru` instead)

---

## When to Use Logger vs Console

### Logger (Internal/Production)

**Use `logger` when:**

- Writing diagnostic information for developers
- Tracking application state and data flow
- Recording errors for monitoring systems
- Capturing structured data (JSON logs)
- Building audit trails

```python
from loguru import logger

# Good - Internal diagnostic logging
logger.info("Processing SBIR awards", extra={"count": 1000, "source": "csv"})
logger.warning("Low match rate detected", extra={"rate": 0.45, "threshold": 0.70})
logger.error("Database connection failed", extra={"uri": db_uri, "attempt": 3})
```

### Console (User-Facing Output)

**Use `context.console.print()` in CLI commands when:**

- Showing results to users
- Displaying progress and status
- Formatting tables or panels
- Providing interactive feedback

```python
from rich.panel import Panel

# Good - User-facing output
context.console.print("[green]✓[/green] Ingestion completed successfully")
context.console.print(f"Processed {count:,} records in {duration}s")
context.console.print(table)  # Rich Table
context.console.print(Panel("Success!", border_style="green"))
```

### Decision Tree

```
Is this for a user running a CLI command?
├─ YES → Use context.console.print()
└─ NO  → Is this internal application logic?
          ├─ YES → Use logger
          └─ NO  → Is this a standalone CLI utility script?
                   ├─ YES → Use print(..., file=out)  # stdout
                   └─ NO  → Use logger
```

---

## Structured Logging

### Basic Usage

```python
from loguru import logger

# Simple message
logger.info("Starting data extraction")

# With structured context (preferred)
logger.info(
    "Starting data extraction",
    extra={
        "source": "sbir_awards.csv",
        "record_count": 50000,
        "batch_size": 1000
    }
)
```

### Context Binding

Bind context variables that persist across multiple log calls:

```python
from loguru import logger

# Bind context for entire module/function
context_logger = logger.bind(
    component="enrichment",
    stage="usaspending_api",
    run_id="abc123"
)

context_logger.info("Starting enrichment")  # Includes component, stage, run_id
context_logger.info("Processing batch", extra={"batch": 1, "size": 100})
```

### Using log_with_context

For operations with a clear beginning and end:

```python
from src.utils import log_with_context

with log_with_context(stage="extraction", run_id="xyz789") as logger:
    logger.info("Extracting data from source")
    # All logs within this block include stage and run_id
    logger.info("Extraction complete", extra={"records": 1000})
```

---

## Log Levels

### Level Guidelines

| Level | When to Use | Examples |
|-------|-------------|----------|
| **DEBUG** | Development debugging, verbose details | Variable values, loop iterations, detailed state |
| **INFO** | Normal operations, key milestones | Pipeline stages starting/completing, record counts |
| **WARNING** | Unexpected but recoverable conditions | Low match rates, retries, degraded performance |
| **ERROR** | Errors requiring attention | Failed API calls, validation failures, data quality issues |
| **CRITICAL** | System failures, data corruption | Database unavailable, configuration errors, data loss |

### Examples

```python
# DEBUG - Detailed debugging information
logger.debug("Fetching record", extra={"id": award_id, "index": i})

# INFO - Key operational milestones
logger.info("Validation complete", extra={"passed": 9500, "failed": 500})

# WARNING - Recoverable issues
logger.warning(
    "Match rate below threshold",
    extra={"actual": 0.65, "threshold": 0.70, "action": "continuing"}
)

# ERROR - Failures requiring attention
logger.error(
    "API request failed",
    extra={"endpoint": "/awards", "status_code": 500, "retry_count": 3}
)

# CRITICAL - System-level failures
logger.critical(
    "Database connection lost",
    extra={"uri": db_uri, "error": str(e), "action": "aborting_pipeline"}
)
```

---

## Context Variables

### Standard Context Keys

Use these standard keys for consistency:

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `component` | str | System component | `"enrichment"`, `"cli"`, `"loader"` |
| `stage` | str | Pipeline stage | `"extraction"`, `"validation"`, `"loading"` |
| `run_id` | str | Unique run identifier | `"abc12345"` |
| `operation` | str | Specific operation | `"api_call"`, `"database_query"` |
| `count` | int | Record/item count | `1000` |
| `duration` | float | Time in seconds | `12.5` |
| `error` | str | Error message | `"Connection timeout"` |
| `status` | str | Operation status | `"success"`, `"failed"`, `"retrying"` |

### Custom Context

Add domain-specific context as needed:

```python
logger.info(
    "Transition detection complete",
    extra={
        "component": "transition",
        "stage": "scoring",
        "run_id": run_id,
        # Domain-specific
        "awards_processed": 50000,
        "transitions_detected": 12000,
        "high_confidence_count": 8000,
        "detection_rate": 0.24,
        "avg_score": 0.73,
    }
)
```

---

## CLI Logging

### CommandContext Integration

The `CommandContext` automatically sets up structured logging:

```python
from src.cli.context import CommandContext

# Context includes logger with bound context
context = CommandContext.create()

# All operations include run_id, component="cli", environment
context.logger.info("Starting command", extra={"command_name": "ingest"})
```

### CLI Command Pattern

```python
import typer
from ..context import CommandContext

@app.command()
def my_command(ctx: typer.Context) -> None:
    """Example CLI command with logging."""
    context: CommandContext = ctx.obj

    # Log internal operations
    context.logger.info("Command started", extra={"command": "my_command"})

    try:
        # Do work
        result = process_data()

        # Log success
        context.logger.info(
            "Command completed successfully",
            extra={"records_processed": result.count, "duration": result.duration}
        )

        # Show user-facing output
        context.console.print(f"[green]✓[/green] Processed {result.count:,} records")

    except Exception as e:
        # Log error with context
        context.logger.error(
            "Command failed",
            extra={"command": "my_command", "error": str(e)},
            exception=e
        )

        # Show user-friendly error
        context.console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
```

---

## Performance Considerations

### Lazy Evaluation

Loguru automatically handles lazy evaluation, but you can optimize expensive operations:

```python
# Avoid expensive operations if debug is disabled
if logger.level("DEBUG").no >= logger.level():
    logger.debug("Detailed state", extra=expensive_computation())

# Better: Use lambdas for automatic lazy evaluation
logger.opt(lazy=True).debug(
    "Detailed state: {state}",
    state=lambda: expensive_computation()
)
```

### Sampling High-Volume Logs

For very high-volume operations, sample logs:

```python
# Log every 1000th record
if record_index % 1000 == 0:
    logger.debug(
        "Processing checkpoint",
        extra={"index": record_index, "total": total_records}
    )
```

### Async Logging

Loguru supports async logging for better performance:

```python
# In logging configuration (config/base.yaml or setup)
logger.add(
    "logs/app.log",
    enqueue=True,  # Async logging
    rotation="500 MB"
)
```

---

## Examples

### Example 1: Data Pipeline Asset

```python
from loguru import logger
from dagster import asset

@asset
def enriched_awards(context, raw_awards):
    """Enrich awards with external data."""
    # Bind context for all logs in this asset
    asset_logger = logger.bind(
        component="enrichment",
        asset="enriched_awards",
        run_id=context.run_id
    )

    asset_logger.info("Starting enrichment", extra={"input_count": len(raw_awards)})

    enriched = []
    errors = []

    for i, award in enumerate(raw_awards):
        try:
            result = enrich_award(award)
            enriched.append(result)

            # Log progress periodically
            if (i + 1) % 1000 == 0:
                asset_logger.info(
                    "Enrichment progress",
                    extra={"processed": i + 1, "total": len(raw_awards)}
                )
        except Exception as e:
            asset_logger.warning(
                "Enrichment failed for award",
                extra={"award_id": award.id, "error": str(e)}
            )
            errors.append({"award_id": award.id, "error": str(e)})

    # Log final results
    asset_logger.info(
        "Enrichment complete",
        extra={
            "input_count": len(raw_awards),
            "enriched_count": len(enriched),
            "error_count": len(errors),
            "success_rate": len(enriched) / len(raw_awards)
        }
    )

    return enriched
```

### Example 2: Error Handling with Context

```python
from src.exceptions import EnrichmentError, APIError
from src.utils import log_with_context

def enrich_from_api(awards, api_client):
    """Enrich awards using external API."""
    with log_with_context(stage="api_enrichment", run_id=generate_run_id()) as logger:
        logger.info("Starting API enrichment", extra={"award_count": len(awards)})

        enriched = []
        for award in awards:
            try:
                data = api_client.get_award_data(award.id)
                enriched.append({**award.dict(), **data})

            except APIError as e:
                logger.warning(
                    "API call failed",
                    extra={
                        "award_id": award.id,
                        "api": api_client.name,
                        "status_code": e.status_code,
                        "retryable": e.retryable
                    }
                )
                if e.retryable:
                    # Retry logic...
                    pass
                else:
                    raise
            except Exception as e:
                logger.error(
                    "Unexpected enrichment error",
                    extra={"award_id": award.id, "error_type": type(e).__name__},
                    exception=e
                )
                raise EnrichmentError(
                    message=f"Failed to enrich award {award.id}",
                    component="api_enrichment",
                    operation="get_award_data",
                    details={"award_id": award.id},
                ) from e

        logger.info(
            "API enrichment complete",
            extra={"enriched_count": len(enriched), "input_count": len(awards)}
        )

        return enriched
```

### Example 3: CLI Utility Script

```python
#!/usr/bin/env python3
"""Standalone CLI utility for data export."""

import argparse
import sys

from loguru import logger

def export_data(input_file, output_file):
    """Export data with logging."""
    logger.info("Starting export", extra={"input": str(input_file)})

    try:
        # Process data
        data = load_data(input_file)
        logger.info("Data loaded", extra={"record_count": len(data)})

        # Write output (user sees this)
        write_data(output_file, data)
        print(f"✓ Exported {len(data):,} records to {output_file}")  # stdout

        logger.info("Export complete", extra={"output": str(output_file)})

    except Exception as e:
        logger.error("Export failed", extra={"error": str(e)}, exception=e)
        print(f"Error: {e}", file=sys.stderr)  # stderr
        sys.exit(1)

if __name__ == "__main__":
    # Configure loguru for this script
    logger.add(sys.stderr, level="INFO", format="{time} {level} {message}")

    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    export_data(args.input, args.output)
```

---

## Configuration

### Default Configuration (config/base.yaml)

```yaml
logging:
  level: "INFO"
  format: "json"  # or "pretty" for development
  file_path: "logs/sbir-analytics.log"
  max_file_size_mb: 100
  backup_count: 5
  include_stage: true
  include_run_id: true
  include_timestamps: true
```

### Programmatic Configuration

```python
from src.utils.logging_config import setup_logging

# Set up logging with configuration
setup_logging(
    level="INFO",
    format_type="json",
    file_path="logs/app.log",
    include_stage=True,
    include_run_id=True
)
```

---

## Migration Guide

If you have existing code using `print()` or stdlib `logging`:

### Migrating from print()

```python
# OLD
print(f"Processing {count} records")

# NEW (internal logic)
logger.info("Processing records", extra={"count": count})

# NEW (CLI user output)
context.console.print(f"Processing {count:,} records...")
```

### Migrating from stdlib logging

```python
# OLD
import logging
logging.info("Message")

# NEW
from loguru import logger
logger.info("Message")
```

### Migrating mock logging (test shims)

```python
# OLD
class MockLogger:
    def info(self, *a, **kw):
        print(*a)

# NEW
from loguru import logger as _logger

class MockLogger:
    def info(self, *a, **kw):
        _logger.info(*a, **kw)
```

---

## Related Documentation

- [Exception Handling Guide](exception-handling.md)
- [Configuration Overview](../configuration/paths.md)
- [CLI Reference](../cli/README.md)

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-05 | 1.0 | Initial logging standards documentation |
