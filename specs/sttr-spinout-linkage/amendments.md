# STTR Spinout–Subcontract Linkage Freeze and Amendment Log

This is the append-only approval record for [`design.md`](design.md). Existing records must not be
edited, removed, or reordered. Every later change is a new numbered record stating the reason, the
criteria impact, and what result information was visible when it was approved. Git history preserves
each prior version; a materializing asset (when one is authorized) would verify and record the
raw-byte SHA-256 of `design.md` and this file before running.

The pattern mirrors [`specs/phase-iii-census/amendments.md`](../phase-iii-census/amendments.md).
Unlike that spec, **no freeze has occurred**: the criteria remain in draft pending owner resolution
of [`open-questions.md`](open-questions.md). Do not treat Revision 0 as a freeze.

## Revision 0 — Phase 0 draft created; NOT frozen

- **Authority:** 2026-08-14 — design authored; no owner approval sought or given.
- **Reason:** Record the initial Phase 0 design for the STTR spinout–subcontract linkage
  classifier, the RI partner-type classifier, and the RQ2 outcome-comparison design, so the method
  is written before any run. This spec is `exploratory`-tier and non-citable.
- **Criteria impact:** Establishes the proposed evidence dimensions (D1–D5), the proposed ordered
  classification cascade, and the proposed partner-type vocabulary and precedence — **all
  provisional.** Nothing is frozen. Tier thresholds, the D2 window, the D5 lexicon, founders-in-scope,
  the partner-type seed-list versions and precedence, the Bayh-Dole anchor, the RQ2 embedding, and
  the RQ2 ship-here-or-own-spec decision are open in [`open-questions.md`](open-questions.md).
- **Freeze status:** **NOT frozen.** Freezing is blocked until the owner resolves the open
  questions. The first freeze will be recorded as Revision 1 with a commit SHA and a visibility
  statement.
- **Visibility at authoring:** Only documentation, source schemas, and the repository's existing
  primitives were consulted. **No STTR classification, incidence count, coverage count,
  negative-control result, or adjudication result had been computed or seen.**

## Revision 0.1 — Dedicated inventory questions, tasks file, L49 correction; still NOT frozen

- **Authority:** 2026-08-14 — Phase 0 draft continuation; no owner approval sought or given.
- **Reason:** Record three Phase 0 corrections that do not freeze criteria: (1) dedicated
  B1/B2 inventory questions so the spec is not stretched onto the existing B2
  award-to-contract entries; (2) a `tasks.md` listing the freeze gate and blocked
  Phase 1 work; (3) O-8 must not take `[L49]`, which is reserved for an unverified
  Jones & Fearon deposit — next unreserved slot is `[L50]`.
- **Criteria impact:** None. Cascade, lexicon, thresholds, and seed-list versions remain
  provisional. O-6/O-7 source decisions from Revision 0 stand.
- **Freeze status:** **NOT frozen.** Freezing remains blocked until the owner resolves
  the remaining open questions.
- **Visibility at authoring:** Same as Revision 0. **No classification result had been
  computed or seen.**

## Revision 0.2 — 10 of 12 open questions resolved; still NOT frozen

- **Authority:** 2026-08-14 — owner resolved O-0 through O-5 and O-8 through O-11 in conversation;
  recorded here as the numbered revision required by `open-questions.md`'s own header.
- **Reason:** Record the owner's resolutions so `design.md` and `open-questions.md` stop describing
  these as pending. Resolutions, several diverging from the proposed default:
  - **O-0** (kernel): build here at exploratory tier — proposed default accepted.
  - **O-1** (D2 scope): PI **and** founders in v1 — wider than the PI-only default. Founders are
    scoped to D4 Form-D-derived officer/director names only; no new founder-discovery pipeline.
  - **O-2** (D2 window): **±5 years** — wider than the proposed ±3. Sensitivity reporting
    (±1/±2/±3/±5) remains required.
  - **O-3** (tier thresholds): method frozen now (`company_name_similarity` under
    `CompanyNameMetric.JARO_WINKLER` + `generic_token_guard`); **numeric cutoff explicitly deferred**
    to a post-task-1.4 amendment to break the circular dependency on the adjudication sample.
    `SPINOUT_T2` scoring cannot run until that follow-on amendment lands.
  - **O-4** (D5 lexicon): ship a small hand-curated v1 lexicon — proposed default accepted; exact
    phrase list drafted and frozen at task 1.3, not here.
  - **O-5** (partner-type precedence): confirmed as stated — `FFRDC > NEW_MODEL_ORG > UNIVERSITY >
    RESEARCH_HOSPITAL > COMMUNITY_COLLEGE > NONPROFIT_INSTITUTE > OTHER_NONPROFIT`.
  - **O-8** (Bayh-Dole citation): add `[L50]` for 35 U.S.C. §§ 200–212 — proposed default accepted.
  - **O-9** (RQ2 home): stay design-only here, spin off at implementation time — proposed default
    accepted.
  - **O-10** (RQ2 embedding): reuse existing ModernBERT-Embed path — proposed default accepted.
  - **O-11** (partner-type home): ship in this spec — proposed default accepted.
- **Criteria impact:** `design.md`'s D2 row and the classification-cascade method paragraph updated
  to reflect O-1/O-2/O-3. Tier thresholds are now **partially** frozen (method, not cutoff). Founder
  scope, D2 window, and precedence order are now fixed. Lexicon content and the O-3 numeric cutoff
  remain open pending task 1.3 / task 1.4 respectively.
- **Freeze status:** **Still NOT frozen.** [O-12](open-questions.md#o-12--bayh-dole-government-interest-statement-data-source)
  (Bayh-Dole government-interest data source) is the sole remaining blocker on task 0.5 — the owner
  requested a second research pass rather than accepting the first pass's structural-limitation
  finding. Revision 1 cannot be recorded until O-12 resolves.
- **Visibility at authoring:** Same as Revision 0. **No classification result had been computed or
  seen.**
