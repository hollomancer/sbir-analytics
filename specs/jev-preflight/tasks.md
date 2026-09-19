# Jev Preflight Tasks

## Stage 0 — Deterministic vertical slice

- [x] 0.1 Add strict claim, evidence, readiness, and shadow-response contracts.
  - Verify: model validation and extra-field tests pass.
  - Requirements: 1.1–1.4, 2.1.

- [x] 0.2 Implement the versioned deterministic readiness engine.
  - Verify: one fixture for each status and precedence tests pass.
  - Requirements: 2.1–2.7.

- [x] 0.3 Add the SBA annual-report adapter and two claim contracts.
  - Verify: reproduction returns `NARROW`; structural check returns `GO`.
  - Requirements: 3.1–3.5.

- [x] 0.4 Add stable JSON and Markdown output.
  - Verify: repeated runs are byte-identical.
  - Requirements: 1.4, 2.7, 3.1.

## Stage 1 — Frozen evaluation

- [x] 1.1 Add the four-status synthetic matrix and offline evaluator.
  - Verify: all cases match and synthetic output is non-citable.
  - Requirements: 4.1–4.5.

- [x] 1.2 Add fake and live Jev transports with strict response validation.
  - Verify: fake, authentication, timeout, and schema-error tests pass.
  - Requirements: 5.1–5.6.

- [x] 1.3 Run a private live shadow against the matrix and annual-report cases.
  - Verify: save the result outside the repository and report disagreements.
  - Requirements: 5.1–5.6.

## Later, separate PR

- [ ] 2.1 Decide whether a non-blocking CI application is justified.
  - Verify: a separate approved spec names changed-file scope and failure behavior.
