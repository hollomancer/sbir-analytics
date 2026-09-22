# SBA Annual-Report Structural Comparison Release — Tasks

## Gate phase

- [x] 1. Provide durable acquisition for all exact source bytes.
  - Verify: a clean environment retrieves the 394,636,989-byte export and all
    three report PDFs, then verifies every frozen SHA-256 and byte count before
    use.
  - Requirements: publication gate 1, 4.2

- [x] 2. Select, approve, and freeze the prospective fidelity design.
  - Verify: the design predates its evaluated extraction and records population,
    power, threshold, reconciliation, and stop rules.
  - Requirements: publication gates 2-4, 2.1-2.3

- [x] 3. Run the pre-run evidence audit.
  - Verify: the evidence auditor approves the estimand, independence, freeze
    history, threshold, mismatch categories, and claim boundary.
  - Requirements: publication gate 6, 1.1-1.4, 2.1-2.5

## Implementation phase

- [x] 4. Add only the study-manifest fields required by the approved design.
  - Verify: schema and negative tests pass without a generic comparison API.
  - Requirements: 2.1-2.5, 3.1

- [x] 5. Correct the study-owned count classification and generate the
  machine-readable comparison.
  - Verify: dollars cannot affect count classifications; unsupported categories
    remain unresolved.
  - Requirements: 1.2, 2.4-2.5, 3.3

- [x] 6. Build the public renderer and register its sidecar round trip.
  - Verify: regeneration is byte-stable and manual edits fail the check.
  - Requirements: 3.1-3.3

- [x] 7. Add clean-replay and mutation tests.
  - Verify: all six required mutations fail or visibly change the result.
  - Requirements: 4.1-4.2

- [x] 8. Run the frozen validation and record the result.
  - Verify: the manifest includes the frozen design digest, complete result,
    interval or reconciliation, confirmatory status, and threshold outcome.
  - Requirements: publication gates 3-5

- [x] 9. Reconcile the materialization gate for the descriptive product.
  - Verify: historical-sample reproduction remains blocked; only the reviewed
    structural-comparison product can advance.
  - Requirements: publication gate 7

- [x] 10. Run the post-result evidence audit and named-reader review.
  - Verify: both records are in the packet and the reader correctly states the
    claim and non-claims without oral context.
  - Requirements: publication gates 6 and 8, 4.3
  - Current state: the evidence audit authorized `validated`, and the final
    Revision 11 exact-byte evidence audit returned `GO`; its fresh cold
    named-reader review returned `BRIEF` with no remediation. Neither review
    authorized citation, materialization, merge, release, or tagging.

- [ ] 11. Prepare the immutable release packet and citation metadata.
  - Verify: every packet file has a digest and the reproduction command works
    from a clean checkout.
  - Requirements: 3.1-3.4, 4.2
  - Current state: the validated packet and clean replay are ready; final
    citation metadata is intentionally withheld until an actual immutable tag
    exists.

- [x] 12. Request explicit approval before merging any release work.
  - Verify: no merge occurs without the repository owner's approval.
  - Requirements: release governance
  - Current state: approval was requested after the draft PR became green. No
    approval has been received. The PR remains draft and unmerged.
