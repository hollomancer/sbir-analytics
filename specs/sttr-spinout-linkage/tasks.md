# STTR Spinout–Subcontract Linkage — Tasks

**Target epistemic tier:** `exploratory`

**Status:** Phase 0 design. Implementation is **not authorized** until the owner
resolves [`open-questions.md`](open-questions.md) and Revision 1 freezes the
criteria in [`amendments.md`](amendments.md). Exploratory-tier work: no tests or
abstractions beyond what a single probe needs, and no citable numbers.

## Phase 0 — Design (this spec)

- [x] 0.1 Write requirements, design, open questions, amendments log, coverage
      memo, and seed-list provenance
  - Verify: `make docs-check` and `uv run python scripts/ci/check_epistemic_tiers.py` pass
  - Requirements: header (tier + research-question anchor)

- [x] 0.2 Register the spec in `specs/status.md` as Gated backlog
  - Verify: registry coverage check in `make docs-check`

- [x] 0.3 Resolve partner-type source questions O-6 and O-7
  - Verify: sources named in `seed-list-provenance.md`; data capture still pending

- [x] 0.4 Add dedicated inventory questions and Spec pointers in
      `docs/research-questions.md`
  - Verify: B1 partner-type and B2 spinout-vs-subcontract entries link here;
    `make docs-check` passes
  - Requirements: header

- [x] 0.5 Owner resolves remaining open questions (O-0 through O-5, O-8 through
      O-12)
  - O-0 through O-5 and O-8 through O-11 resolved, recorded as `amendments.md`
    Revision 0.2. O-12 required a second research pass (owner did not accept
    the first pass's verdict outright) before being accepted, recorded as
    Revision 0.3.
  - Verify: each resolution is a numbered revision in `amendments.md`
  - Requirements: freeze gate

- [x] 0.6 Freeze criteria as Revision 1 at a commit SHA
  - `amendments.md` Revision 1 records the design.md SHA-256, the visibility
    statement, and that no classification result had been seen. Phase 1 is
    now unblocked to begin.
  - Verify: `amendments.md` Revision 1 records the SHA, the visibility
    statement, and that no classification result had been seen
  - Requirements: freeze gate

## Phase 1 — Implementation (blocked on 0.6)

Do not start these tasks before Revision 1. Build at `exploratory` tier: no
silent promotion, no research question marked answerable, no new causal graph
edges.

- [ ] 1.1 Capture versioned seed lists (hash + date) per
      [`seed-list-provenance.md`](seed-list-provenance.md)
  - 5 of 6 lists captured with real `version`/`captured`/`sha256`
    (#624): `ffrdc_master`, `ipeds_institutions`, `new_model_orgs`,
    `fiscal_sponsors`, `nonprofit_registry`. `research_hospitals` is
    honestly left `_pending_` — both O-7-named sources (NIH RePORTER's
    hospital filter, AAMC COTH) are dead ends; see
    [`seed-list-provenance.md`](seed-list-provenance.md#capture-notes)
    for the blocker and follow-up path. Two O-6-named entries flagged
    for spec-owner review, not silently resolved: Arcadia Science
    (for-profit, not nonprofit like the rest of `new_model_orgs`) and
    Social Finance / RCSA (`fiscal_sponsors` — no public source
    confirms either actually acts as a fiscal sponsor).
  - Verify: every list has `version`, `captured`, and `sha256`; the classifier
    fails closed on an uncaptured list — **still fails closed on
    `research_hospitals`**, so this task is not fully done.
  - Requirements: 2.1

- [x] 1.2 Build the exploratory kernel (`resolve_identity`, `classify_linkage`,
      `generic_token_guard`, `signal_absent_reason`) on `sbir_etl.identity`
      primitives, or consume an upstream spec if O-0 chooses (b)
  - `scripts/sttr_spinout_linkage/kernel.py` (#623). `classify_linkage`
    implements the frozen Order 0-4 cascade *rule structure* only, over
    caller-supplied pre-scored dimension evidence — it does not score
    D1-D5 itself (that's the rest of task 1.3). `similarity_cutoff` is
    a required parameter with no default, per O-3's deferral.
  - Verify: organization-name matching goes through `normalize_company_name` /
    `company_name_similarity`; no forked normalizer
  - Requirements: 1.4, O-0

- [ ] 1.3 Implement the ordered RQ1 cascade and the partner-type classifier as
      exploratory scripts or a notebook-backed probe
  - Verify: labels are a pure function of the five dimensions; typed
    `DimensionStatus` on every dimension; `CANDIDATE` assertions only
  - Requirements: 1.1–1.3, 2.1–2.3, 3.1–3.2

- [ ] 1.4 Run the negative-control and 150–200 award NSF/NIH-first adjudication
      gates
  - Verify: random-RI and permuted-PI controls pass; precision/recall by tier
    reported; every artifact remains `citable: false` until signed off
  - Requirements: design.md validation gates

RQ2 remains design-only in this spec (Requirement 4). Spinning it into its own
spec is O-9 and is not a Phase 1 task here.

## Workbench probe (not Phase 1, not RQ2)

A notebook at
[`notebooks/explorations/b1_sttr_partner_type_commercialization.ipynb`](../../notebooks/explorations/b1_sttr_partner_type_commercialization.ipynb)
stratifies STTR Phase II firms by a coarse RI-name heuristic (`UNIVERSITY` /
`FFRDC` / `COMMUNITY_COLLEGE` / `UNTYPED`) across existing Phase III / Form D /
M&A artifacts. It is unmatched, exploratory, and non-citable. It does **not**
implement the partner-type classifier, does **not** freeze criteria, and is
**not** the RQ2 matched spinout-vs-subcontract comparison.
