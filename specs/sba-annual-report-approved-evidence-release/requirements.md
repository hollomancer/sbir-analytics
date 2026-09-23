# SBA Annual-Report Approved Evidence — Requirements

> **Lifecycle status:** Active release work
> **Spec-file progress:** Validated result recorded; final claim approval remains open
> Anchors inventory question **D1** in
> [docs/research-questions.md](../../docs/research-questions.md#d1-award-totals).

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

After a prospectively frozen fidelity test passes and one pinned final review
approves the claim boundary, the repository can mark one descriptive comparison
as approved evidence. The reader can retrieve the exact input,
verify its identity, reproduce every count, inspect every mismatch, and state
the non-claims without private context.

The validated comparison exists. This definition of done controls evidence
approval, not bibliographic citation or operational materialization.

## Background

The study is validated and not approved evidence. It is a current-vintage structural
comparison, not a reproduction of the historical SBA input. Its prospective
full-population fidelity validation matched 1,264 of 1,264 operands with an
exact point interval of `[1.0, 1.0]`. The earlier comparison bands were derived
after observing the same 632 cells, so they do not validate or promote the
study.

## Evidence-approval gates

All gates must close before the study becomes approved evidence:

1. The exact 394,636,989-byte export and the three exact SBA report PDFs are
   durably retrievable. Each source verifies against its frozen SHA-256 and byte
   count before use.
2. A validation design is approved and frozen before its evaluated run.
3. The validation tests source capture and transformation fidelity on an
   independent extraction or untouched eligible population. It does not test
   whether the post-hoc bands pass.
4. The validation result is confirmatory and records its interval or complete
   reconciliation, as appropriate.
5. `validation_result.threshold_met` is true.
6. One final review, pinned in the study manifest, approves the exact claim
   boundary and freeze history and confirms that the claim and non-claims are
   understandable without oral context.

An immutable release, citation metadata, repository-owner merge approval, and
operational materialization remain required where their own workflows call for
them. They do not strengthen or determine the study's evidence status.

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
4. WHEN the packet is published or cited, THE reference SHALL identify a tag or
   immutable archive, not a moving branch.

### Requirement 4 — Hostile-reading checks

**User story:** As a skeptical researcher, I want the packet to fail visibly
when its evidence changes, so that hidden drift cannot preserve the same claim.

#### Acceptance Criteria

1. CHANGING an input byte, source count, profile, frozen definition, comparison
   sidecar, or renderer output SHALL fail verification or change the recorded
   result and digest.
2. A clean checkout SHALL reproduce the packet using only documented access and
   setup steps.
3. THE final claim-approval review SHALL confirm that the claim and non-claims
   can be restated correctly without oral guidance.

## Dependencies

- `award-export-semantics` — MAINTENANCE
- `award-export-source-pipeline` — MAINTENANCE
- Durable access to all four exact source files — COMPLETE
- Approved prospective validation design and result — COMPLETE
- Pre-run and post-result evidence-auditor review — COMPLETE
- Public renderer, round trip, and mutation checks — COMPLETE
- Reader-comprehension review — COMPLETE (`BRIEF`; retained as supporting evidence)
- Final pinned claim-approval review — OPEN

## Out of scope

- A claim that the published SBA sample has been reproduced.
- A tolerance-band validation of the already observed 632 cells.
- Award-dollar equivalence or verdicts.
- The eight-year post-hoc extension as confirmatory evidence.
- Program effectiveness, Phase III, commercialization, ROI, M&A, or private
  capital conclusions.
- A generic comparison framework, dashboard, API, or graph interface.
