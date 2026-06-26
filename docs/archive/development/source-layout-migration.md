# Source-layout migration inventory

The former `src/` source root has been replaced by four production source roots:

- `sbir_etl/`
- `packages/sbir-analytics/sbir_analytics/`
- `packages/sbir-ml/sbir_ml/`
- `packages/sbir-graph/sbir_graph/`

## Reference inventory

| Classification | Locations reviewed | Migration action |
| --- | --- | --- |
| Executable automation | `.github/workflows/ci.yml`, `.github/workflows/weekly.yml`, `.github/actions/setup-python-uv/action.yml`, `.pre-commit-config.yaml`, `Makefile`, and `scripts/` | Updated coverage, change detection, quality checks, Dagster modules, import paths, and command examples to current package roots. |
| Active documentation | `.github/` documentation, `config/README.md`, and active documents under `docs/` | Updated commands and package-path examples to current roots. |
| Historical documentation | `docs/decisions/ADR-002-etl-library-extraction.md` | Preserved because its references explain the prior layout and migration decision. |

CI and pre-commit run `scripts/ci/check_removed_src_references.py` to reject executable automation that reintroduces the removed source root. The historical ADR is explicitly excluded from that policy.

## Quality-check scope

Before this migration, CI Ruff checked only `sbir_etl/` and `tests/`, MyPy checked `sbir_etl/`, and coverage targeted the removed source root. After this migration:

- Ruff checks all four production roots plus `tests/`.
- Blocking MyPy remains scoped to `sbir_etl/`.
- Each package under `packages/` has a separate MyPy matrix job. `sbir-analytics` and `sbir-ml` are non-blocking while their existing typing debt is resolved; `sbir-graph` is blocking because it currently passes.
- Coverage measures all four current production roots.
- Change detection exposes a `production` result covering every production root and updates domain-specific filters to current paths.

Follow-up work should resolve MyPy findings in `sbir-analytics` and `sbir-ml` one package at a time, then make those matrix entries blocking.
