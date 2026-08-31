# Contract Source-Field Preservation — Tasks

- [ ] 1. Verify and fixture the exact USAspending raw headers.
  - Verify: the fixture contains distinct research code/label, agency tiers, and descriptions.
  - Requirements: 1.1–1.4

- [ ] 2. Extend the canonical contract model and version its schema contract.
  - Verify: model serialization preserves each optional field without fallback.
  - Requirements: 2.1–2.3

- [ ] 3. Expand award-archive projection and row mapping.
  - Verify: CSV→model tests preserve all fields byte-for-byte after normalization.
  - Requirements: 1.1–1.4, 3.1

- [ ] 4. Bind projection and coverage metadata into source checks.
  - Verify: missing headers fail and coverage is emitted for every added field.
  - Requirements: 3.1–3.3

- [ ] 5. Migrate downstream readers without redefining legacy fields.
  - Verify: focused integration tests, `make docs-check`, and `make lint-boundaries` pass.
  - Requirements: 2.1–2.3
