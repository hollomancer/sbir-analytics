---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-08-10
Status: draft
---

# SBIR ↔ Form D identity-review instrument audit

> **Instrument only; non-citable.** This release freezes an outcome-blind,
> explicit-route-masked review sample. It contains no reviewer decisions, measured precision,
> accepted identity links, control exclusions, capital amounts, or outcomes.

## Materialization result

Producer commit `c8950ca18805899e345612b2bc284234f158bd4f` materialized the pinned
full-history inputs twice. The two directories were byte-identical. Their runtime manifests both
have SHA-256 `5c9fe331606e400f87fbb531bf18f486b0ed34f618ded03555c0cf704dd362f8`.
The real packet, private case map, and reviewer ledgers remain outside git; the tracked
[instrument manifest](agency-private-capital-sbir-form-d-identity-review-instrument.manifest.json)
publishes only their hashes, schemas, counts, and closed gates.

| Exclusive stratum | Candidate pairs | Eligible one-to-one pairs | Review cases |
| --- | ---: | ---: | ---: |
| Exact normalized name | 4,542 | 3,685 | 100 |
| Strong name | 271 | 110 | 100 |
| State supported | 1,162 | 283 | 100 |
| ZIP supported | 1,812 | 130 | 100 |
| **Total** | **7,787** | **4,208** | **400** |

The priority is exact → strong → state → ZIP, so the strata are mutually exclusive. Candidate
degrees are computed on the complete 7,787-pair graph before exclusions. The eligibility filter
removes 3,579 pairs in total: 3,560 have fanout in at least one direction and 36 belong to
quarantined SBIR components; those reasons overlap. The marginal fanout counts are 2,943
firm-to-multiple-CIK pairs and 2,533 CIK-to-multiple-firm pairs.

Within each eligible stratum, the producer orders stable edge IDs with a frozen SHA-256 domain and
takes the first 100. It then pools and independently reorders all 400 cases before assigning
`case_0001` through `case_0400`. Reversing and repinning the source candidate rows produces the
same packet and case-map bytes, hashes, and case IDs.

## Reviewer evidence boundary

The packet contains only each neutral case ID and two identity-history arrays. Organization A uses
raw SBIR organization names, addresses, and identity-only observation dates. The SBIR export's
`Contact Phone` is person-linked and is deliberately excluded. Organization B uses raw Form D
issuer aliases, addresses, issuer phone, filing dates, and incorporation jurisdiction/year.
Duplicate snapshots collapse deterministically while retaining first/last observation dates and
observation counts.

An aggregate privacy audit found 400 organization-A history snapshots and 837 organization-B
history snapshots. All 400 cases have evidence on both sides. Organization A has zero non-null
phone values; all 837 organization-B snapshots retain a Form D issuer phone. Recursive inspection
found no internal firm IDs, CIKs, accessions, routes, scores, amounts, outcomes, people, emails,
websites, or reviewer decisions in the packet.

| Private artifact | Rows | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Route-masked review packet | 400 | 522,314 | `15246841b62d0ed22823d9a013691c470c23e245822a7310f5b696ab07884695` |
| Source-bearing case map | 400 | 387,892 | `f2fbf66bfb61d3b31f0fa297b7ad71df2e72593f41767286fb83f50e2caf126a` |

The packet is outcome-blind and route-masked, not fully blinded: reviewers can sometimes infer
that names or locations agree from the evidence they must inspect. The separate private map
contains the edge, route, CIK, firm, and source lineage needed for later aggregation.

## Frozen human-review gate

Two distinct human reviewers must independently label every case as
`same_organization`, `different_organization`, or `insufficient_evidence`. A third, distinct
human adjudicator must label exactly the primary disagreements. Different and insufficient
decisions both count against the rule.

The evaluator reports raw agreement counts and a separate 95% Wilson interval for each exclusive
stratum. A route passes only when its lower bound is at least 0.90. With 100 cases, 96
`same_organization` decisions pass and 95 fail. There is no pooled headline precision.

No human labels exist in this release, so every
`exclusive_route_validation_passed` value remains false. Identity acceptance, complete SBIR
exclusion, covariate readiness, matching, rates, and outcomes remain closed. Candidate review can
estimate positive-candidate precision only; recall, specificity, and non-filer status remain
unknown.

## Reproduction

With the pinned private inputs present:

```bash
uv run python scripts/data/build_sbir_form_d_identity_review_sample.py \
  --candidate-manifest data/processed/agency_private_capital/identity_candidates/sbir_form_d_identity_candidates.manifest.json \
  --candidate-manifest-sha256 adf9dc5219861f8ca144da46ead0038577b28e9fb5d122492c403a6a4955de32 \
  --crosswalk-manifest data/processed/agency_private_capital/identity_crosswalk/sbir_form_d_identity_crosswalk.manifest.json \
  --crosswalk-manifest-sha256 71944c74dd7d6db05545757db85b812c56aa03fdb5cf25febdb23f13e50744c3 \
  --control-manifest data/processed/agency_private_capital/control_universe/form_d_control_universe.manifest.json \
  --control-manifest-sha256 3ce34a04b592131dbd0aefdb8692c21c5ab72e46f90f5f81a2aeffb9dbaeeaaf \
  --awards-csv data/raw/sbir/award_data.csv \
  --output-dir data/private/agency_private_capital/identity_review/v1 \
  --code-version c8950ca18805899e345612b2bc284234f158bd4f
```

Repeat in a second output directory and compare with `diff -rq`. PR3b begins only when two
genuinely independent human reviewers and a third disagreement adjudicator are available. PR4
must preserve linkage-error sensitivity even for a route that passes this gate.
