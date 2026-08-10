---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-08-09
Status: draft
---

# Exact-name SBIR candidate / Form D filing-proxy audit

> **Exploratory and non-citable.** This is an identity-and-evidence audit, not
> an outcome study or a treated-versus-control comparison. The evidence is a
> filer-supplied Form D business-combination filing proxy. It does not verify a
> merger, acquisition, transaction, exit, or successful commercialization.

## Materialization result

The audit linked the 4,465 exact-name candidate CIKs from the pinned Form D
control-universe identity stage to the symmetric
`form_d_business_combination_filing_proxy` evidence on canonical exact CIK.
Within the complete federal filing fiscal years FY2010–FY2024, it retained 283
unique Form D accessions across 212 exact Form D CIKs. These are filing and CIK
counts, not rates. They do not establish that every candidate identity is an
SBIR firm or that any filing corresponds to a completed business combination.

| Filing fiscal year | Proxy filings | Distinct exact Form D CIKs |
| ---: | ---: | ---: |
| 2010 | 26 | 23 |
| 2011 | 29 | 23 |
| 2012 | 16 | 13 |
| 2013 | 29 | 20 |
| 2014 | 22 | 21 |
| 2015 | 20 | 18 |
| 2016 | 19 | 16 |
| 2017 | 14 | 12 |
| 2018 | 12 | 10 |
| 2019 | 16 | 14 |
| 2020 | 17 | 16 |
| 2021 | 17 | 16 |
| 2022 | 13 | 11 |
| 2023 | 16 | 15 |
| 2024 | 17 | 15 |
| **Complete FY2010–FY2024 window** | **283** | **212** |

Distinct-CIK counts are not additive across filing fiscal years because a CIK
can have evidence in more than one year. Filing fiscal year is derived from the
SEC filing date: October through December map to the following federal fiscal
year. It is not a transaction, announcement, signing, closing, or exit year.

The bounded source starts on 2009-01-01 and ends on 2024-12-31. Consequently,
FY2009 and FY2025 are incomplete. Ten FY2009 filings across ten CIKs and two
FY2025 filings across two CIKs were audited as boundary diagnostics but excluded
from the product and headline counts. The full source-window join contains 295
filings across 222 CIKs; that boundary-inclusive count is not the complete-FY
result.

## Identity sensitivity

Each candidate CIK is classified from the already-materialized exact-name
evidence. `unique_within_materialized_name_map` means that at least one matched
normalized name mapped to one CIK in that materialization.
`ambiguous_name_only` means every matched normalized name mapped to multiple
candidate CIKs.

| Exact-name evidence class | Proxy filings | Distinct exact Form D CIKs |
| --- | ---: | ---: |
| `unique_within_materialized_name_map` | 250 | 186 |
| `ambiguous_name_only` | 33 | 26 |
| **Complete FY2010–FY2024 window** | **283** | **212** |

“Unique” here is not a verified real-world corporate identity. The upstream
exact-name exclusion has unknown recall and can miss aliases, renames, spelling
variation, acquisitions, or unresolved CIKs. This audit does not rerun or expand
name matching.

## Agency membership diagnostics

Agency tags are reconstructed from the pinned SBIR award snapshot only for the
normalized names already recorded in the candidate ledger. A CIK can carry
multiple tags, so the rows below overlap and must not be summed.

| Agency tag | Proxy filings | Distinct exact Form D CIKs |
| --- | ---: | ---: |
| NSF | 44 | 31 |
| DOE | 31 | 23 |
| HHS | 181 | 133 |
| DoD | 96 | 76 |

These are evidence-membership diagnostics, not agency outcome comparisons.
They do not use award dates, post-award windows, matched controls, or mutually
exclusive agency assignment.

## Filing lineage

The complete-FY product preserves 257 original `D` filings and 26 `D/A`
amendments. Each amendment remains a separate filing-evidence row with its prior
accession when supplied. The audit does not collapse related filings into an
inferred transaction.

Each output row retains the exact CIK and firm key, accession, filing date and
fiscal year, submission type, amendment lineage, proxy/evidence labels, source
snapshot, matched normalized names, evidence class, and sorted agency tags.
One accession produces one row even when it has multiple names or agency tags.

## Provenance and gate decision

The [tracked materialization manifest](agency-private-capital-sbir-form-d-business-combination-proxy-audit.manifest.json)
pins both upstream manifest byte hashes; the candidate, event, and coverage
product hashes, sizes, and row counts; the SBIR award snapshot; the
content-addressed audit product; aggregate reconciliations; and all fail-closed
gates. The producer verifies exact canonical CIKs, unique accessions and event
IDs, complete source coverage for every candidate CIK, expected proxy labels,
and the 2009-01-01 through 2024-12-31 source interval before publishing.

| Product | Rows | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Complete-FY filing evidence audit | 283 | 244,696 | `aaa60a046a8a8d952dee06fd4a83a496eecb167f3ce2bff2d0e4ae69a5f4af91` |

Two full materializations produced byte-identical product and manifest hashes;
the tracked manifest SHA-256 is
`9c23587c49a1ecddea15f1fc0af67b4016a905d253d46d3198c3f0642042e768`.

This audit does not close the Phase 2 identity, covariate, or outcome gates.
Its manifest retains `complete_sbir_identity=false`,
`complete_sbir_exclusion=false`, `exclusion_recall="unknown"`,
`covariates_ready=false`, `ready_for_matching=false`,
`outcome_kind="filing_proxy"`, and `verified_ma=false`.

Reproduce after materializing the pinned #582 and #584 products:

```bash
uv run python scripts/data/audit_sbir_form_d_business_combination_proxy.py \
  --control-manifest docs/research/agency-private-capital-form-d-control-universe.manifest.json \
  --candidate-jsonl data/processed/agency_private_capital/control_universe/sbir_cik_exclusion_candidates.identity-staging.jsonl \
  --proxy-manifest docs/research/agency-private-capital-form-d-business-combination-proxy.manifest.json \
  --event-jsonl data/processed/agency_private_capital/form_d_business_combination_events/form_d_business_combination_filing_proxy.events.8ad27fa2cc319971853f6aaed8b637c7267ca4803901fa62b3b30799da5086fb.jsonl \
  --coverage-jsonl data/processed/agency_private_capital/form_d_business_combination_events/form_d_business_combination_filing_proxy.coverage.1a8b017959109e8c14ce8469fd93b6ef3df5751b93678a4b092b8af7562c510b.jsonl \
  --awards-csv data/raw/sbir/award_data.csv \
  --output-dir data/processed/agency_private_capital/sbir_form_d_proxy_audit \
  --audit-manifest docs/research/agency-private-capital-sbir-form-d-business-combination-proxy-audit.manifest.json \
  --code-version 3e76c3bf165693ebca056841127255a28ad497d6
```
