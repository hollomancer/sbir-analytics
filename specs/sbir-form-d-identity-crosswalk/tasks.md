# SBIR ↔ Form D Identity Crosswalk — Tasks

- [x] 1. Define the pinned input, ledger, atomic edge, and publication contracts.
  - Verify: `requirements.md` declares the `pipelines` tier and all downstream non-claims.
  - Requirements: 1.1–1.4, 2.1–2.5, 3.1–3.4, 4.1–4.4

- [x] 2. Implement `scripts/data/build_sbir_form_d_identity_crosswalk.py`.
  - Verify: the CLI validates source pins, emits content-addressed products, and reports only
    candidate/unreviewed edges with every downstream gate closed.
  - Requirements: 1.1–4.4

- [x] 3. Add focused producer tests.
  - Verify: tests cover multi-CIK collisions, one name across multiple SBIR identifier components,
    UEI/DUNS conflict quarantine, no-identifier identity, pin drift, deterministic reruns, and
    publication rollback.
  - Requirements: acceptance criteria

- [x] 4. Point the parent private-capital spec at this atomic prerequisite without closing its
  identity, covariate, matching, or outcome gates.
  - Verify: parent requirements/design/tasks describe candidate-only atomic evidence and link here.
  - Requirements: 3.4, non-claims

- [x] 5. Run focused verification and repository guards.
  - Verify: focused pytest, Ruff, mypy, `make lint-boundaries`, `make docs-check`, and scope diff pass.
  - Requirements: 4.4

- [ ] 6. Materialize the pinned full-history inputs twice and publish the tracked audit record.
  - Verify: both real runs are byte-identical; the tracked manifest and report reconcile source,
    component, collision, quarantine, and candidate-edge counts while every downstream gate stays
    closed.
  - Requirements: 1.1–4.4
