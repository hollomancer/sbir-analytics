# Supplier-Share Census Tasks

**Target epistemic tier:** `exploratory`

- [x] 1. Audit reusable sources and lifecycle gates
  - Verify: requirements/design list Active, Maintenance, Deferred, and Gated dependencies

- [x] 2. Freeze Revision 0 before computation
  - Verify: `amendments.md` records the raw-byte `design.md` SHA-256 and no result visibility

- [x] 3. Implement the deterministic exploratory producer
  - Verify: all 18 grid cells reconcile; missing required signals suppress the headline

- [x] 4. Add the thin review notebook and registry/research-question entries
  - Verify: notebook contains no duplicate classification logic; `make docs-check` passes

- [x] 5. Run available materialized inputs and inspect artifacts
  - Verify: Parquet, summary CSV, SVG, Markdown, and manifest are emitted; validation status is
    truthful for missing channels

- [x] 6. Run focused quality checks and commit
  - Verify: Ruff, tier guards, docs checks, and deterministic rerun checks pass

## Promotion Tasks (Not Part Of This Exploratory Slice)

- [ ] P1 Restore or regenerate complete Form D and final M&A signal artifacts
- [ ] P2 Complete and review the 50-firm hand adjudication
- [ ] P3 Supply and review face-validity anchors
- [ ] P4 Approve a negative-control threshold and rerun
- [ ] P5 Create a separate evidence study contract with source hashes and blocking checks
