# SBA Annual-Report Structural Comparison Release — Requirements

> **Lifecycle status:** Gated backlog
> **Spec-file progress:** Design only; implementation not authorized
> Anchors inventory question **D1** in
> [docs/research-questions.md](../../docs/research-questions.md#d1-descriptive-tier-1).

**Target epistemic tier:** `evidence`

**Research question anchor:** D1 — award totals by state, agency, and phase
**Answers for:** policy analysts and SBIR program managers
**RQ complexity tier:** Descriptive
**Declared estimand:** For FY2020-FY2022, the cell-by-cell difference between
SBA Annual Report award counts and counts produced from the exact 2026-09-17
SBIR.gov export under `EXPORT_ROW_V1`, `AWARD_YEAR_FIELD_V1`, and the frozen
jurisdiction rules. The estimand is wrong if either source is transcribed
incorrectly, the pinned export is unavailable or changed, or a declared rule is
not applied as written.

## Done when

After a prospectively frozen fidelity test passes, an external reader can cite
one released descriptive comparison. The reader can retrieve the exact input,
verify its identity, reproduce every count, inspect every mismatch, and state
the non-claims without private context.

This definition of done does not authorize implementation while the gates below
remain closed.

## Background

The existing study is reproducible and non-citable. It is a current-vintage
structural check, not a reproduction of the historical SBA input. Its comparison
bands were derived after observing the same 632 cells, so they cannot validate
or promote the study.

## Publication gates

All gates must close before the study becomes citable:

1. The exact 394,636,989-byte export is durably retrievable and verifies as
   SHA-256 `aed146eab56f370c9f3fe7f562475e3eedfc61cca2eba112c830fac6f73bf38a`.
2. A validation design is approved and frozen before its evaluated run.
3. The validation tests source capture and transformation fidelity on an
   independent extraction or untouched eligible population. It does not test
   whether the post-hoc bands pass.
4. The validation result is confirmatory and records its interval or complete
   reconciliation, as appropriate.
5. `validation_result.threshold_met` is true.
6. An evidence auditor approves the claim boundary and freeze history.
7. The current closed materialization gate is reconciled for this descriptive
   product without reopening the blocked historical-sample reproduction claim.
8. A named outside reader completes the public packet without oral context.

## Requirements

### Requirement 1 — Frozen descriptive claim

**User story:** As a policy analyst, I want one precise permitted claim, so that
I can quote the comparison without implying official-source equivalence.

#### Acceptance Criteria

1. THE claim SHALL identify FY2020-FY2022, the 2026-09-17 export, and the
   declared count rules.
2. THE claim SHALL report observed differences, not a pass/fail verdict from the
   existing post-hoc bands.
3. THE claim SHALL state that it is a current-vintage structural comparison,
   not a reproduction of the publication-era SBA input.
4. THE adjacent non-claims SHALL exclude source certification, dollar
   equivalence, commercialization outcomes, program effects, M&A linkage, and
   repository-wide trust.

### Requirement 2 — Prospective fidelity validation

**User story:** As an SBIR program manager, I want an independent fidelity test,
so that transcription and transformation errors are distinguishable from source
disagreement.

#### Acceptance Criteria

1. BEFORE the evaluated run, THE study SHALL freeze the eligible units,
   extraction method, reconciliation rules, decision threshold, and failure
   response.
2. THE validation population SHALL be independent of the implementation under
   test or untouched when the design is frozen.
3. THE decision threshold SHALL measure source and transformation fidelity. It
   SHALL not measure agreement with the post-hoc comparison bands.
4. EVERY unmatched or unequal cell SHALL remain `unresolved` unless direct
   evidence supports a narrower mismatch category.
5. Dollar differences SHALL not affect count classifications.

### Requirement 3 — Release packet

**User story:** As a policy analyst, I want a frozen study packet, so that I can
reproduce and challenge the result from a stable release.

#### Acceptance Criteria

1. THE packet SHALL contain the study contract, exact source metadata, frozen
   validation design and result, machine-readable comparison, generated public
   rendering, environment lock, checksums, one reproduction command, review
   records, known limits, and permitted citation text.
2. THE rendering SHALL be generated from the machine-readable comparison and a
   registered sidecar. Manual result edits SHALL fail the round-trip check.
3. THE packet SHALL expose count cells and mismatch evidence. It SHALL suppress
   dollar verdicts.
4. THE release SHALL cite a tag or immutable archive, not a moving branch.

### Requirement 4 — Hostile-reading checks

**User story:** As a skeptical researcher, I want the packet to fail visibly
when its evidence changes, so that hidden drift cannot preserve the same claim.

#### Acceptance Criteria

1. CHANGING an input byte, source count, profile, frozen definition, comparison
   sidecar, or renderer output SHALL fail verification or change the recorded
   result and digest.
2. A clean checkout SHALL reproduce the packet using only documented access and
   setup steps.
3. A named outside reader SHALL be able to restate the claim and non-claims
   correctly without oral guidance.

## Dependencies

- `award-export-semantics` — ACTIVE
- `award-export-source-pipeline` — ACTIVE
- Durable access to the exact pinned export — BLOCKED
- Approved prospective validation design — BLOCKED
- Evidence-auditor approval — BLOCKED

## Out of scope

- A claim that the published SBA sample has been reproduced.
- A tolerance-band validation of the already observed 632 cells.
- Award-dollar equivalence or verdicts.
- The eight-year post-hoc extension as confirmatory evidence.
- Program effectiveness, Phase III, commercialization, ROI, M&A, or private
  capital conclusions.
- A generic comparison framework, dashboard, API, or graph interface.
