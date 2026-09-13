# SBIR Federal Spending vs Form D Private Capital (2009–2024)

**Audience:** F-area analysts, investor researchers, and policy staff studying
program-wide private-capital leverage.
**Evidence status:** retired; no current numerical result and not approved for citation.
**Study contract:** [`studies/form-d-fundraising`](../../studies/form-d-fundraising/study.yaml).
**Current tier rule:** `corroborated-person-v2`.

## Result status

The former tables and headline estimates are withdrawn. They were computed from a local,
gitignored Form D corpus scored under the historical `person-or-zip-v1` rule, where a fuzzy
person-name hit alone could reach high. The repository does not contain the input bytes needed to
prove a complete v2 rebuild, so those numbers cannot be relabeled as v2 results.

There is no current high-only or high-plus-medium leverage estimate. There are also no current
agency, year, security-type, fill-rate, pathway-cohort, or PIF-exposure results. Downstream reports
that used the old cohort are historical v1 artifacts until rebuilt from one pinned v2
materialization.

## Why the study was retired

Realistic pairs of distinct people can clear the person similarity threshold. Raising the
threshold does not separate real matches from collisions, so `corroborated-person-v2` changes the
tier rule:

| Tier | Current record-level rule |
|---|---|
| High | Exact ZIP, or person score at least 0.7 together with exact ZIP or state overlap |
| Medium | Person hit without corroboration, state overlap alone, or missing state evidence |
| Low | No person/ZIP hit and an observed state mismatch |

New confidence objects persist `match_confidence.rule_version`. Consumers supporting this study
reject unversioned and mixed-version records.

## Offline migration

Existing detail rows can be re-tiered without contacting the SEC:

```bash
python scripts/data/rescore_form_d_details.py \
  --input data/form_d_details.jsonl \
  --output data/form_d_details.corroborated-person-v2.jsonl
```

The command reads stored person, address, and state scores, writes deterministically, and replaces
the target atomically. It reports the before/after tier distribution plus the number of records
whose confidence inputs may span filings or CIKs. The archived fetcher's `--resume` mode refuses a
stale checkpoint instead of silently skipping its v1 rows.

This migration changes only the named Boolean tier rule. It is not a fresh source fetch and it is
not identity validation.

## Filing and CIK limitation

The historical detail producer pooled people, states, ZIPs, dates, and incorporation evidence
across all Form D filings attached to one SBIR company record. The filings can span multiple CIKs.
A stored person-plus-state conjunction therefore does not prove that both signals came from the
same filing or issuer.

The v2 PIF cross-link audit now:

- treats person-plus-state/no-ZIP as a distinct valid-v2 profile instead of person-only;
- retains both person and CIK link types for the same company pair;
- treats shared CIK and aggregate signal scope as review flags; and
- emits a review queue, not a claim that the other high-tier records are trustworthy.

No bootstrap interval can absorb this identity uncertainty automatically. Firm resampling and
match validity are different error sources.

## Intended analysis after the gate reopens

The intended estimand remains two descriptive ratios based on Form D `totalAmountSold` for
2009–2024:

1. Form D dollars for matched firms divided by all SBIR.gov award dollars in the window.
2. Form D dollars for matched firms with in-window SBIR awards divided by SBIR.gov dollars for that
   same subset.

The analysis will continue to report high and high-plus-medium filters and a seed-42, 1,000-draw
firm bootstrap. It will not describe either ratio as a lower bound: identity false positives and
filing aggregation can move the numerator up, while missed and non-Form-D capital can move it
down.

## Rebuild gates

Before any number returns to this page:

1. Pin the complete Form D and SBIR inputs by SHA-256, size, and row count.
2. Apply `corroborated-person-v2` to the complete corpus and verify exact row coverage and a single
   persisted rule version.
3. Score at a declared filing/issuer grain, or quarantine and quantify all cross-filing and
   multi-CIK confidence records.
4. Define and enforce accession and amendment-chain aggregation so one filing is not credited to
   multiple firms or counted again as a restatement.
5. Complete realistic person-collision and PIF/CIK identity review on the pinned output.
6. Rebuild every dependent result, record output hashes, amend/refreeze the study, and only then
   reconsider its evidence status.

`scripts/data/bootstrap_form_d_leverage_ci.py` enforces the closed study gate and will not produce
a replacement result until the manifest is reopened after those conditions are met.
