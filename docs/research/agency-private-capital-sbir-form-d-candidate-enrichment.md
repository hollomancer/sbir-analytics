---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-08-10
Status: draft
---

# SBIR ↔ Form D candidate-enrichment audit

> **Exploratory and non-citable.** This release expands a deterministic identity-review
> worklist. Exact and fuzzy name evidence generate candidates, not legal-entity decisions. It
> contains no accepted identity links, defines no control population, and attaches no capital
> amounts or outcomes.

## Materialization result

Producer commit `c91f00ac55f95b4c0d0d468af8a82c2428f9be61` materialized the pinned
full-history inputs twice. The two release directories were byte-identical. Their runtime manifests
both have SHA-256 `a2c293796b135094ce4bfa77f6aa2f704c153277394adffa7aebf121ca09744f`;
their candidate JSONLs both have SHA-256
`67779f952df4abb114488bbfcee3f3898758662f6898898ae6abd952bc71a1c7`.

| Audit measure | Value |
| --- | ---: |
| SBIR award rows validated | 219,500 |
| SBIR firm-ledger components | 34,426 |
| Form D issuer CIKs / filing records validated | 311,809 / 673,656 |
| Atomic candidate pairs | 7,787 |
| Preserved exact pairs / fuzzy-only pairs | 4,542 / 3,245 |
| Candidate SBIR firms / Form D CIKs | 5,631 / 6,033 |
| Firms linked to multiple candidate CIKs | 787 (maximum 27) |
| CIKs linked to multiple candidate firms | 779 (maximum 29) |
| Candidate pairs with any contact intersection / none | 7,015 / 772 |
| Quarantined-component pairs / firms | 36 / 30 |

The large collision maxima are review signals, not permission to choose one CIK. The 36
quarantined-component pairs remain in the review universe, visibly marked, but cannot become
automatic identity decisions. The release also preserves 254 exact pairs whose names are too short
for fuzzy generation.

## Frozen candidate routes

Fuzzy comparison applies only to unequal names with at least six alphanumeric characters on each
side. Similarity is pinned to RapidFuzz `3.14.3`; a different or missing backend fails closed.

- `strong_name`: equal two-character alphanumeric prefix and ratio at least `0.95`;
- `state_supported`: equal prefix, equal strict U.S. state, and ratio at least `0.85`; and
- `zip_supported`: equal strict ZIP5 and ratio at least `0.80`, without a prefix requirement.

There is no fallback, top-k truncation, phonetic rule, person rule, or post-materialization
threshold tuning. Route counts overlap because one pair can satisfy multiple declared rules.

| Exact route combination | Pairs |
| --- | ---: |
| `exact_normalized_name` | 4,542 |
| `strong_name` | 232 |
| `strong_name` + `state_supported` | 26 |
| `strong_name` + `state_supported` + `zip_supported` | 13 |
| `state_supported` | 1,116 |
| `state_supported` + `zip_supported` | 46 |
| `zip_supported` | 1,812 |

The marginal route totals are 271 `strong_name`, 1,201 `state_supported`, and 1,871
`zip_supported`. For a later exclusive validation sample ordered exact → strong → state → ZIP,
the corresponding strata contain 4,542, 271, 1,162, and 1,812 pairs.

Every route has a deterministic witness. Fuzzy witnesses retain the qualifying SBIR raw names and
source-record ordinals, Form D raw aliases and accessions, ratio/token-sort/token-set scores, and
the required prefix, state, or ZIP evidence. Exact rows embed their Phase 1 edge unchanged.

## Contact corroboration and provenance

Street line 1, city, strict state, strict ZIP5, and normalized ten-digit U.S. phone are intersected
only after a name route creates a pair. They never generate candidates. Each shared value names its
supporting SBIR source records and Form D accessions, within one firm and one CIK.

| Contact field | Pairs with an exact intersection |
| --- | ---: |
| Street line 1 | 641 |
| City | 5,079 |
| State | 6,942 |
| ZIP5 | 4,522 |
| Phone | 1,733 |

The tracked
[candidate manifest](agency-private-capital-sbir-form-d-candidate-enrichment.manifest.json) pins
the PR1 crosswalk runtime manifest at SHA-256
`71944c74dd7d6db05545757db85b812c56aa03fdb5cf25febdb23f13e50744c3`
and its upstream control manifest at SHA-256
`3ce34a04b592131dbd0aefdb8692c21c5ab72e46f90f5f81a2aeffb9dbaeeaaf`.
The tracked copy adds only `artifact_role`, so its digest intentionally differs from the runtime
manifest.

| Artifact | Rows | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| SBIR `award_data.csv` | 219,500 | 394,456,822 | `73d646fc6883ed93b36d19518b0d9442a9ebae94c5b49ad5a7fcd6d3c2b872dd` |
| PR1 firm identity ledger | 34,426 | 62,253,221 | `272d566a665aca6262f073c75c585dcca4d9ed61ff52bb7f8197e95f50b80508` |
| PR1 exact candidate edges | 4,542 | 6,578,060 | `5677ffe3b96b8d103312a7cc99b1ef9d12d3a7ebf95032b5e24e4c53fbbc193a` |
| PR2 enriched candidates | 7,787 | 25,768,887 | `67779f952df4abb114488bbfcee3f3898758662f6898898ae6abd952bc71a1c7` |

Reproduce with the pinned runtime products and award snapshot present:

```bash
uv run python scripts/data/build_sbir_form_d_identity_candidates.py \
  --crosswalk-manifest data/processed/agency_private_capital/identity_crosswalk/sbir_form_d_identity_crosswalk.manifest.json \
  --crosswalk-manifest-sha256 71944c74dd7d6db05545757db85b812c56aa03fdb5cf25febdb23f13e50744c3 \
  --control-manifest data/processed/agency_private_capital/control_universe/form_d_control_universe.manifest.json \
  --control-manifest-sha256 3ce34a04b592131dbd0aefdb8692c21c5ab72e46f90f5f81a2aeffb9dbaeeaaf \
  --awards-csv data/raw/sbir/award_data.csv \
  --output-dir /tmp/sbir-form-d-candidate-enrichment-run-1 \
  --code-version c91f00ac55f95b4c0d0d468af8a82c2428f9be61
```

Repeat with `run-2`, then compare the directories with `diff -rq`.

## Gate decision and next validation step

Every row remains `candidate_unreviewed`; `same_legal_entity` is `null`.
`identity_accepted`, `exclusion_eligible`, `covariates_ready`, `matching_eligible`, and
`rate_eligible` are false. `complete_sbir_exclusion` and `ready_for_matching` are false, and
`exclusion_recall` remains `unknown`.

The next phase must construct outcome-blind review packets, obtain independent labels, adjudicate
disagreements, and estimate conservative precision separately for each exclusive route. Review of
generated candidates can estimate route precision, but not recall for SBIR–Form D links that no
route generated. Until that phase passes, this product cannot support filer/non-filer, capital
amount, leverage, matching, outcome, or rate claims.
