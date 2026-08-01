# Schema-verified transition source materialization

**Status:** prerequisite source layer; no Phase III census criteria or results live here.

## Purpose

Produce reproducible USAspending contract actions and Phase II prior-award rows whose
schema, identifiers, grain, and source files are independently auditable. This layer is
useful to every transition consumer; the label-free census is one downstream consumer,
not the source of its parsing rules.

## Why the prior path was insufficient

The legacy extractor selected a guessed dump member and interpreted fields through fixed
positions associated with an older `transaction_normalized` layout. It could not prove
that the values exposed as FPDS research coding, NAICS/PSC, transaction identity, or award
identity came from those canonical columns in a particular dump. The legacy Phase II
collapse also used bare PIID/input order, so repeated actions could change the chosen end
date and equal PIIDs from different award contexts could collide.

## Source contracts

### USAspending

- Resolve `rpt.transaction_search` (or its FPDS partition) from the PostgreSQL archive
  TOC and schema rather than a hard-coded member number.
- Read the ordered `COPY` column list emitted by `pg_restore`; fail if required columns
  are absent or a serialized row has a different field count.
- Preserve authoritative `research`, NAICS, PSC, UEI, generated award ID, transaction ID,
  action date, signed obligation, agency, and competition fields.
- Select vendor candidates with a bounded-memory prefilter, then revalidate every emitted
  row in Python. The prefilter is an execution optimization, not an inclusion rule.
- Bind archive relation/member/TOC fingerprints, vendor-filter hash, extraction audit
  statistics, output shape, and output SHA-256 in an adjacent checks manifest. Publication
  is atomic and a changed input fails closed.

### SBIR.gov

- Read the complete declared CSV row and collapse only exact duplicates across every
  source field.
- Preserve the raw source identifier. When a base identifier is missing or repeats within
  a phase, derive the canonical row ID from the complete source-row SHA-256 rather than
  selecting by input order.
- Bind the source file, ordered schema, duplicate/collision audit, output shape, and output
  SHA-256 in an adjacent checks manifest.

### Phase II award grain

- Require generated award and transaction identifiers on federally coded Phase II rows.
- Collapse actions deterministically by valid action date and transaction ID; use the
  representative action's current performance end, the earliest action as award date,
  and the signed sum of Phase II-coded obligations.
- Reconcile SBIR.gov and federal rows only through an exact normalized raw source ID when
  the relationship is one-to-one. Ambiguity or conflicting taxonomy fails closed.

## Outputs

- `data/transition/contracts_ingestion.parquet` and `.checks.json`
- `data/processed/phase_iii_census_sbir_awards.parquet` and `.checks.json`
- `data/processed/phase_ii_awards.parquet` and `.checks.json`

Paths are configurable; the manifests bind the selected inputs to the exact outputs.

## Non-goals

This layer defines no Phase III census criterion, score, weight, similarity rule,
threshold, classifier, or firm-to-contract join. It does not modify the transition scorer
or claim that any extracted contract is statutory Phase III. Those decisions belong to
downstream, separately reviewed analyses.
