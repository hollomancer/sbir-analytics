---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-08-10
Status: draft
---

# SBIR ↔ Form D candidate identity-crosswalk audit

> **Exploratory and non-citable.** This release is a deterministic identity-review
> worklist. Exact normalized-name equality supplies candidate evidence, not proof
> that an SBIR awardee and a Form D issuer are the same legal entity. It contains
> no accepted matches and defines no control population.

## Materialization result

Producer commit `84cd4db9bd04be23bf61d30d8b9405d08ab95c73`
materialized the pinned full-history sources twice. The two release directories
were byte-identical, including both content-addressed JSONL products and the
fixed-name runtime manifest.

| Audit measure | Value |
| --- | ---: |
| SBIR award rows | 219,500 |
| Rows with at least one valid UEI or DUNS | 182,000 |
| Rows with malformed nonblank identifier evidence | 1,864 |
| Unique normalized SBIR organization names | 34,287 |
| Form D source window | 2009Q1–2024Q4 (64 quarters) |
| Form D issuer CIKs / filing records validated | 311,809 / 673,656 |
| SBIR firm-ledger components | 34,426 |
| Identifier-basis / name-only-basis components | 23,519 / 10,907 |
| `identifier_consistent` / `name_only` / `quarantined_conflict` | 23,456 / 10,736 / 234 |
| Candidate edges | 4,542 |
| Candidate SBIR firms / Form D CIKs / normalized names | 4,450 / 4,465 / 4,423 |
| Firms with multiple candidate CIKs | 90 (maximum 3) |
| CIKs with multiple candidate firms | 74 (maximum 3) |

Valid-identifier and malformed-identifier row counts are not mutually
exclusive. Likewise, construction basis and component status are separate:
conflicting or malformed evidence is retained in the ledger but quarantined.

## Grain and evidence lineage

The candidate-edge grain is exactly one unique
`(sbir_firm_id, form_d_cik)` pair. A firm linked by exact name to three CIKs has
three edges; a CIK linked to three distinct SBIR components also has three.
There is no first-CIK, best-CIK, or name-level collapse. Each edge aggregates
only the evidence belonging to its own pair.

SBIR firm IDs are content-derived. Rows with valid identifiers form connected
components from exact UEI/DUNS co-occurrence only; organization names never join
two identifier-backed components. Rows without a valid UEI or DUNS use a
separate exact-name-key namespace and never merge into an identifier component.
Every SBIR source record is preserved once in the ledger.

Candidate generation then applies exact equality under
`CompanyNameProfile.ORGANIZATION_KEY_V1`. Every edge retains the matching
normalized name, one-based SBIR source-record ordinals and raw company names,
plus the Form D raw aliases and filing accession numbers for that CIK. Form D
evidence is CIK-local and is never pooled across issuers.

The source runtime manifest is externally pinned at SHA-256
`3ce34a04b592131dbd0aefdb8692c21c5ab72e46f90f5f81a2aeffb9dbaeeaaf`
(231,122 bytes). It in turn pins the broad Form D issuer universe and the SBIR
award source. The tracked
[crosswalk manifest](agency-private-capital-sbir-form-d-identity-crosswalk.manifest.json)
records the complete input/output lineage and invariants. Both builds emitted
the runtime crosswalk manifest with SHA-256
`71944c74dd7d6db05545757db85b812c56aa03fdb5cf25febdb23f13e50744c3`.
The tracked copy adds only its `artifact_role`, so its file digest is
intentionally different.

| Artifact | Rows | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| SBIR `award_data.csv` | 219,500 | 394,456,822 | `73d646fc6883ed93b36d19518b0d9442a9ebae94c5b49ad5a7fcd6d3c2b872dd` |
| SBIR firm identity ledger | 34,426 | 62,253,221 | `272d566a665aca6262f073c75c585dcca4d9ed61ff52bb7f8197e95f50b80508` |
| SBIR–Form D candidate edges | 4,542 | 6,578,060 | `5677ffe3b96b8d103312a7cc99b1ef9d12d3a7ebf95032b5e24e4c53fbbc193a` |

Reproduce from the pinned producer commit with the runtime control-universe
products and SBIR snapshot present:

```bash
uv run python scripts/data/build_sbir_form_d_identity_crosswalk.py \
  --control-manifest data/processed/agency_private_capital/control_universe/form_d_control_universe.manifest.json \
  --control-manifest-sha256 3ce34a04b592131dbd0aefdb8692c21c5ab72e46f90f5f81a2aeffb9dbaeeaaf \
  --awards-csv data/raw/sbir/award_data.csv \
  --output-dir /tmp/sbir-form-d-identity-crosswalk-run-1 \
  --code-version 84cd4db9bd04be23bf61d30d8b9405d08ab95c73
```

Repeat with `run-2` as the output directory, then verify the deterministic
release with
`diff -rq /tmp/sbir-form-d-identity-crosswalk-run-1 /tmp/sbir-form-d-identity-crosswalk-run-2`.

## Gate decision and nonclaims

Every edge remains `candidate_unreviewed`; `same_legal_entity` is unknown
(`null`). `identity_accepted`, `exclusion_eligible`, `matching_eligible`, and
`rate_eligible` are all false. The release also keeps
`complete_sbir_exclusion`, `covariates_ready`, and `ready_for_matching` false,
with `exclusion_recall="unknown"`.

Accordingly, these candidates do not identify a legal-entity match, establish
parent/subsidiary, affiliate, acquirer, successor, fund, or shared-person
identity, authorize SBIR exclusion, establish control eligibility, choose a
preferred CIK, attach capital amounts, or support matching, outcome, or rate
claims. Those decisions require a separate reviewed identity contract.
