# SBIR Weekly Data Checks

## Overview

The `Weekly SBIR Awards Refresh` workflow now performs the following post-download validations before opening an automated PR:

- **Input profiling** via `scripts/data/profile_sbir_inputs.py` captures row counts, column headers, and schema drift for `data/raw/sbir/award_data.csv` and the SBIR company search extracts. Artifacts: `reports/awards_data_refresh/inputs_profile.json` and `.md`.
- **DuckDB ingestion + validator** using `scripts/data/run_sbir_ingestion_checks.py` materializes `raw_sbir_awards`, `validated_sbir_awards`, and `sbir_validation_report`, emitting metadata JSON, the validation report, and a markdown summary in `reports/awards_data_refresh/`.
- **Company enrichment coverage** through `scripts/data/run_sbir_enrichment_check.py` combines the refreshed awards file with all company search CSVs to report match coverage, method distribution, and merged company columns.
- **Integration regression tests** run `tests/integration/test_sbir_ingestion_assets.py` and `test_sbir_enrichment_pipeline.py` against the refreshed `award_data.csv` (using `SBIR_E2E_AWARD_CSV`) to guard core asset behaviour.
- **Neo4j Aura smoke tests** (optional) via `scripts/data/run_neo4j_sbir_load.py` loads validated awards into a Neo4j Aura cloud instance, creates Award and Company nodes with AWARDS relationships, and runs Cypher smoke checks via `scripts/data/run_neo4j_smoke_checks.py` to verify graph structure. The database is reset before each run via `scripts/data/reset_neo4j_sbir.py` to ensure clean state. See [Neo4j Aura Setup](neo4j-aura-setup.md) for configuration.

All generated artifacts are uploaded as a single `sbir-awards-metadata` workflow artifact alongside the gzipped raw CSV.

## Neo4j Smoke Test Details

The workflow connects to a Neo4j Aura cloud instance (if configured), resets it to a clean state, loads validated SBIR awards using the `neo4j_sbir_awards` asset, and runs smoke checks that verify:

- Award node count > 0
- Company node count > 0
- AWARDS relationship count > 0
- Sample award properties are populated correctly
- Award-Company connectivity is established

Load metrics and smoke check results are archived as JSON and Markdown artifacts for inspection.

## Remaining gaps

- **Supplemental datasets**: USPTO, transition detection, and fiscal assets remain out of scope for this job; they require their own source refreshes and validation harnesses.
- **Company enrichment realism**: The enrichment coverage step reports match quality but does not yet validate downstream dependants that consume the enriched frame (e.g., DAG outputs or dashboards). Consider extending regression tests to assert selected `company_` fields for real award samples.
