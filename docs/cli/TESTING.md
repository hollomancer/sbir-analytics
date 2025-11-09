# CLI Testing Guide

This guide covers how to test the SBIR CLI implementation.

## Test Structure

Tests are organized in two main directories:

- `tests/unit/cli/` - Unit tests for CLI components
- `tests/integration/cli/` - Integration tests for end-to-end command execution

## Running Tests

### Run All CLI Tests

```bash

## Unit tests

poetry run pytest tests/unit/cli/ -v

## Integration tests

poetry run pytest tests/integration/cli/ -v

## All CLI tests with coverage

poetry run pytest tests/unit/cli/ tests/integration/cli/ --cov=src/cli --cov-report=html
```

### Run Specific Test Files

```bash

## Test integration clients

poetry run pytest tests/unit/cli/test_integration_clients.py -v

## Test commands

poetry run pytest tests/unit/cli/test_commands.py -v

## Test display components

poetry run pytest tests/unit/cli/test_display.py -v
```

### Quick Validation Script

For a quick sanity check of CLI installation:

```bash
poetry run python scripts/test_cli.py
```

This validates:

- All modules can be imported
- CommandContext can be created
- CLI app structure is correct
- Display components work

## Test Categories

### Unit Tests

#### Integration Clients (`test_integration_clients.py`)

Tests for `DagsterClient`, `Neo4jClient`, and `MetricsCollector`:

```bash
poetry run pytest tests/unit/cli/test_integration_clients.py::TestDagsterClient -v
poetry run pytest tests/unit/cli/test_integration_clients.py::TestNeo4jClient -v
poetry run pytest tests/unit/cli/test_integration_clients.py::TestMetricsCollector -v
```

### Mocking Strategy:

- DagsterClient: Mock `defs` and `DagsterInstance`
- Neo4jClient: Mock `GraphDatabase.driver` and session responses
- MetricsCollector: Mock file system and JSON loading

#### Commands (`test_commands.py`)

Tests for command logic (status, metrics, ingest, enrich):

```bash
poetry run pytest tests/unit/cli/test_commands.py::TestStatusCommands -v
poetry run pytest tests/unit/cli/test_commands.py::TestMetricsCommands -v
```

### Mocking Strategy:

- Mock `CommandContext` with all clients
- Mock client methods to return test data
- Verify command outputs using Typer's `CliRunner`

#### Display Components (`test_display.py`)

Tests for Rich UI components:

```bash
poetry run pytest tests/unit/cli/test_display.py::TestProgressTracker -v
poetry run pytest tests/unit/cli/test_display.py::TestMetricsDisplay -v
```

### Integration Tests

#### End-to-End Commands (`test_cli_integration.py`)

Tests using Typer's `CliRunner` with mocked services:

```bash
poetry run pytest tests/integration/cli/test_cli_integration.py -v
```

### Test Scenarios:

- CLI app help output
- Status commands with mocked clients
- Metrics commands with sample data
- Error handling and exit codes

## Manual Testing

### Quick Command Tests

```bash

## Help

poetry run sbir-cli --help

## Status commands

poetry run sbir-cli status summary
poetry run sbir-cli status assets
poetry run sbir-cli status neo4j --detailed

## Metrics commands

poetry run sbir-cli metrics latest
poetry run sbir-cli metrics show --limit 10

## Ingest commands

poetry run sbir-cli ingest run --dry-run
poetry run sbir-cli ingest run --groups sbir_ingestion --dry-run

## Enrich commands

poetry run sbir-cli enrich stats
```

### With Real Services (Advanced)

For testing with actual Dagster and Neo4j instances:

1. Start services:

```bash

## Terminal 1: Start Dagster

poetry run dagster dev -m src.definitions

## Terminal 2: Start Neo4j (if using Docker)

docker compose up neo4j
```

2. Run commands:

```bash

## Test with real services

poetry run sbir-cli status summary
poetry run sbir-cli status neo4j --detailed
```

## Writing New Tests

### Example: Testing a New Command

```python
from unittest.mock import Mock
import typer
from typer.testing import CliRunner

def test_new_command():
    """Test a new CLI command."""
    # Setup
    mock_context = Mock()
    mock_context.client.method.return_value = {"data": "test"}

    # Create command context
    ctx = typer.Context(
        command=Mock(),
        params={},
        info_name="new-command",
        obj=mock_context,
    )

    # Test command logic
    # ...
```

### Example: Testing Display Component

```python
from unittest.mock import Mock
from src.cli.display.metrics import create_metrics_table

def test_metrics_table():
    """Test metrics table creation."""
    console = Mock()
    metrics = [
        {
            "timestamp": "2024-01-01T00:00:00",
            "asset_key": "test",
            "duration_seconds": 10.0,
            "records_processed": 100,
            "success": True,
        }
    ]

    table = create_metrics_table(metrics, console)

    assert table is not None
    assert len(table.columns) > 0
```

## Coverage Goals

Target coverage for CLI components:

- **Integration Clients**: ≥85% coverage
- **Commands**: ≥80% coverage (mocking external dependencies)
- **Display Components**: ≥80% coverage
- **Error Handling**: Test all error paths

## Continuous Integration

CLI tests are included in CI:

```bash

## Run in CI environment

poetry run pytest tests/unit/cli/ tests/integration/cli/ \

  --cov=src/cli \
  --cov-report=xml \
  --cov-report=term-missing
```

## Troubleshooting

### Import Errors

```bash

## Ensure dependencies installed

poetry install

## Verify Rich is available

poetry run python -c "import rich; print('OK')"
```

### Mock Issues

If mocks aren't working:

- Check import paths match actual module paths
- Verify mock patches target the correct modules
- Use `patch.object` for instance methods

### Typer CliRunner Issues

If `CliRunner` tests fail:

- Ensure `ctx.obj` is set (CommandContext)
- Verify command registration in `main.py`
- Check for import errors in command modules
