---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-08-09
Status: draft
---

# Form D possible-SBIR contamination candidate audit

> **Exploratory and non-citable.** This artifact is an unreviewed identity-audit
> queue. It is not a contamination estimate, does not change the provisional
> controls, and reports no treated-versus-control outcome.

## Materialization result

The follow-on screen compared all historical issuer aliases and location
evidence for the 307,344 provisional Form D control CIKs with the pinned SBIR
award history. It emitted 2,588 candidate pairs spanning 1,568 control CIKs.
Every candidate remains unreviewed and the producer applied **zero** additional
exclusions.

| Audit measure | Value |
| --- | ---: |
| Provisional control CIKs screened | 307,344 |
| Upstream exact-exclusion CIKs verified | 4,465 |
| Historical SBIR award rows | 219,500 |
| Eligible normalized SBIR names | 32,603 |
| Unreviewed candidate pairs | 2,588 |
| Provisional control CIKs represented in the queue | 1,568 |
| Strong-name route hits | 230 |
| State-supported route hits | 982 |
| ZIP-supported route hits | 1,464 |
| Additional exclusions applied | 0 |

Route counts overlap because a pair can satisfy more than one rule. They must
not be summed or interpreted as distinct firms. The 32,603 eligible SBIR names
exclude normalized keys shorter than six alphanumeric characters; the input
snapshot itself remains unchanged.

## Frozen candidate rules

The producer uses `organization-key-v1` name normalization and
`us-jurisdiction-strict-v1` state normalization. It evaluates every eligible
historical alias, state, and ZIP observed for each issuer; there is no top-k
cutoff.

1. **Strong name:** same two-character normalized prefix and ratio similarity
   at least 0.95.
2. **State supported:** same strict U.S. state, same prefix, and ratio similarity
   at least 0.85.
3. **ZIP supported:** exact valid ZIP5 and ratio similarity at least 0.80; no
   prefix agreement is required.

Pairs are deduplicated at `(CIK, normalized SBIR name)`. Ratio, token-sort, and
token-set similarities are retained as review evidence, but none can establish
identity. A stable candidate ID binds the contract version, CIK, and normalized
SBIR name.

## Interpretation boundary

This run contains no adjudication and therefore provides no precision, recall,
or contamination-rate estimate. Shared ZIP codes and similar organization
names can produce unrelated candidates. Missing geography does not count as
agreement, and geographic agreement does not convert a fuzzy name into an
identity decision.

The machine-readable manifest consequently preserves:

- `candidate_only=true`;
- `applied_exclusion_count=0`;
- `complete_sbir_exclusion=false`;
- `exclusion_recall="unknown"`;
- `identity_only=true`;
- `covariates_ready=false`; and
- `ready_for_matching=false`.

The original 307,344-row provisional control product remains unchanged. No
candidate in this queue may be removed from that product without a separate,
versioned adjudication decision.

## Product and provenance

The full [tracked research manifest](agency-private-capital-form-d-sbir-contamination-audit.manifest.json)
pins the upstream control-universe manifest, provisional controls, exact
exclusion ledger, SBIR award snapshot, frozen policies and thresholds, producer
commit, output hash, and invariant results.

| Product | Rows | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Possible-SBIR contamination candidates | 2,588 | 2,390,117 | `f7a10a24e7e55405508539466feb638debead67293e0724c39bb28315b9e09fd` |

The source products remain gitignored. Their pinned hashes are:

- provisional controls:
  `aaffebbda1ef3d2b1fe04e211b6973a027181d6840b03c12d4329a1649f31c75`;
- exact-exclusion ledger:
  `94cb5bc0eae682675f6e0015cc2c21b48411aba6429b6ef5e4cccfe769af38d3`;
- SBIR award CSV:
  `73d646fc6883ed93b36d19518b0d9442a9ebae94c5b49ad5a7fcd6d3c2b872dd`;
  and
- upstream control-universe manifest:
  `1777119114c4f7385dd09d6b60c603f2c5c59db765311255440513190d94b331`.

Two independent real-data builds produced the same content-addressed candidate
product. Reproduce after materializing the pinned control-universe inputs at
their default processed-data paths:

```bash
uv run python scripts/data/build_form_d_sbir_exclusion_candidates.py \
  --source-manifest \
  docs/research/agency-private-capital-form-d-control-universe.manifest.json \
  --awards-csv data/raw/sbir/award_data.csv
```

## Gate decision

This screen turns a broad fuzzy search into a bounded review queue, but it does
not close task 2.2. The next identity step must adjudicate candidate pairs and
incorporate higher-recall authoritative CIK or alias evidence, then rebuild and
validate the exclusion boundary. A validated SIC-to-NAICS-2 strategy and
symmetric FPDS, patent, and verified-M&A coverage remain separate prerequisites
for matching.
