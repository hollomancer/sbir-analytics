# SBIR ↔ Form D Candidate Enrichment — Tasks

- [x] 1. Freeze the three fuzzy routes, contact-only prohibition, atomic grain, and non-claims.
  - Verify: requirements contain the exact inclusive thresholds and every downstream gate.

- [x] 2. Implement the pinned candidate-enrichment producer.
  - Verify: exact Phase 1 pairs are preserved, fuzzy routes are exhaustive within their declared
    blocks, and contact evidence cannot originate a pair.

- [x] 3. Add focused deterministic and failure-path tests.
  - Verify: thresholds, collisions, lineage, pin drift, forbidden fields, repeatability, and
    rollback are covered.

- [x] 4. Run focused tests, Ruff, mypy, repository guards, and scope review.
  - Verify: all checks pass without opening identity or analytical gates.

- [ ] 5. Materialize the pinned full corpus twice and publish the tracked manifest and audit.
  - Verify: both releases are byte-identical and the report reconciles exact, fuzzy, route,
    contact, collision, and quarantine counts.
