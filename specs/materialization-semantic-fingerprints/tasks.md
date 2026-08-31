# Materialization Semantic Fingerprints — Tasks

- [ ] 1. Add canonical semantic-fingerprint payload and validation helpers.
  - Verify: unit tests cover stable hashing and component-level mismatch reporting.
  - Requirements: 2.1–2.3

- [ ] 2. Declare and test transformation contracts for Phase II and Phase III assets.
  - Verify: a classifier-behavior fixture requires a version bump when output changes.
  - Requirements: 1.1–1.3

- [ ] 3. Bind Phase II/III manifests to source and configuration fingerprints.
  - Verify: stale, legacy, and empty-output cases fail closed or rematerialize.
  - Requirements: 2.1–2.3, 3.1, 3.3

- [ ] 4. Propagate verified lineage through pairs and survival outputs.
  - Verify: changing either upstream output invalidates both downstream stages.
  - Requirements: 3.1–3.2

- [ ] 5. Document migration without performing a live materialization.
  - Verify: focused tests, `make docs-check`, and `make lint-boundaries` pass.
  - Requirements: 3.1–3.3
