# Company Categorization Validation

**Type**: Operator Guide

**Owner**: Engineering Team

**Last-Reviewed**: 2026-08-03

**Status**: Active

`scripts/validation/categorization_validation.py` is an operator-facing validation CLI for running
contract-based company categorization over a company CSV. It is not a pytest test module.

## Setup

```bash
make install
```

By default the command looks for the validation dataset named in `--help`, retrieves contracts from
the configured DuckDB database, and falls back to the USAspending API when local data is unavailable.
Use `--dataset` for an explicit input and verify any API credentials before a large run.

## Common runs

Start with a small sample:

```bash
uv run python scripts/validation/categorization_validation.py --dataset companies.csv --limit 10
```

Run the entire input and save both machine-readable and narrative output:

```bash
uv run python scripts/validation/categorization_validation.py \
  --dataset companies.csv \
  --output reports/categorization-results.csv \
  --markdown-report reports/categorization-validation.md
```

Inspect one company or request detailed contract justifications:

```bash
uv run python scripts/validation/categorization_validation.py --dataset companies.csv --uei UEI_VALUE
uv run python scripts/validation/categorization_validation.py --dataset companies.csv --detailed
```

Force API retrieval and use bounded concurrency:

```bash
uv run python scripts/validation/categorization_validation.py \
  --dataset companies.csv --use-api --max-workers 3
```

`--use-api` disables DuckDB rather than merely preferring the API. Respect USAspending rate limits;
the CLI recommends three to five workers at most.

## Options

| Option | Purpose |
| --- | --- |
| `--dataset`, `-d`, `--csv` | Input company CSV |
| `--limit N` | Process at most `N` companies |
| `--uei VALUE` | Process one UEI |
| `--output PATH` | Write result rows as CSV |
| `--markdown-report PATH` | Write a detailed Markdown report |
| `--detailed` | Print contract-level justifications |
| `--use-api` | Disable DuckDB and retrieve from USAspending API only |
| `--max-workers N` | Parallel API workers; defaults to one |
| `--load-neo4j` | Load completed categorizations into Neo4j |
| `--verbose` | Enable debug logging |

Run `uv run python scripts/validation/categorization_validation.py --help` for the authoritative
option list.

## Neo4j loading

`--load-neo4j` is write-producing and requires a reachable Neo4j instance and valid credentials.
Do not point an exploratory validation run at the live database. Before any live operation, use the
[self-hosted server runbook](../deployment/self-hosted-server.md#live-instance-on-the-server-host).

## Automated coverage

The categorization implementation is covered separately by:

```bash
uv run pytest tests/unit/transformers/test_company_categorization.py -v
uv run pytest tests/integration/test_company_categorization_client_injection.py -v
uv run pytest tests/validation/test_categorization_quick.py -v
```

See [Categorization Testing](categorization-testing.md) for the intent of each layer.
