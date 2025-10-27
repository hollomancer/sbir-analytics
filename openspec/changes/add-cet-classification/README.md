# Add CET Classification — Change Set README

This change set adds the foundations for CET (Critical & Emerging Technologies) classification:
- Taxonomy loader and Pydantic validation
- Dagster-compatible `cet_taxonomy` asset (lightweight, import-safe)
- Lightweight completeness checks and CLI suitable for CI
- Unit tests for the taxonomy loader / asset
- CI workflow change to run taxonomy checks before the full test suite

Purpose
- Provide a validated, versioned source of CET areas that downstream ML, aggregation, and Neo4j loaders can consume.
- Make it easy to fail fast in CI when taxonomy issues (missing keywords, missing definitions, incorrect count) are detected.
- Keep unit tests and CI runs robust in environments that may not have optional binary dependencies (e.g., parquet engines, Dagster installed).

Key files added / changed
- `src/ml/config/taxonomy_loader.py` — Taxonomy loader with `validate_taxonomy_completeness()` that returns metrics useful for asset checks.
- `src/assets/cet_assets.py` — `cet_taxonomy` asset that:
  - loads the taxonomy, converts to a DataFrame, and persists an artifact
  - writes a companion checks JSON next to the artifact
  - is resilient when `dagster` or parquet engines are not installed (small stubs; JSON fallback)
- `src/ml/config/taxonomy_checks.py` — CLI to run taxonomy completeness checks (intended for CI).
- `tests/unit/ml/test_taxonomy_asset.py` — Unit tests for loader + asset behavior.
- `.github/workflows/ci.yml` — CI workflow updated to run the taxonomy checks CLI and upload the checks artifact before the test step.

Where artifacts go
- Primary expected artifact: `data/processed/cet_taxonomy.parquet` (parquet; real environment)
- If parquet engine is not available, a JSON fallback is produced alongside a placeholder `.parquet` file:
  - NDJSON fallback: `data/processed/cet_taxonomy.json`
- Companion checks JSON: `data/processed/cet_taxonomy_checks.json` (written by the asset) and/or `data/processed/cet_taxonomy_checks_summary.json` (written by the CLI)

How to run checks locally
1. Ensure your working directory is the project root.
2. With the project's environment (Poetry / virtualenv) active, run:
   - Run CLI checks (fail on issues):
     `poetry run python -m src.ml.config.taxonomy_checks --output data/processed/cet_taxonomy_checks.json --fail-on-issues`
   - Run CLI checks without failing (print summary):
     `poetry run python -m src.ml.config.taxonomy_checks --output data/processed/cet_taxonomy_checks.json`
3. To run the unit tests added here:
   `pytest tests/unit/ml/test_taxonomy_asset.py`

CI behavior (what we changed)
- The existing CI workflow now invokes the taxonomy checks CLI early:
  - If `--fail-on-issues` triggers, the job fails and CI stops; the checks JSON is uploaded as an artifact for inspection.
  - If checks pass, CI continues to run the full test suite.
- The checks JSON artifact is uploaded so reviewers can inspect completeness output.

Interpreting checks JSON and exit codes
- The checks JSON contains a `completeness` object with keys such as:
  - `total_areas`, `areas_missing_keywords_count`, `areas_missing_definition_count`, `missing_required_fields`
- CLI exit codes:
  - `0`: checks passed (no blocking issues)
  - `2`: issues detected and `--fail-on-issues` was used
  - `1`: unexpected exception or failure to run checks

Notes and caveats
- The repository code is now resilient for running the taxonomy tests without optional dependencies:
  - When a parquet engine (`pyarrow`/`fastparquet`) is not present, the asset writes an NDJSON fallback and a placeholder `.parquet` file.
  - When `dagster` is not installed, small local stubs are used so unit tests and CI can exercise the asset logic without needing the full runtime.
- For a full-production run, ensure `pyarrow` (or `fastparquet`) and Dagster are installed so real parquet files and Dagster materializations are produced.

Next recommended steps
1. Review and merge this change set so the taxonomy checks run on PRs.
2. Once merged, monitor CI runs for any taxonomy failures and iterate on taxonomy content if necessary.
3. Begin Sprint 2 (EvidenceExtractor and CET classifier core) after taxonomy is stable.

Owners / contacts
- Implementation lead: @conradhollomon
- Data / asset owner: data-engineer (per tasks.md)
- ML owner: ml-engineer

If you want, I will:
- Add a tiny README example showing a parsed checks JSON sample,
- Or proceed to Sprint 2 implementation (evidence extraction + classifier scaffolding).