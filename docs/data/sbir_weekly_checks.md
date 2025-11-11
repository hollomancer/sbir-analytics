# SBIR Weekly Data Checks

## Overview

The `Weekly SBIR Awards Refresh` workflow now performs the following post-download validations before opening an automated PR:

- **Input profiling** via `scripts/data/profile_sbir_inputs.py` captures row counts, column headers, and schema drift for `data/raw/sbir/award_data.csv` and the SBIR company search extracts. Artifacts: `reports/awards_data_refresh/inputs_profile.json` and `.md`.
- **DuckDB ingestion + validator** using `scripts/data/run_sbir_ingestion_checks.py` materializes `raw_sbir_awards`, `validated_sbir_awards`, and `sbir_validation_report`, emitting metadata JSON, the validation report, and a markdown summary in `reports/awards_data_refresh/`.
- **Company enrichment coverage** through `scripts/data/run_sbir_enrichment_check.py` combines the refreshed awards file with all company search CSVs to report match coverage, method distribution, and merged company columns.
- **Integration regression tests** run `tests/integration/test_sbir_ingestion_assets.py` and `test_sbir_enrichment_pipeline.py` against the refreshed `award_data.csv` (using `SBIR_E2E_AWARD_CSV`) to guard core asset behaviour.

All generated artifacts are uploaded as a single `sbir-awards-metadata` workflow artifact alongside the gzipped raw CSV.

## Remaining gaps

- **Neo4j coverage**: The workflow does not currently materialize loaders against a live Neo4j instance. A future enhancement could launch a disposable Aura/Container Neo4j and run the appropriate loader asset checks.
- **Supplemental datasets**: USPTO, transition detection, and fiscal assets remain out of scope for this job; they require their own source refreshes and validation harnesses.
- **Company enrichment realism**: The enrichment coverage step reports match quality but does not yet validate downstream dependants that consume the enriched frame (e.g., DAG outputs or dashboards). Consider extending regression tests to assert selected `company_` fields for real award samples.

