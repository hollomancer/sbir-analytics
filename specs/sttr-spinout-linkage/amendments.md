# STTR Spinout–Subcontract Linkage Freeze and Amendment Log

This is the append-only approval record for [`design.md`](design.md). Existing records must not be
edited, removed, or reordered. Every later change is a new numbered record stating the reason, the
criteria impact, and what result information was visible when it was approved. Git history preserves
each prior version; a materializing asset (when one is authorized) would verify and record the
raw-byte SHA-256 of `design.md` and this file before running.

The pattern mirrors [`specs/phase-iii-census/amendments.md`](../phase-iii-census/amendments.md).
**Frozen as of Revision 1** (2026-08-14). Revisions 0 through 0.3 are the pre-freeze draft history
and are not themselves freezes — only Revision 1 is. Any change to `design.md` after Revision 1
requires its own numbered amendment here, per the append-only rule above.

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

## Revision 0.3 — O-12 resolved after a second research pass; task 0.5 complete, still NOT frozen

- **Authority:** 2026-08-14 — owner declined to accept the first research pass's verdict outright,
  requested a second pass, then accepted the combined findings ("Satisfied").
- **Reason:** Record the second Bayh-Dole-sourcing research pass and its acceptance, completing
  task 0.5 (all of O-0 through O-12 now resolved).
- **Second-pass findings:** AUTM STATT (paid, aggregate-only — ruled out on two independent
  grounds) and AUTM TransACT (paid, explicitly de-identified — wrong grain at any price) both
  ruled out; UCC-1 filings ruled out (IP-collateral parsing was explicitly out of scope for the
  repo's existing UCC-1 pilot, and a UCC-1 records the SBC's own IP as loan collateral, not an
  inbound RI license, regardless). One genuinely new candidate surfaced: **SEC EDGAR full-text
  search** — the repo's existing `sec_edgar` client can search filing exhibits (EX-10 material
  contracts) since 2001 via a verified multi-phrase query; real positive evidence when it fires,
  but coverage is limited to STTR firms that later became SEC filers and each hit needs manual
  confirmation. The local USPTO `convey_text` proxy was sharpened from a generic "license" search
  (first pass) to the actual Bayh-Dole regulatory term **"confirmatory license"** (37 CFR 401.14):
  12,946 hits directly verified in a 3,000,001-row sample of the local `assignment.csv.zip`
  (~45,000 extrapolated repo-wide) — a materially more specific proxy, though it still answers
  federal-funding nexus (contractor-to-government), not an RI-to-SBC license.
- **Criteria impact:** `design.md`'s D3 discipline note updated to fold in both second-pass proxies
  (sharper `convey_text` term, optional corroborating EDGAR search) as the v1 sourcing plan for
  `D3.recorded_license_RI_to_SBC`, should it ship at all. No change to the Order-1/Order-3 cascade
  predicates themselves — this question only ever concerned D3's *source*, not its scoring logic.
- **Freeze status:** **Still NOT frozen — task 0.5 is now complete; task 0.6 (Revision 1 freeze) is
  unblocked but has not been authorized.** Freezing is a separate, higher-stakes action (locks the
  cascade, the lexicon, and the seed-list versions at a commit SHA and unlocks Phase 1
  implementation) and requires its own explicit go-ahead, not an automatic consequence of O-12
  resolving.
- **Visibility at authoring:** Same as Revision 0. **No classification result had been computed or
  seen.**

## Revision 1 — FREEZE

- **Approved:** 2026-08-14 — repository owner authorized the freeze explicitly ("Yes, freeze it"),
  after accepting all 12 open-question resolutions (Revisions 0.2 and 0.3).
- **Frozen file:** `design.md`, raw-byte **SHA-256:**
  `52d8b531d56f3b91e1d3b0946e1ac91dd6f5dfeab371e3d48f87dc5e6095ac49`. A materializing asset (task
  1.3+) must recompute this hash against the working copy before running and fail closed on any
  mismatch — including a mismatch caused by a well-intentioned edit to `design.md` that was never
  recorded as a further amendment here.
- **Git-history anchor:** the commit that introduces this Revision 1 entry is the approval-record
  anchor for `amendments.md` itself; its identifier is intentionally not embedded in the content it
  would hash, mirroring the convention already used in
  [`specs/phase-iii-census/amendments.md`](../phase-iii-census/amendments.md) Revision 10.
- **What is frozen:** the classification cascade structure and ordering (Order 0–4, D1–D5 evidence
  dimensions and their sourcing, including the O-12 D3 findings); the exact-vs-fuzzy similarity
  **method** (`CompanyNameMetric.JARO_WINKLER` + `generic_token_guard`); the partner-type precedence
  order (`FFRDC > NEW_MODEL_ORG > UNIVERSITY > RESEARCH_HOSPITAL > COMMUNITY_COLLEGE >
  NONPROFIT_INSTITUTE > OTHER_NONPROFIT`); the D2 scope (PI + Form-D-derived founders, ±5-year
  window); the D4/D5 sourcing as designed; the RQ2 design-only status (O-9) and its embedding choice
  (O-10, not yet exercised).
- **What remains explicitly open, by design, not oversight:** the O-3 numeric similarity cutoff
  (deferred to a post-task-1.4 amendment, calibrated from the adjudication sample); the D5 phrase
  lexicon's actual content (task 1.3); the six partner-type seed lists' actual captured
  versions/hashes (task 1.1, `seed-list-provenance.md` still all `_pending_`). None of these block
  Phase 1 from *starting*; they block specific Phase 1 sub-steps from *completing*.
- **Criteria impact:** This is the freeze itself — see Revisions 0.2 and 0.3 for the substance of
  every resolved question. No classification cascade has been coded or run as of this revision.
- **Freeze status:** **FROZEN.** Phase 1 (`tasks.md`) is unblocked to begin. This does not authorize
  materialization, a headline cell, or any citable claim — those remain gated on the negative-control
  and adjudication results (task 1.4) per `design.md`'s validation-and-gates section.
- **Visibility at approval:** Same as Revision 0. **No classification result, incidence count,
  coverage count, negative-control result, or adjudication result had been computed or seen at the
  time of this freeze.**

## Revision 2 — Doc-hygiene follow-up to Revision 1 (O-8 citation + stale freeze wording)

- **Authority:** 2026-08-15 — address review nits on the Revision 1 freeze PR (#620) after merge.
- **Reason:** Revision 1 resolved O-8 as "add `[L50]`" but left `design.md` still saying the
  Bayh-Dole anchor was missing, and left the cascade-table header saying "pending threshold
  decisions" after the method freeze. No classification criterion changed.
- **Criteria impact:** None. Cascade Order 0–4 predicates, D1–D5 sourcing, similarity method,
  partner-type precedence, and D2 scope/window are unchanged. `design.md` now cites
  [L50](../../docs/research-questions.md) for 35 U.S.C. §§ 200–212 and the cascade-table header
  clarifies that only the O-3 *numeric* cutoff remains deferred. Companion non-frozen docs
  (`tasks.md` status header, `coverage-memo.md` O-12 second-pass language,
  `docs/research-questions.md` `[L50]` entry) updated in the same change.
- **Frozen file:** `design.md`, raw-byte **SHA-256:**
  `8e754731f0d0841e5f48c425e269bc9db59191e761bcd8df7292032f9f78ff07`. Supersedes the Revision 1
  digest for guard purposes; Revision 1 remains the freeze-authorization record.
- **Freeze status:** Still **FROZEN** (this is a documented working-copy refresh, not a thaw).
- **Visibility at authoring:** **No classification result had been computed or seen.**
