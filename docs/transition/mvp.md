# Transition Detection MVP — Quick Start

This guide walks you through running the Transition Detection MVP locally, reviewing artifacts, and understanding the quality gates and scoring signals.

The MVP links SBIR awards to federal contracts using vendor resolution (UEI/DUNS/fuzzy name), light scoring (method weight + temporal + agency), and emits structured evidence for manual review. It is designed to run without Dagster installed (import-safe shims), using pandas and simple file IO.

## What you’ll get

Artifacts (created under data/processed and reports/validation):

- data/processed/contracts_sample.parquet (or .csv fallback) + contracts_sample.checks.json
- data/processed/vendor_resolution.parquet (or .ndjson fallback) + vendor_resolution.checks.json
- data/processed/transitions.parquet (or .ndjson fallback) + transitions.checks.json
- data/processed/transitions_evidence.ndjson (one JSON object per candidate)
- reports/validation/transition_mvp.json (summary of counts and gates)

Quality gates (reported and enforced via checks/summary):

- contracts_sample:
  - action_date coverage ≥ 0.90
  - any identifier coverage (UEI or DUNS or PIID or FAIN) ≥ 0.60
- vendor_resolution:
  - resolution_rate ≥ 0.60

Scoring signals:

- Match method weight: UEI=0.9, DUNS=0.8, fuzzy-name=0.7
- Temporal boost: award_date ≤ contract action_date, within window (default 5y), with stronger boost for ≤2y
- Agency alignment boost: awarding agency code or normalized name match

Notes:
- Parquet is attempted first; if pyarrow/fastparquet is not available, artifacts fall back to NDJSON in the same directory with .ndjson suffix.
- Asset checks are available for Dagster environments and are also reflected in the validation summary for the local MVP run.

## Prerequisites

- Python 3.11+
- Poetry installed and the project dependencies installed:
  - poetry install

No local Neo4j or Dagster environment is required for this MVP run.

## Run the MVP

The repo includes a convenience Make target that runs the assets in-process with shims (no Dagster needed) and seeds tiny fixtures if needed:

- make transition-mvp-run

What it does:
1) Prepare a minimal contracts sample if none exists:
   - data/processed/contracts_sample.parquet (or .csv if parquet not available)
   - Two dummy contracts (UEI exact match and fuzzy name match) are created with awarding agency fields for alignment signals.
2) Run assets (in order):
   - contracts_sample
   - vendor_resolution
   - transition_scores_v1
   - transition_evidence_v1
3) Write checks and validation summary:
   - data/processed/*.checks.json
   - reports/validation/transition_mvp.json

Clean up artifacts:
- make transition-mvp-clean

## Reviewing results

- Vendor mapping:
  - data/processed/vendor_resolution.parquet or .ndjson
  - data/processed/vendor_resolution.checks.json
- Transition candidates:
  - data/processed/transitions.parquet or .ndjson
  - data/processed/transitions.checks.json
- Evidence:
  - data/processed/transitions_evidence.ndjson

Example: View first 5 evidence lines
- head -n 5 data/processed/transitions_evidence.ndjson

Example: Filter evidence for a specific contract_id (requires jq)
- jq -c 'select(.contract_id=="C1")' data/processed/transitions_evidence.ndjson

Validation summary:
- reports/validation/transition_mvp.json
  - Consolidates counts, method breakdown, score stats, and pass/fail for the gates
  - Useful for CI or quick manual checklist

## Thresholds and environment variables

You can tweak thresholds and scoring parameters using environment variables:

- Input/config:
  - SBIR_ETL__TRANSITION__CONTRACTS_SAMPLE__PATH
    - Path to contracts sample (default: data/processed/contracts_sample.parquet)

- Vendor resolution:
  - SBIR_ETL__TRANSITION__FUZZY__THRESHOLD (default: 0.85)
  - SBIR_ETL__TRANSITION__VENDOR_RESOLUTION__MIN_RATE (default: 0.60)

- Contracts coverage gates:
  - SBIR_ETL__TRANSITION__CONTRACTS__DATE_COVERAGE_MIN (default: 0.90)
  - SBIR_ETL__TRANSITION__CONTRACTS__IDENT_COVERAGE_MIN (default: 0.60)

- Candidate scoring:
  - SBIR_ETL__TRANSITION__LIMIT_PER_AWARD (default: 50)
  - SBIR_ETL__TRANSITION__DATE_WINDOW_YEARS (default: 5)
  - SBIR_ETL__TRANSITION__DATE_BOOST_MAX (default: 0.10)
  - SBIR_ETL__TRANSITION__AGENCY_BOOST (default: 0.05)

These are read at runtime; no restart needed for subsequent runs in the same shell.

## Data expectations

Contracts sample schema (minimal):
- contract_id
- piid
- fain
- vendor_uei
- vendor_duns
- vendor_name
- action_date
- obligated_amount
- awarding_agency_code
- awarding_agency_name (optional, helps with agency alignment)

Enriched SBIR awards minimal fields leveraged:
- award_id
- Company
- UEI
- Duns
- award_date (or a reasonable date proxy; the scorer looks for several common date columns)
- Agency (or awarding_agency_name / code for alignment)

For the quick-start run, a tiny in-memory awards DataFrame is created within the runner and does not require any files on disk.

## How gating works

- contracts_sample_quality_check:
  - Computes coverage for action_date and any identifier
- vendor_resolution_quality_check:
  - Computes resolution_rate = share of match_method != unresolved

In Dagster environments, these checks can block downstream assets if thresholds fail. In the local shimmed run, gate evaluations are recorded in reports/validation/transition_mvp.json, which you can use for CI pass/fail logic or manual review.

## Troubleshooting

- Parquet module missing
  - The pipeline will write .ndjson files instead of parquet automatically.
  - You can install pyarrow to enable parquet:
    - poetry add pyarrow

- No data produced
  - Check logs printed by the make target.
  - Ensure you have write permissions to data/processed and reports/validation.

- Fuzzy matches too strict or too lenient
  - Adjust SBIR_ETL__TRANSITION__FUZZY__THRESHOLD (e.g., export SBIR_ETL__TRANSITION__FUZZY__THRESHOLD=0.7)

- Gates failing
  - Review the checks JSON files and validation summary.
  - You can relax thresholds via environment variables while iterating locally.

## What’s next (extensibility)

- Additional scoring signals:
  - Amount sanity checks (obligation vs award)
  - Patent/external signals
- PaECTER layer integration (embeddings + similarity) for richer linking
- CI wiring for the validation summary to gate transitions in PRs
- Optional FAISS index for scalable candidate generation
- Neo4j loaders for transition relationships

If you want to integrate this into a Dagster job, import the transition assets and asset checks from src/assets/transition_assets.py and register them in your definitions. The code is import-safe and can run in constrained environments.

## Commands reference

- Run:
  - make transition-mvp-run
- Clean:
  - make transition-mvp-clean

Artifacts appear under data/processed and reports/validation after a successful run.