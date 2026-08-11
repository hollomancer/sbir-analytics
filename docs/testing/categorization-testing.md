# Categorization Testing

**Type**: Testing Guide

**Maintainer**: Conrad Hollomon

**Last-Reviewed**: 2026-08-03

**Status**: Active

Company categorization is tested at three automated layers, with a separate operator CLI for
dataset-scale validation.

## Automated tests

### Unit behavior

`tests/unit/transformers/test_company_categorization.py` covers classification rules and
transformer behavior in isolation:

```bash
uv run pytest tests/unit/transformers/test_company_categorization.py -v
```

### Client integration

`tests/integration/test_company_categorization_client_injection.py` verifies categorization with
injected contract clients:

```bash
uv run pytest tests/integration/test_company_categorization_client_injection.py -v
```

### Quick validation

`tests/validation/test_categorization_quick.py` provides a small validation smoke test:

```bash
uv run pytest tests/validation/test_categorization_quick.py -v
```

Run all categorization-related automated tests with:

```bash
uv run pytest \
  tests/unit/transformers/test_company_categorization.py \
  tests/integration/test_company_categorization_client_injection.py \
  tests/validation/test_categorization_quick.py -v
```

## Dataset-scale validation

Use `scripts/validation/categorization_validation.py` when evaluating real company inputs,
contract retrieval, report quality, or Neo4j loading. It is a CLI, not a test file:

```bash
uv run python scripts/validation/categorization_validation.py \
  --dataset companies.csv --limit 10 --detailed
```

The command is DuckDB-first with USAspending API fallback by default. `--use-api` disables DuckDB.
For output, loading, and concurrency options, see
[Company Categorization Validation](validation-testing.md).

## Adding coverage

- Put deterministic classification examples in the unit module.
- Put contract-client boundaries in the integration module and inject fakes instead of calling a
  public API during normal tests.
- Use the validation layer for compact representative datasets and invariant checks.
- Keep large or exploratory datasets out of the pytest suite; exercise them through the CLI and
  record evidence under `reports/` when appropriate.

Do not use SBIR/STTR award revenue as an input to the contract-based categorization decision. The
validation CLI reports those awards for context only.
