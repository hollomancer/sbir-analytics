---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-08-09
Status: draft
---

# Form D matching-covariate feasibility audit

> **Exploratory and non-citable.** This is a descriptive source-field audit.
> It does not construct matches, validate a treated cohort, establish balance,
> or authorize a treated-versus-control comparison.

## Decision

SEC SIC is not a viable v1 matching field in the pinned Form D universe. It is
present for 7,041 of 311,809 issuer CIKs and 26,291 of 673,656 filings. The
missingness also differs across the exact-name candidate and provisional
remainder partitions.

Form D `industry_group` is complete and can be evaluated as a candidate
coarsening variable for a narrower descriptive comparison among Form D filers.
It is not NAICS, a validated substitute for NAICS-2, a technology
classification, or evidence that two firms are economically comparable. The
audit therefore keeps `covariates_ready=false` and `ready_for_matching=false`.

## Field availability

The exact-name candidate partition contains the 4,465 CIKs conservatively
flagged in the preceding identity audit. The provisional remainder is the exact
set difference from the 311,809-CIK broad universe. It is not known to be free
of SBIR exposure.

| CIK-grain field | Broad universe | Exact-name candidates | Provisional remainder |
| --- | ---: | ---: | ---: |
| CIK rows | 311,809 | 4,465 | 307,344 |
| `industry_group` present anywhere in history | 311,809 | 4,465 | 307,344 |
| SEC SIC present anywhere in history | 7,041 | 431 | 6,610 |
| `state_or_country_code` present anywhere in history | 311,807 | 4,465 | 307,342 |
| First observed Form D year present | 311,809 | 4,465 | 307,344 |

| Filing-grain field | Broad universe | Exact-name candidates | Provisional remainder |
| --- | ---: | ---: | ---: |
| Filing rows | 673,656 | 15,390 | 658,266 |
| `industry_group` present | 673,656 | 15,390 | 658,266 |
| SEC SIC present | 26,291 | 2,113 | 24,178 |
| `state_or_country_code` present | 673,652 | 15,390 | 658,262 |
| Filing date present | 673,656 | 15,390 | 658,266 |

Missing values remain missing; the producer creates no `Unknown` matching
stratum.

## Frozen index-field rule

Every candidate field is taken from the same earliest observed eligible Form D
filing, ordered by filing date and accession:

- `index_accession`
- `index_filing_date`
- `first_observed_form_d_year`
- `index_industry_group`
- `index_state_or_country_code`
- `index_submission_type`

The audit never combines an industry group from one filing with a state code
from a later filing. Histories still change: 7,483 broad-universe CIKs have more
than one industry group and 8,744 have more than one state-or-country code.
Among exact-name candidates, those counts are 562 and 314.

| History diagnostic | Broad universe | Exact-name candidates | Provisional remainder |
| --- | ---: | ---: | ---: |
| Multiple industry groups | 7,483 | 562 | 6,921 |
| Multiple state-or-country codes | 8,744 | 314 | 8,430 |
| Index group `Pooled Investment Fund` | 146,737 | 15 | 146,722 |

There are 35 source industry-group values. At the frozen index filing, `Pooled
Investment Fund` accounts for 146,737 broad-universe CIKs, followed by `Other`
(34,258), `Other Technology` (27,838), and `Commercial` (18,613). Any later
eligibility rule would need to preregister how pooled funds and other
structurally different categories are handled; this audit does not exclude
them.

## Time-field limitation

`first_observed_form_d_year` is complete, but it is not founding year, financing
vintage, or award vintage. The source starts at 2009Q1, so the 2009 count is
left-censored. Matching a treated firm's first SBIR-award year against another
issuer's first observed Form D year would compare different time concepts.

