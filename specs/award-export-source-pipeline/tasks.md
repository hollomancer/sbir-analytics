# Award Export Source Pipeline — Tasks

- [ ] 1. Inventory raw readers, provenance helpers, and active consumers.
  - Verify: the design records every active reader and why it is or is not in
    this migration.
  - Requirements: 1.4, 4.5

- [ ] 2. Refactor the existing exact parser into the canonical extractor path.
  - Verify: Phase II parser and materialization tests remain byte-identical.
  - Requirements: 1.1-1.4

- [ ] 3. Add pin-before-use verification.
  - Verify: valid fixture loads; missing sidecar, byte tamper, size mismatch,
    row-count mismatch, and schema mismatch each fail before use.
  - Requirements: 2.1-2.5

- [ ] 4. Migrate the SBA study to the verified raw reader and named profiles.
  - Verify: golden analytical values match; result paths are portable; a guard
    rejects direct CSV reading in the study.
  - Requirements: 4.1-4.5

- [ ] 5. Implement the new-capture dated-vintage policy.
  - Verify: a new capture lands atomically; an overwrite is refused unless all
    bytes and metadata match.
  - Requirements: 3.1-3.4

- [ ] 6. Reconcile docs and run repository checks.
  - Verify: focused tests, tier boundaries, spec registry, formatting, and type
    checks for touched modules pass.
  - Requirements: all

- [ ] 7. Write a separate migration plan for existing storage.
  - Verify: the plan lists consumers and live-host authorization needs. It does
    not move data.
  - Requirements: 3.4
