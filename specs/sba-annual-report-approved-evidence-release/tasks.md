# SBA Annual-Report Approved Evidence — Tasks

## Gate phase

- [x] 1. Provide durable acquisition for all exact source bytes.
  - Verify: a clean environment retrieves the 394,636,989-byte export and all
    three report PDFs, then verifies every frozen SHA-256 and byte count before
    use.
  - Requirements: evidence-approval gate 1, 4.2

- [x] 2. Select, approve, and freeze the prospective fidelity design.
  - Verify: the design predates its evaluated extraction and records population,
    power, threshold, reconciliation, and stop rules.
  - Requirements: evidence-approval gates 2-4, 2.1-2.3

- [x] 3. Run the pre-run evidence audit.
  - Verify: the evidence auditor approves the estimand, independence, freeze
    history, threshold, mismatch categories, and claim boundary.
  - Requirements: evidence-approval gate 6, 1.1-1.4, 2.1-2.5

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
  - Requirements: evidence-approval gates 3-5

- [x] 9. Reconcile the materialization gate for the descriptive product.
  - Verify: historical-sample reproduction remains blocked and operational
    materialization is documented independently from evidence approval.
  - Requirements: operational governance

- [x] 10. Run the post-result evidence audit and named-reader review.
  - Verify: both records are in the packet and the reader correctly states the
    claim and non-claims without oral context.
  - Requirements: supporting review evidence, 4.3
  - Current state: the evidence audit authorized `validated`, and the final
    Revision 11 exact-byte evidence audit returned `GO`; its fresh cold
    named-reader review returned `BRIEF` with no remediation. Neither review
    authorized citation, materialization, merge, release, or tagging.

- [x] 11. Prepare the immutable release packet.
  - Verify: every packet file has a digest and the reproduction command works
    from a clean checkout.
  - Requirements: 3.1-3.4, 4.2
  - Current state: the validated packet is present in immutable tag `v0.18.0`.
    Repository citation metadata is maintained separately and does not determine
    evidence status.

- [x] 12. Request explicit approval before merging any release work.
  - Verify: no merge occurs without the repository owner's approval.
  - Requirements: release governance
  - Current state: the validated packet was merged and tagged as `v0.18.0`.
    Future merges still follow ordinary repository-owner approval.

- [ ] 13. Record one final pinned claim-approval review and promote the manifest.
  - Verify: the review approves the exact `permitted_claims` and limitations,
    its path and SHA-256 appear in `frozen_artifacts` and `claim_approval`,
    `claim_approval.claim_boundary_sha256` matches those fields, and
    `evidence_status: approved` passes the manifest and research-status guards.
  - Requirements: evidence-approval gate 6
