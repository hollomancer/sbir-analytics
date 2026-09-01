# SEC Source Fidelity — Tasks

- [ ] 1. Audit the SEC Form D amendment chain key in a notebook.
  - The `021-…` file number is absent from the codebase and from `FormDFiling`.
    Establish where it can be sourced before any implementation task is written.
  - Verify: a notebook showing an original and its amendments grouped by the
    proposed key against real filings.
  - Requirements: 3.1

- [ ] 2. Persist per-filing EDGAR event records.
  - Verify: two filings from one filer with different accessions both survive
    serialization, with their own form, date, and mention type.
  - Requirements: 1.1

- [ ] 3. Derive type-anchored dates and settle the field-naming decision.
  - Verify: a profile with an old non-M&A mention and a recent unrelated mention
    cannot report a recent M&A date.
  - Requirements: 1.2–1.3

- [ ] 4. Migrate the two script consumers and re-label affected artifacts.
  - Verify: both scripts read the anchored field; regenerated artifacts record
    the change.
  - Requirements: 2.1–2.2

- [ ] 5. Replace the interim Form D lower bound with exact chain collapse.
  - Blocked on task 1.
  - Verify: an original plus two restating amendments reports the final
    restatement, and `offering_count` counts one offering.
  - Requirements: 3.1–3.3
