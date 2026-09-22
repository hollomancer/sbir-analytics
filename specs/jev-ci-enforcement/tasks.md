# Jev CI Enforcement Tasks

## Stage 0 — Deterministic contract gate

- [x] 0.1 Add the strict, versioned CI policy and report contracts.
  - Verify: malformed, duplicate, missing, and unknown cases fail.
  - Requirements: 1.1–1.5, 4.1–4.4.

- [x] 0.2 Add the offline annual-report enforcement command.
  - Verify: current decisions pass; status, blocker, and ruleset drift fail.
  - Requirements: 2.1–2.6, 4.1–4.5.

- [x] 0.3 Add the changed-file CI job and local Make target.
  - Verify: actionlint, repository guards, and workflow path tests pass.
  - Requirements: 3.1–3.3, 4.5.

- [x] 0.4 Verify the stacked pull request.
  - Verify: focused tests, `make lint`, `make lint-boundaries`, and hosted checks pass.
  - Requirements: all.
