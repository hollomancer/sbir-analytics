# Phase-Transition Report Grain — Tasks

- [ ] 1. Define and validate the row-per-Phase-II follow-up schema.
  - Verify: duplicate identifiers and incomplete event/censor rows fail closed.
  - Requirements: 1.1–1.3, 3.1–3.2

- [ ] 2. Move all headline reporter queries onto the follow-up frame.
  - Verify: incidence, latency, agency, and cohort fixtures share one denominator.
  - Requirements: 1.1–1.4

- [ ] 3. Add candidate-pair multiplicity diagnostics.
  - Verify: one-to-many and reused-contract fixtures emit the expected audit counts.
  - Requirements: 2.1–2.3

- [ ] 4. Version report keys and migrate downstream readers.
  - Verify: no pair-weighted metric remains under a headline transition label.
  - Requirements: 1.3–1.4, 2.3

- [ ] 5. Reconcile transition reporting documentation.
  - Verify: focused tests, `make docs-check`, and `make lint-boundaries` pass.
  - Requirements: 1.1–3.3
