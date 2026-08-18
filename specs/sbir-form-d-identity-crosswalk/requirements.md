# SBIR ↔ Form D Identity Crosswalk — Requirements

- Research questions: F1, F2, F3
**Target epistemic tier:** `pipelines`
- Status: active
- Out of scope: identity acceptance; control exclusion; matching covariates; Form D amounts;
  downstream rates or outcomes; fuzzy, ML, LLM, affiliate, and acquisition matching

## Purpose

The maintained Form D control-universe producer emits a pinned broad issuer universe and
provisional CIK-level name evidence. This focused prerequisite turns the pinned full-history SBIR
award source into a deterministic firm ledger and emits exact-name *candidate* edges without
claiming that an SBIR component and a Form D issuer are the same legal entity. It serves the
identity gate for the private-capital comparison while deliberately leaving that gate open.

## Requirements

### 1. Pinned inputs and source validation

1.1. The producer SHALL require the expected SHA-256 of the Form D control-universe manifest and
SHALL fail before publication when the manifest bytes differ.

1.2. The producer SHALL accept only the versioned, complete, identity-only control-universe
manifest for the closed `2009Q1`–`2024Q4` source window. The upstream manifest's exclusion,
covariate, and matching gates SHALL remain false.

1.3. The producer SHALL resolve the broad issuer JSONL from the manifest and validate its safe
relative path, byte size, SHA-256, row count, CIK uniqueness, and issuer/filing identity contract.
That contract SHALL retain both street address lines as distinct evidence fields.

1.4. The producer SHALL validate the supplied full-history SBIR award CSV against the byte size,
SHA-256, and row count pinned in the control-universe manifest. Source changes without a new
manifest pin SHALL fail closed.

### 2. SBIR firm identity ledger

2.1. UEI, DUNS, and organization-name normalization SHALL reuse the repository's versioned
identity primitives: `normalize_uei`, `normalize_duns`, and
`CompanyNameProfile.ORGANIZATION_KEY_V1`.

2.2. Rows with valid identifiers SHALL form connected components using exact UEI/DUNS evidence
only. Names SHALL NOT connect two identifier-backed components.

2.3. A component with multiple UEIs, multiple DUNS values, or malformed nonblank identifier
evidence SHALL be retained and labeled `quarantined_conflict` with deterministic reasons. It
SHALL NOT be silently accepted as a resolved legal entity.

2.4. Rows with no valid UEI or DUNS SHALL receive a stable exact-name-key identity. Name-only rows
SHALL never be merged into an identifier-backed component, including when their normalized names
are equal.

2.5. Every nonblank-name SBIR source row SHALL occur in exactly one emitted ledger component.
Stable `sbir_firm_id` values SHALL be content-derived under the versioned
`sbir-firm-id-v1` contract and independent of input row order.

### 3. Atomic candidate edges

3.1. The producer SHALL compare every normalized SBIR component name with every Form D issuer
alias using exact equality under `ORGANIZATION_KEY_V1`.

3.2. Candidate output SHALL have exactly one row per `(sbir_firm_id, form_d_cik)` pair. When one
name maps to multiple CIKs, every CIK SHALL be emitted on its own edge. When one name occurs in
multiple SBIR components, every component SHALL retain its own edge.

3.3. Each edge SHALL retain the matching normalized names, SBIR source row numbers and raw names,
and Form D raw aliases and filing accession numbers. Evidence for one CIK SHALL never be pooled
onto another CIK's edge.

3.4. Every edge SHALL remain `candidate_unreviewed`, set `same_legal_entity` to unknown, and keep
identity, exclusion, matching, and rate eligibility false. The candidate contract SHALL contain no
Form D offering or sale amounts.

### 4. Publication and audit contract

4.1. The ledger and candidate-edge JSONLs SHALL be canonical, deterministically ordered, and
named with their full content SHA-256. Their schema and ID contracts SHALL be explicitly
versioned.

4.2. The producer SHALL build a complete release in a sibling staging directory and atomically
publish it as a directory replacement. If publication fails, the previous release SHALL be
restored byte for byte and temporary directories SHALL be removed.

4.3. A deterministic audit manifest SHALL pin all input and output hashes, sizes, and row counts;
record preservation and atomic-grain invariants; and declare every downstream gate false or
unknown. It SHALL also pin the producer source SHA-256 and contain no run timestamp or other
wall-clock value.

4.4. Re-running with identical inputs and producer bytes SHALL produce byte-identical artifacts
and manifest contents.

## Acceptance criteria

- A normalized name shared by two Form D CIKs produces two atomic candidate edges.
- A normalized name shared by two identifier-backed SBIR components does not merge those
  components and produces distinct edges.
- A DUNS bridge connecting different UEIs produces a retained quarantined component.
- A no-identifier row produces a stable name-key component separate from an identically named
  identifier-backed component.
- Manifest, broad issuer, or award CSV pin drift fails before publication.
- An identical rerun is byte-identical.
- An injected publication failure restores the prior release byte for byte.

## Non-claims

This producer does not identify a legal-entity match, authorize SBIR exclusion, establish control
eligibility, infer an affiliate relationship, choose a preferred CIK, attach capital amounts, or
support a comparison rate. Those decisions require separate reviewed contracts.
