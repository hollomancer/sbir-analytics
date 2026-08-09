# Agency Private-Capital Phase 2 Form D Methodology

Phase 2 is intended to compare a configured agency's SBIR awardees with a
covariate-matched cohort of Form D issuers. The repository currently has a tested
comparison scaffold and a bounded control-identity staging producer, not a valid
matched comparison. The staging artifacts described below must not be consumed by
the existing matched-comparison asset or used for a Phase 2 finding. The target
remains a descriptive artifact for research questions F3, B2, and B3, not a causal
treatment estimate.

## Official source and frozen coverage

The maintained CLI, `scripts/data/build_form_d_control_universe.py`, consumes the
SEC Division of Economic and Risk Analysis (DERA)
[quarterly Form D bulk ZIP files](https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets).
Its source contract is the closed, inclusive set **2009Q1 through 2024Q4**, not a
moving "latest" window. Deterministic manifests pin the expected quarter set and
the source and product checksums so a rerun cannot silently change its inputs.

The SEC's [official Form D](https://www.sec.gov/files/Form_D.pdf) and the DERA bulk
files supply issuer SIC and Form D industry-group fields. They do **not** supply
NAICS. This producer does not infer NAICS or claim that SIC or industry group is
an interchangeable substitute for NAICS-2.

## Provisional staging products

Under `data/processed/agency_private_capital/control_universe/`, the CLI produces
three logically distinct products plus one build manifest:

- a broad issuer universe parsed from the pinned official quarterly files;
- candidate SBIR-CIK exclusion evidence, created by exact equality after
  normalizing every observed historical SBIR company name and each Form D issuer
  name with `CompanyNameProfile.ORGANIZATION_KEY_V1`; and
- a filtered, disjoint identity-only control staging set after removing those
  candidate exact-name matches.

The second product is candidate exclusion evidence, not a complete resolution of
SBIR firms to CIKs. Exact normalized-name matching has unknown exclusion recall:
aliases, acquisitions, renames, spelling variants, and other identity changes can
remain unmatched. Accordingly, the manifest states
`complete_sbir_exclusion=false`. A retained issuer means only that its name was
not an exact normalized-key match to the observed SBIR award history; it does
**not** mean "never SBIR."

The filtered product is useful for auditing the identity boundary because its
included and excluded CIK sets are disjoint. It is still provisional staging,
with `covariates_ready=false`, because no validated SIC-to-NAICS-2 strategy exists.
A higher-recall authoritative CIK/alias union and a validated SIC-to-NAICS-2
strategy are both required before task 2.2 can close or the matched asset can read
this output.

## Target matching design

After those prerequisites are satisfied, the target v1 matcher uses
coarsened-exact matching on:

- filing or award vintage year;
- validated NAICS-2; and
- issuer state.

The target deliberately avoids propensity scoring until the control side has
richer firm-level covariates. A later valid run should publish matched-pair rows
and balance metadata with cohort sizes, match rates, per-stratum counts, and
unmatched residuals. None of those are current staging results.

## Outcome availability

The Phase 2 scaffold is not symmetric today:

- no real FPDS outcome input is joined for both treated and control firms;
- no patent input is joined for both sides; and
- `data/sbir_ma_events.jsonl` contains SBIR-side M&A evidence and therefore
  cannot establish control-side M&A coverage.

Missing event inputs and missing coverage are reported as **unavailable**, never
as zero. Symmetric FPDS, patent, and M&A outcome contracts belong in separate
follow-on PRs. Until they are implemented and validated, the scaffold cannot
support treated-versus-control outcome deltas.

## Target outputs and interpretation

Once the identity, covariate, and outcome gates are satisfied, the Dagster asset
`agency_private_capital_form_d_matched_comparison` is intended to write under
`data/processed/agency_private_capital/<agency_lower>/`:

- `agency_vs_form_d_comparison.parquet`;
- `agency_vs_form_d_matched_pairs.parquet`;
- `agency_vs_form_d_comparison.md`;
- `match_balance.json`; and
- `threats_to_validity.json`.

The eventual comparison is descriptive, not a causal treatment estimate.
Required threats to validity include SAFE and convertible undercount, late-stage
Form D inclusion, industry classification limits, incomplete SBIR-CIK exclusion,
selection bias, and timing leakage. The Phase 2 gate remains open.
