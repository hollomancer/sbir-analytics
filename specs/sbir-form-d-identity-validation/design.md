# SBIR ↔ Form D Organizational-Identity Review — Design

## Release split

PR3a freezes the review instrument and a synthetic-test evaluator. It publishes no reviewer
labels and no measured precision. PR3b will be a separate release containing two independent
human reviews and disagreement adjudication. Without those humans, work stops after PR3a.

## Data flow

```text
pinned candidate v2 JSONL ── exclusive strata + fanout/quarantine eligibility
          │
          ├── SHA rank: 100 per stratum ── pool/rerank ── neutral case IDs
          │
pinned firm ledger + award CSV ── complete organization-A histories
pinned broad issuer universe   ── complete organization-B histories
          │
          ├── route-masked review packet (private, content addressed)
          └── source-bearing case map     (private, content addressed)

two primary ledgers + disagreement-only adjudication ledger
          └── per-exclusive-route Wilson report, all other gates closed
```

The builder declares `EPISTEMIC_TIER = "pipelines"`; it deterministically constructs an
instrument. The evaluator declares `EPISTEMIC_TIER = "evidence"`; it measures only the pinned
exclusive route rules once genuine human ledgers exist and imports no lower-tier analysis code.

## Input validation

The builder accepts externally pinned candidate, crosswalk, and control manifests plus the
pinned award CSV. Safe single-filename product references resolve beside their owning manifests.
The supplied manifests must match the candidate manifest's embedded SHA and byte pins, and their
ledger, broad-universe, and award pins must agree. Every large product is streamed under a
before/after file-stability check and validated against its recorded SHA, bytes, and rows.

Candidate rows remain atomic `(sbir_firm_id, CIK)` pairs under the v2 candidate contract. The
builder accepts those unique pairs in any row order and validates stable edge IDs, allowed routes,
component status, and closed decision gates before using them.

## Eligibility and deterministic sampling

The first present member of the priority list `exact_normalized_name > strong_name >
state_supported > zip_supported` is the exclusive stratum. Fanout is computed over the entire
pinned candidate universe before exclusions. A row is eligible only if its component is not
quarantined and both its firm and CIK have candidate degree one.

Within each stratum, candidates sort by `SHA256(rank-domain, edge_id)` and the first 100 are
selected. The 400 selected edges then sort by `SHA256(pool-order-domain, edge_id)`. Sequential IDs
`case_0001` through `case_0400` are assigned only in that pooled order, so neither the ID nor
packet position encodes a route. Reordering and repinning the same candidate pairs can change the
runtime manifest's input pins but cannot change the packet or case-map bytes.

## Identity-history reconstruction

For each selected firm, every ledger source-record ordinal is retrieved from the award CSV. A
snapshot contains the trimmed raw organization name and address fields; proposal-award date is
the observation date, with award year as a bounded fallback. PI/contact
names and phones, emails, websites, award titles, amounts, and outcomes are never read into the
packet. In particular, the pinned award export has `Contact Phone` but no reliably corporate phone
field, so organization-A snapshots intentionally leave `organization_phone` null.

For each selected CIK, every CIK-local broad-universe filing contributes the trimmed raw issuer
aliases, address fields, issuer phone, incorporation jurisdiction, and incorporation year, with
filing date as the observation date. Accessions and offering/outcome fields remain only source
lineage in the private map or are discarded.

Snapshots deduplicate by their canonical identity fields, excluding observation date. Each
unique snapshot records its first and last observation date and count. Missing fields stay null;
they are not imputed. Packet rows expose only `case_id`, `organization_a_history`,
`organization_b_history`, and frozen schema/contract markers. A recursive key denylist and a
recursive value check for explicit route tokens run before publication.

The private case map records case ID, stable edge ID, source firm/CIK, exclusive stratum,
selection and pooled ranks, the original route set, and complete source-record/accession lineage.
It is never embedded in the reviewer packet.

## Publication

Canonical JSON uses sorted keys and compact separators. Packet and map filenames include the
SHA-256 of their exact bytes. A deterministic manifest pins inputs, producer bytes/commit,
outputs, exclusion counts, stratum populations, sample counts, schemas, rank domains, and closed
gates. Files are written to temporary siblings and moved into place only after their expected
content hash is known. Existing content-addressed bytes must match exactly; otherwise publication
fails. This one-time artifact flow intentionally does not reproduce PR2's directory-exchange
framework.

## Evaluation

Reviewer ledger rows contain `case_id`, `reviewer_id`, and one allowed decision. Each primary
ledger must cover the manifest's complete case set once, and the two ledger-level reviewer IDs
must differ. The adjudication ledger must cover exactly disagreements. Agreements preserve the
common primary decision; disagreements append an adjudicated final decision without changing
either original.

The evaluator calculates per-exclusive-stratum successes and a Wilson 95% interval using the
same formula and z constant as the existing agency-private-capital outcome utility. Importing that
utility would execute the Dagster asset package and is not a clean script boundary, so the tiny
dependency-free formula is kept local and regression-tested at the 95/96 boundary. The output has
no pooled precision and no accepted pair ledger. Only the four
`exclusive_route_validation_passed` flags may become true; every analytical gate remains closed
and recall remains unknown.
