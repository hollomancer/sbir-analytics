# Form D Amendment-Chain Deduplication — Tasks

- [ ] 1. Audit SEC amendment-link fields and quantify candidate-key collisions on a fixture cut.
  - Verify: the chosen policy and unresolved cases are documented before implementation.
  - Requirements: 2.1–2.3

- [ ] 2. Add accession-grain normalization and duplicate/conflict checks.
  - Verify: every filing retains source lineage and conflicting accessions fail closed.
  - Requirements: 1.1–1.3

- [ ] 3. Implement the named conservative chain resolver and resolution audit.
  - Verify: known chains resolve; ambiguous and orphan amendments remain unresolved.
  - Requirements: 2.1–2.3

- [ ] 4. Build as-of series amounts and grain-specific quality metrics.
  - Verify: cumulative amendment fixtures select one amount and independent series remain additive.
  - Requirements: 3.1–3.3

- [ ] 5. Migrate shared monetary consumers away from raw filing sums.
  - Verify: no headline capital path sums amendment rows directly.
  - Requirements: 3.1–3.4

- [ ] 6. Document legacy-artifact boundaries and run repository guards.
  - Verify: focused tests, `make docs-check`, and `make lint-boundaries` pass.
  - Requirements: 1.1–3.4
