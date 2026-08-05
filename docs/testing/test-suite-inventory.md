# Integration, End-to-End, and Validation Test Inventory

**Type**: Reference

**Owner**: Engineering Team

**Last-Reviewed**: 2026-08-03

**Status**: Active

This inventory describes the test boundaries without hard-coding test counts, which change too
frequently to be a reliable contract. Use pytest collection for the current executable inventory.

## Current inventory

```bash
uv run pytest --collect-only tests/integration/ tests/e2e/ tests/validation/ -q
```

The directories have distinct purposes:

| Directory | Purpose | Normal execution |
| --- | --- | --- |
| `tests/integration/` | Interactions among current components or a declared service | Full CI on `main`; focused local runs |
| `tests/e2e/` | Pipeline scenarios spanning major boundaries, often with Neo4j | Full CI on `main`; Docker E2E locally |
| `tests/validation/` | Numerical/reference checks and small operator validation programs | Full CI where collectable; explicit local runs |

Pull-request CI currently runs fast unit-test shards, not these entire directories. See
[Test Execution and Scheduling](test-scheduling.md) for the event matrix.

## Prerequisite classes

| Class | Rule |
| --- | --- |
| Fixture-based | Deterministic local fixtures; no live external API or restricted dataset |
| Service-backed | Declares its Neo4j or other service prerequisite and skips clearly when unavailable |
| External API | Marked `requires_api`; not executed by normal CI |
| Real-data validation | Explicitly skipped unless approved reference data is mounted |
| Operator program | May live under `tests/validation/` but is not necessarily a collectable pytest suite |

`tests/validation/test_categorization_quick.py` and
`tests/validation/test_patentsview_enrichment.py` are operator programs rather than ordinary pytest
suites. Run them explicitly as scripts when their prerequisites are available.

## Important suites

- `tests/integration/neo4j/` and `tests/integration/test_neo4j_client.py` exercise graph service
  behavior.
- `tests/integration/test_company_categorization_client_injection.py` covers categorization client
  boundaries.
- `tests/integration/test_patent_etl_integration.py` covers the patent ETL chain with fixtures.
- `tests/e2e/test_pipeline_validator.py` covers shared pipeline validation models and behavior.
- `tests/e2e/transition/` covers transition assets, quality metrics, detection, and graph queries.
- `tests/validation/test_fiscal_reference_validation.py` contains local numerical checks plus
  reference-data cases that may skip when their external prerequisites are absent.

This list is navigational, not exhaustive; collection is authoritative.

## Suite integrity

Static integrity checks reject concrete `Test*` classes containing only `pass` and pytest modules
with no executable tests where a suite is expected:

```bash
uv run pytest tests/unit/test_test_suite_integrity.py -v
```

When adding a skipped test, state the unavailable prerequisite and the command or environment that
can execute it. A skip is not a substitute for a removed implementation or an obsolete dependency.

## CI relationship

On pushes to `main` and manual runs, `.github/workflows/ci.yml` starts Neo4j and runs the complete
`tests/` tree except `requires_api` cases and the named known-failure deselections recorded directly
in the workflow. GitHub Actions does not mount production data and does not run live pipeline work.
