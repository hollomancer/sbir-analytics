# SBIR ↔ Form D Organizational-Identity Review — Requirements

- Research questions: F1, F3
**Target epistemic tier:** `evidence`
- Status: active
- Out of scope: legal-entity certification; recall or negative-class validation; automatic identity
  acceptance; controls, matching, amounts, outcomes, and rates; people, emails, websites,
  affiliates, acquisitions, and successors

## Purpose

The enriched crosswalk is a deterministic candidate universe, not a set of accepted links. This
phase freezes an outcome-blind, explicit-route-masked review instrument for estimating whether
each exclusive candidate rule identifies the **same organization under the frozen administrative
evidence**. It also supplies a fail-closed evaluator for later, genuinely independent human
review. It does not claim legal identity and does not manufacture or publish human labels.

## Requirements

### 1. Pinned evidence and estimand

1.1. The instrument producer SHALL require external SHA-256 pins for the candidate-enrichment,
Phase 1 crosswalk, and Form D control runtime manifests. It SHALL reconcile their embedded pins
and validate the content, bytes, row counts, schema contracts, and closed downstream gates of the
candidate JSONL, firm ledger, broad issuer universe, and award CSV.

1.2. The estimand SHALL be `same organization under frozen administrative evidence`. The review
rubric SHALL define `different_organization` as affirmative contradictory evidence and SHALL
treat missing evidence or merely changed contact information as `insufficient_evidence`.

### 2. Frozen eligibility and sampling

2.1. Every candidate SHALL receive exactly one exclusive stratum under this priority:
`exact_normalized_name`, `strong_name`, `state_supported`, then `zip_supported`.

2.2. Candidates with `quarantined_conflict`, any firm linked to more than one candidate CIK, or
any CIK linked to more than one candidate firm SHALL be excluded from automatic route-validation
eligibility. The manifest SHALL report the reason-specific and union exclusion counts.

2.3. The producer SHALL select exactly 100 eligible cases per exclusive stratum using a frozen
SHA-256 rank. It SHALL fail closed if a stratum has fewer than 100 eligible cases. Only after all
four stratified selections SHALL it pool the 400 selected edges, order them by a separate SHA-256
rank, and assign neutral sequential case IDs.

### 3. Outcome-blind review packet

3.1. The packet SHALL contain one row per neutral case ID and the two organizations' complete
identity-only histories. Histories SHALL be reconstructed from all firm-ledger source records in
the pinned award CSV and all CIK-local filings in the pinned broad issuer universe.

3.2. A history SHALL contain unique identity snapshots, deterministically deduplicated while
retaining each snapshot's first observation date, last observation date, and observation count.
Allowed evidence is raw organization name, address, corporate phone, identity-only dates, and,
on the Form D side, incorporation jurisdiction and year.

3.3. The packet SHALL recursively exclude internal firm IDs, CIKs, accessions, route names,
similarity or confidence scores, amounts, outcomes, people, emails, and websites. It SHALL contain
no reviewer decision or source lineage. One identical packet is used by both primary reviewers.

3.4. A separate private case map SHALL retain case-to-edge, firm, CIK, exclusive-stratum, and
source-record/accession lineage. The packet and case map SHALL be canonical, content-addressed
JSONL files with fail-closed hashes. Real packet, map, and reviewer-ledger bytes SHALL remain out
of the public repository; only code, schemas, hashes, and aggregate audits may be committed.

### 4. Human-review evaluator

4.1. The evaluator SHALL require two separately pinned primary-review ledgers with distinct,
non-empty reviewer IDs and exactly one complete decision for every one of the 400 case IDs. The
only decisions SHALL be `same_organization`, `different_organization`, and
`insufficient_evidence`.

4.2. A separately pinned adjudication ledger SHALL contain exactly the primary-disagreement case
IDs, no more and no fewer, with one allowed decision per disagreement. Primary decisions SHALL be
preserved and never overwritten.

4.3. Final decisions SHALL equal the common primary decision for agreements and the adjudicator
decision for disagreements. Both `different_organization` and `insufficient_evidence` SHALL count
as failures.

4.4. The evaluator SHALL report raw agreement and disagreement counts and per-exclusive-stratum
Wilson 95% intervals only. It SHALL NOT report pooled headline precision. A stratum passes only
when its Wilson lower bound is at least `0.90`; with the frozen `n=100`, 96 same-organization
decisions pass and 95 fail.

4.5. The only validation gate the evaluator may emit is a route-keyed
`exclusive_route_validation_passed`. Identity acceptance, complete exclusion, covariate,
matching, and rate gates SHALL remain false, and recall SHALL remain unknown. The evaluator SHALL
be testable with synthetic ledgers but SHALL NOT publish real precision or infer human labels.

## Acceptance criteria

- Exclusive-route assignment is exhaustive and respects the frozen priority.
- Quarantine and either direction of fanout are excluded and reconciled before sampling.
- Two identical builds produce byte-identical packet, case-map, and manifest bytes.
- Case IDs reveal neither route nor source identifiers, and forbidden evidence cannot enter the
  packet recursively.
- Full SBIR and Form D identity histories deduplicate snapshots with correct observation spans and
  counts.
- Pin drift, malformed lineage, incomplete strata, incomplete reviews, duplicate reviewers,
  extra or missing adjudications, and unknown decisions fail closed.
- Synthetic evaluation proves the 96/100 pass and 95/100 fail boundaries without opening any
  other gate.

## Non-claims

The instrument does not validate legal identity, recall, specificity, non-filer status, complete
SBIR exclusion, full-corpus linkage accuracy, or later candidate cuts. Passing route estimates in
a later human-review release still require linkage-error sensitivity in the outcome analysis.
