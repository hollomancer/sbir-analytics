# Agency Private-Capital Phase 2 Form D Methodology

Phase 2 compares a configured agency's SBIR awardees that have high-confidence
Form D matches with non-SBIR Form D issuers. It supports research questions
F3, B2, and B3 by producing a descriptive matched-cohort artifact, not a causal
treatment estimate.

## Inputs

- `data/form_d_details.jsonl`: SBIR-company Form D matches from the SEC EDGAR
  pipeline. Phase 2 keeps high-tier matches and excludes industry groups already
  flagged as structurally incompatible with operating-company SBIR raises.
- `data/form_d_control_universe.jsonl`: broader Form D issuer universe for
  non-SBIR controls. Issuers with CIKs already resolved to any SBIR company are
  dropped before matching.
- `data/sbir_ma_events.jsonl`: curated M&A event signals. Missing files produce
  unavailable metrics rather than zero-valued outcomes.

## Matching

The v1 matcher uses coarsened-exact matching on:

- filing or award vintage year
- Form D industry group
- issuer state

This intentionally avoids propensity scoring until the control side has richer
firm-level covariates. The asset publishes matched-pair rows and a
`match_balance.json` file with cohort sizes, match rate, per-stratum counts, and
an agency-scoped Form D leverage cross-check.

## Outputs

The Dagster asset
`agency_private_capital_form_d_matched_comparison` writes to
`data/processed/agency_private_capital/<agency>/`:

- `agency_vs_form_d_comparison.parquet`
- `agency_vs_form_d_matched_pairs.parquet`
- `agency_vs_form_d_comparison.md`
- `match_balance.json`
- `threats_to_validity.json`

The markdown report includes outcome rows for federal-contract presence, patent
presence, and M&A exit rate. Metrics whose event inputs are not materialized are
marked unavailable.

## Interpretation

The comparison is descriptive. Required threats-to-validity entries cover SAFE
and convertible undercount, late-stage Form D inclusion, issuer-reported
industry noise, CIK-resolution recall limits, selection bias, and timing leakage
from excluding any issuer ever matched to SBIR.
