# SBIR ↔ Form D Candidate Enrichment — Design

## Data flow

```text
pinned Phase 1 runtime manifest ── ledger + exact atomic edges
               │
               ├── pinned SBIR award CSV ── source-record contact evidence
               │
pinned control runtime manifest ── broad Form D CIK/filing evidence
               │
               └── frozen exact/fuzzy name routes
                              ↓
             one enriched candidate per (sbir_firm_id, CIK)
                              ↓
            content-addressed JSONL + deterministic manifest
```

The module declares `EPISTEMIC_TIER = "pipelines"`. It generates and enriches a review universe;
it does not score confidence or accept identity.

## Inputs and validation

The CLI accepts a Phase 1 crosswalk manifest plus required SHA-256, the upstream control manifest
plus required SHA-256, the SBIR award CSV, an output directory, and a required full commit SHA.
Product filenames resolve only beside their manifest and must be safe single filenames. The
crosswalk's embedded upstream-manifest and award pins must equal the independently supplied pins.

The ledger supplies stable firm IDs, component status, normalized names, and the exact mapping
from CSV data-record ordinal to firm. The awards CSV is reparsed only to attach location and phone
evidence to those already frozen components; it cannot change component membership. The exact-edge
JSONL supplies the immutable exact pair set. The broad Form D JSONL is streamed once and validates
unique ordered CIKs, CIK-local filings, globally unique accessions, traceable aliases, and the
filing identity-field contract.

## Blocking and routes

For fuzzy-eligible SBIR names, two deterministic indexes avoid a Cartesian comparison:

- two-character alphanumeric name prefix; and
- strict ZIP5 observed on an award row carrying that normalized name.

Each Form D alias draws possible SBIR names from its prefix block and each issuer ZIP draws names
from its ZIP block. Unequal name pairs then apply exactly the three rules in the requirements.
Route counts may overlap. There is no top-k truncation; retrieval is exhaustive within the frozen
blocks and thresholds. Similarity calls go directly to the required RapidFuzz `3.14.3` backend;
the producer rejects a different or missing backend instead of changing algorithms silently.

Exact pairs are seeded from Phase 1 and are never inferred again. During the broad-issuer scan,
exact equality is reconstructed solely to prove that the seeded set is complete and unchanged.
Short exact names therefore survive even though short fuzzy names are ineligible.

## Evidence model

The candidate key and `edge_id` remain the Phase 1 pair-derived contract. Exact candidates embed
their original Phase 1 edge unchanged. Fuzzy candidates record the best qualifying name comparison
under a deterministic ratio/name/alias ordering while the route list is the union of every
qualifying comparison for that pair. A separate route-evidence map records the best comparison for
each emitted route; state and ZIP witnesses include their shared values and supporting lineage.
The exact route points to its selected nested Phase 1 witness. Name evidence includes the
supporting raw aliases, accessions, raw SBIR names, and source-record ordinals.

After a pair exists through exact or fuzzy name evidence, the producer intersects normalized
street line 1, city, strict state, strict ZIP5, and ten-digit U.S. phone histories. Each intersection
records the value and supporting source records/accessions. These contact maps are computed inside
one firm and one CIK; street, city, and phone indexes are never used for retrieval.

## Outputs and failure behavior

The release contains one content-addressed `sbir_form_d_identity_candidates.v2.<sha256>.jsonl` and
`sbir_form_d_identity_candidates.manifest.json`. Rows and keys use canonical JSON ordering. The
manifest records input products, frozen thresholds and normalizer contracts, pair/route/contact
counts, ambiguity counts, producer bytes, and explicit false decision gates.

The producer stages a complete sibling directory. First publication uses one atomic rename;
replacement uses the native macOS or Linux atomic directory-exchange primitive and fails closed
when that primitive is unavailable. Pin drift, unsafe paths, exact-pair mutation, source-record
disagreement, untraceable or cross-CIK filing evidence, forbidden fields, duplicate pairs, or
failed invariants abort publication. A failed exchange leaves the prior release byte for byte.

## Consequences

The result is deliberately broader than Phase 1 but remains only a finite review queue. Geography
and contact agreement may help later reviewers; it has no calibrated meaning until the blinded
adjudication phase evaluates predeclared rules on human labels.
