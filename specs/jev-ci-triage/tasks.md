# Jev CI Failure Triage — Tasks

## Stage 0 — Hermetic boundary

- [x] 0.1 Register the exploratory pilot and freeze its Stage 0 exclusions.
  - Verify: `scripts/ci/check_epistemic_tiers.py` and repository hygiene tests pass.
  - Requirements: 5.1–5.5.

- [x] 0.2 Add strict failure-envelope and decision contracts.
  - Verify: focused validation tests pass.
  - Requirements: 1.5, 2.1–2.3.

- [x] 0.3 Parse and sanitize synthetic JUnit failures.
  - Verify: redaction, malformed-input, and truncation tests pass.
  - Requirements: 1.1–1.4.

- [x] 0.4 Add the fake transport and transport-neutral classifier.
  - Verify: a hermetic test returns a typed decision without network access.
  - Requirements: 2.4.

- [x] 0.5 Add deterministic policy and rendering.
  - Verify: threshold-boundary and byte-stability tests pass.
  - Requirements: 3.1–3.4, 4.1–4.3.

## Stage 1 — Offline evaluation

- [ ] 1.1 Record approved TypeSafe API, retention, and disclosure terms.
  - Verify: design amendment names the reviewed documents and remaining restrictions.
  - Requirements: 5.1, 5.2.

- [ ] 1.2 Build and human-label a private historical failure corpus.
  - Verify: the corpus has a frozen taxonomy, split, and label-adjudication record.
  - Requirements: 2.1–2.3.

- [ ] 1.3 Run a private held-out evaluation and write a keep-or-stop memo.
  - Verify: the memo reports routing accuracy, unsafe retry rate, calibration,
    availability, latency, and sanitizer rejection rate.
  - Requirements: 3.1–3.4.

## Stage 2 — Non-blocking shadow

- [ ] 2.1 Add an authenticated Jev transport only after task 1.1 passes.
  - Verify: mocked timeout, authentication, schema-error, and rate-limit tests pass.
  - Requirements: 2.1–2.4, 5.1, 5.2.

- [ ] 2.2 Add structured failure artifacts for selected unit-test shards.
  - Verify: successful and failed synthetic workflow runs upload bounded artifacts.
  - Requirements: 1.1–1.5.

- [ ] 2.3 Add a non-blocking, internal-PR-only shadow job.
  - Verify: forks and security failures make no Jev call; Jev failure leaves CI unchanged.
  - Requirements: 3.4, 5.3, 5.4.

- [ ] 2.4 Evaluate at least 30 prospective failed runs.
  - Verify: a held-out decision memo approves expansion, revision, or removal.
  - Requirements: 5.5.

## Stage 3 — Optional bounded action

- [ ] 3.1 Decide whether one automatic retry is justified.
  - Verify: a separate approved change records thresholds, exclusions, rollback,
    and a false-retry ceiling.
  - Requirements: 3.1–3.4, 5.5.
