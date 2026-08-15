# SBIR ↔ Form D Organizational-Identity Review — Tasks

- [x] 1. Freeze the estimand, route strata, eligibility exclusions, sample size, reviewer rubric,
  and non-claims.
  - Verify: requirements distinguish organizational evidence from legal identity and keep recall
    and every analytical gate closed.

- [x] 2. Implement the pinned deterministic review-instrument producer.
  - Verify: exactly 100 eligible cases per exclusive stratum produce a route-masked packet and a
    separate source-bearing private map with complete deduplicated identity histories.

- [x] 3. Implement the fail-closed human-review evaluator.
  - Verify: two complete distinct primary ledgers plus exact disagreement adjudication yield only
    per-route Wilson results and route validation gates.

- [x] 4. Add focused deterministic and failure-path tests.
  - Verify: priority, exclusions, hash ranks, masking, history deduplication, pin drift, review
    coverage, disagreement handling, and 95/96 boundaries are covered.

- [x] 5. Run focused pytest, Ruff, mypy, repository guards, and a repeat-build byte comparison.
  - Verify: all checks pass and no real labels, packets, maps, or precision results enter git.

- [x] 6. Materialize the real 400-case private instrument and publish only hashes plus aggregate
  audit metadata.
  - Verify: real packet and case-map bytes remain private; the tracked report contains no labels
    or precision claim. This task is owned by the release integrator, not the script implementation.

- [ ] 7. Obtain two independent human reviews and adjudicate disagreements in PR3b.
  - Verify: 800 independent primary judgments and every disagreement are genuinely human-labeled.
  This task is intentionally blocked on external human reviewers and cannot be completed in PR3a.
