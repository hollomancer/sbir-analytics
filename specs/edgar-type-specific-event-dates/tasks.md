# EDGAR Type-Specific Event Dates — Tasks

- [ ] 1. Define the filing/event identity and canonical event schema.
  - Verify: fixtures retain two accessions from one filer without collision.
  - Requirements: 1.1–1.3

- [ ] 2. Persist normalized inbound-mention events with source lineage.
  - Verify: every event round-trips accession, form, type, and filing date.
  - Requirements: 1.1–1.3, 3.1

- [ ] 3. Derive type-specific profile summaries from the event artifact.
  - Verify: a newer unrelated mention does not change the acquisition-type date.
  - Requirements: 2.1–2.3, 3.2

- [ ] 4. Add conflict checks and legacy-profile migration guards.
  - Verify: ambiguous identity blocks publication and legacy generic dates are not retyped.
  - Requirements: 1.3, 3.1–3.3

- [ ] 5. Migrate capital-event consumers and document claim boundaries.
  - Verify: focused tests, `make docs-check`, and `make lint-boundaries` pass.
  - Requirements: 2.1–3.3
