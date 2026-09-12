# EDGAR Event-Date Fidelity — Tasks

- [ ] 1. Persist per-filing EDGAR event records.
  - Verify: two filings from one filer with different accessions both survive
    serialization, with their own form, date, and mention type.
  - Requirements: 1.1

- [ ] 2. Derive type-anchored dates and settle the field-naming decision.
  - Verify: a profile with an old M&A mention and a recent unrelated mention
    cannot report a recent M&A date.
  - Requirements: 1.2–1.3

- [ ] 3. Migrate the two script consumers and re-label affected artifacts.
  - Verify: both scripts read the anchored field; regenerated artifacts record
    the change.
  - Requirements: 2.1–2.2
