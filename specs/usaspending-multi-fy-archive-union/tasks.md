# USAspending Multi-FY Contract Archive Union — Tasks

- [ ] 1. Add fiscal-year-aware archive resolution and typed archive metadata.
  - Verify: resolver unit tests cover ordering, revision selection, and missing years.
  - Requirements: 1.1–1.3

- [ ] 2. Extend archive extraction to stream a declared archive sequence.
  - Verify: two-partition fixture emits the union at transaction grain.
  - Requirements: 2.1

- [ ] 3. Add deterministic cross-partition transaction reconciliation.
  - Verify: identical repeats collapse and conflicting repeats fail closed.
  - Requirements: 2.2–2.3

- [ ] 4. Version the manifest and bind the complete archive set to cache validity.
  - Verify: adding, removing, or replacing one fiscal partition invalidates the cache.
  - Requirements: 3.1–3.3

- [ ] 5. Document the fiscal-year configuration and scalar-manifest migration.
  - Verify: focused tests, `make docs-check`, and `make lint-boundaries` pass.
  - Requirements: 3.2–3.3