| First observed Form D year | Broad universe | Exact-name candidates | Provisional remainder |
| ---: | ---: | ---: | ---: |
| 2009 | 16,456 | 498 | 15,958 |
| 2010 | 15,812 | 379 | 15,433 |
| 2011 | 12,559 | 227 | 12,332 |
| 2012 | 12,146 | 231 | 11,915 |
| 2013 | 13,373 | 242 | 13,131 |
| 2014 | 15,241 | 256 | 14,985 |
| 2015 | 15,827 | 277 | 15,550 |
| 2016 | 16,123 | 262 | 15,861 |
| 2017 | 17,200 | 313 | 16,887 |
| 2018 | 19,464 | 306 | 19,158 |
| 2019 | 19,967 | 268 | 19,699 |
| 2020 | 20,617 | 294 | 20,323 |
| 2021 | 33,600 | 251 | 33,349 |
| 2022 | 33,807 | 291 | 33,516 |
| 2023 | 24,287 | 206 | 24,081 |
| 2024 | 25,330 | 164 | 25,166 |

## State-or-country codes

The retained field is the SEC `STATEORCOUNTRY` value and is labeled
`state_or_country_code`. Its 192 observed values are not uniformly U.S. states;
for example, the raw index distribution includes codes `A6`, `E9`, and `X1`.
No truncation or state-only reinterpretation is applied.

| Frozen index-code class | Broad universe | Exact-name candidates | Provisional remainder |
| --- | ---: | ---: | ---: |
| Enumerated U.S. state or territory code | 283,846 | 4,428 | 279,418 |
| Other nonmissing SEC code | 27,960 | 37 | 27,923 |
| Missing at the index filing | 3 | 0 | 3 |

The classification above distinguishes enumerated U.S. state/territory codes
from all other SEC codes; it does not infer country names or domestic status.

## Mechanical cell support

Using only fields from the frozen index filing, the audit constructs cells on:

```text
(first observed Form D year, index industry group, index state-or-country code)
```

All 4,465 exact-name candidate CIKs have the three cell fields. Of those, 4,287
share a cell with at least one provisional-remainder CIK and 3,897 share a cell
with at least three. The provisional remainder contributes 307,341 eligible
CIKs across 18,247 cells.

These are cell-support counts, not match rates. They do not show balance,
comparability, or a valid counterfactual. The exact-name candidates are not the
final agency-treated cohort, and the provisional remainder is not a validated
control cohort.

## Provenance and remaining gates

The [tracked audit manifest](agency-private-capital-form-d-matching-covariates.manifest.json)
contains the full machine-readable availability, cardinality, history,
state-code, year, industry-group, and common-support tables. It pins and
verifies the 229,986-byte #582 control manifest, 725,072,925-byte issuer universe,
and 2,276,095-byte exact-name exclusion ledger. The universe and exclusion
SHA-256 values are respectively
`28bb167e0281bca00652444600b6635c4c0b60b0103817715df34a98f67e3fe5`
and `94cb5bc0eae682675f6e0015cc2c21b48411aba6429b6ef5e4cccfe769af38d3`.
The control-manifest SHA-256 is
`ea8959eced26e5435bf4db29947452cbc19878cb494d5ec5ee30d9954b0c8916`.
Two full runs produced byte-identical tracked manifests with SHA-256
`57c093fbb0a71283f2460c0d62579470979b6fea3949c32d939cf22e19b8c9e3`.

Before any matching PR, the project still needs a validated agency-specific
treated CIK set, one symmetric index-date rule, a preregistered
operating-company eligibility rule, agency-specific overlap checks, and a
revised estimand if source `industry_group` replaces the originally required
NAICS-2. Matching on a post-award Form D classification could also condition on
a mediator and must be addressed explicitly.

Reproduce after materializing the pinned #582 products:

```bash
uv run python scripts/data/audit_form_d_matching_covariates.py \
  --manifest docs/research/agency-private-capital-form-d-control-universe.manifest.json \
  --universe data/processed/agency_private_capital/control_universe/form_d_issuer_universe.identity-staging.jsonl \
  --exclusions data/processed/agency_private_capital/control_universe/sbir_cik_exclusion_candidates.identity-staging.jsonl \
  --audit-manifest docs/research/agency-private-capital-form-d-matching-covariates.manifest.json \
  --code-version b326926a56ea7aa2627fde7faf5109463344a6ac \
  --expected-real-data-contract
```
