# Materialization Semantic Fingerprints — Requirements

> **Lifecycle status:** Maintenance
> **Spec-file progress:** Not yet started
> Anchors inventory questions **B2–B3** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `pipelines`

**Research question anchor:** B2/B3 transition artifacts and their reproducible inputs
**Answers for:** pipeline engineers and reviewers of materialized transition data
**RQ complexity tier:** Relational / Inferential downstream; this spec governs lineage only

---

## Done when

Every Phase II, Phase III, pair, and survival materialization is accepted as current only when its
source bytes, normalized configuration, upstream outputs, and named transformation contract all
match the adjacent manifest; semantic code changes invalidate stale outputs deterministically.

---

## Background

Transition checks currently record generation time, paths, row counts, and selected source
provenance, but the Phase III classifier contract is not part of cache validity. A materialization
created shortly before a classifier correction therefore remained a valid-looking zero-row checks
artifact after the same input was classifiable. Input hashes alone cannot detect changed semantics.

## Requirements

### Requirement 1 — Named transformation contracts

**User story:** As a pipeline engineer, I want materializations to declare the behavior version
that produced them, so semantic changes cannot reuse stale outputs.

#### Acceptance Criteria

1. EACH transition stage SHALL declare a stable transformation contract name and version.
2. A change that can alter row inclusion, identity, dates, or values SHALL require a contract
   version change enforced by tests or review tooling.
3. A repository commit SHA MAY be recorded diagnostically but SHALL NOT be the sole semantic
   version because identical behavior must remain reproducible across builds.

### Requirement 2 — Complete deterministic fingerprint

**User story:** As a reviewer, I want one fingerprint covering every behavior-changing input, so I
can determine whether an output is reusable without inspecting the working tree.

#### Acceptance Criteria

1. THE fingerprint SHALL include transformation contract/version, normalized configuration,
   ordered upstream output hashes, and direct source hashes where applicable.
2. THE normalized payload used to compute the SHA-256 SHALL be emitted in the manifest.
3. Paths, timestamps, and dictionary insertion order SHALL NOT change the fingerprint unless they
   change source identity or configured behavior.

### Requirement 3 — Fail-closed cache validation

**User story:** As an operator, I want stale artifacts rejected before downstream use, so a checks
file cannot certify output produced by different semantics.

#### Acceptance Criteria

1. IF an output or manifest is missing, uses a legacy schema, or has a mismatched fingerprint,
   THEN cache validation SHALL require rematerialization.
2. Downstream stages SHALL bind the verified upstream output SHA and semantic fingerprint, not
   only its filesystem path.
3. Empty outputs SHALL receive the same fingerprint and validation treatment as non-empty outputs.

## Out of scope

- Making exploratory analyses citable or promoting evidence status.
- Hashing the entire repository or Python environment as a substitute for named contracts.
- Retrofitting every Dagster asset in one change; the first bounded slice is the phase-transition
  chain.
- Running or rematerializing live assets as part of implementation.

## Dependencies

- Existing transition `.checks.json` manifests — EXISTS
- Existing file SHA-256 and atomic JSON helpers — EXISTS
- Phase II, Phase III, pairs, and survival assets — EXISTS
