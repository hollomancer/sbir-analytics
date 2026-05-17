# UCC-1 Financing Analysis — Tasks

**Status:** Pilot complete through the partial-run epistemic checkpoint;
extension deferred. See [docs/research/sbir-ucc1-pilot.md](../../docs/research/sbir-ucc1-pilot.md)
("Recommendation: Stop here") for the rationale. Phases 4–6 and the
remaining pieces of 7 / 8 are unimplemented by design — re-open this
spec only if one of the Future-options paths (multi-state, paid DE bulk,
or BDC SoI pivot) is selected.

## Phase 0: Feasibility check — COMPLETE

Recorded in [docs/research/sbir-ucc1-pilot.md](../../docs/research/sbir-ucc1-pilot.md).

- [x] 0.1 ~~DE web search of 5 firms~~ → **DE has no free public UCC search.**
      All non-"Search to Reflect" searches require a paid Authorized
      Searcher (CSC, CT, Cogency, FCS). DE dropped from pilot scope.
- [x] 0.2 CA bizfileOnline lookups of Inhibrx and Pacific Biosciences →
      portal viable; clean schema; full UCC-3 lifecycle in History modal;
      Advanced search supports File Type filter; no CAPTCHA at modest
      query rates; § 9-307 jurisdictional bias confirmed (CA-HQ but
      DE-incorporated biotechs return only tax liens, zero venture debt).
- [x] 0.3 ~~Confirm cohort export path~~ → **No discrete cohort export
      exists.** Cohort is a derivation per
      `sbir-form-d-fundraising-analysis.md`. A one-shot export script is
      a prerequisite, added as task 0.6 below.
- [x] 0.4 `data/sbir_ma_events.jsonl` schema confirmed: `company_name`,
      `event_date`, `confidence` (note: field is `confidence`, not `tier`
      as the original spec assumed), `signals`, `form_d_detail`,
      `efts_detail`, `sbir_context`. 4,306 events total; 1,197 high /
      1,593 medium / 1,516 low confidence.
- [x] 0.5 Phase 0 memo committed at `docs/research/sbir-ucc1-pilot.md`
      with gate-condition statement template.

## Phase 0.5: Prerequisites (no Phase 1 code without these)

- [x] 0.6 Write `scripts/data/ucc/export_cohort.py` — one-shot script that
      reproduces the Form D high-confidence SBIR cohort per the rules in
      `sbir-form-d-fundraising-analysis.md` (high tier + name OR ZIP
      match against `data/form_d_details.jsonl`). Output:
      `data/form_d_high_conf_cohort.jsonl` with `{company_name, state,
      agency, first_award_year, last_award_year, total_award_amount,
      form_d_filing_count, form_d_total_raised}`
      → verified: 3,639 rows produced (memo §Cohort export completed)
- [x] 0.7 Reproduce the cohort row count documented in the prior analysis
      (±5%) as a sanity check on the export
      → verified: 3,639 vs documented ~3,640 (0.03% deviation)
- [x] 0.8 Establish `SBIR_DATA_DIR` env-var convention for cross-worktree
      data access (default: repo's own `data/` resolved relative to the
      script; override via `SBIR_DATA_DIR`)
      → verified: `scripts/data/ucc/_common.py` resolves `data_path()`
      via the env var; all ucc1 scripts use it

## Phase 1: Cohort narrowing

- [x] 1.1 Create `scripts/data/ucc/cohort_state_filter.py` with
      `CohortStateFilter` that takes the Form D cohort and emits a
      CA-organized subset by querying CA SOS Business Search
      (`bizfileonline.sos.ca.gov/search/business`)
      → verified: `is_ca_organized()` correctly classifies the CA/foreign
      cases (test_cohort_state_filter.py)
- [x] 1.2 Per-firm rate limit (≤1 req/sec to bizfileOnline), resumable
      checkpoint
      → verified: `DEFAULT_DELAY_SECONDS=1.0`, JSONL checkpoint with
      resume covered by `test_narrow_to_ca_organized_skips_checkpointed`
- [x] 1.3 Bulk run; write `data/ucc1_pilot_ca_org_cohort.jsonl`
      → **partial:** 70 of 3,639 firms processed before Imperva escalated
      (memo §Cohort-narrowing geometry). CA-organized fraction recorded
      at 12.9% (9 / 70). Full-cohort coverage requires operational
      scaling (residential proxies, real Playwright) which the pilot
      deemed not warranted.
- [x] 1.4 If N < 50, stop and report — sample too small for meaningful
      conclusions; pilot conclusion is "CA-only scope is structurally
      undersized; future work needs DE coverage to be informative"
      → verified: gate-condition statement recorded in memo's
      §Gate-condition statement (partial sample)

## Phase 2: UCC extraction

- [x] 2.1 Create `scripts/data/ucc/ca_extractor.py` with `CAUCCExtractor`
      that, per debtor name, submits a bizfileOnline UCC search with
      Advanced filter `File Type = Financing Statement`, expands each
      result, and pulls the full History modal (initial + UCC-3
      amendments / continuations / assignments / terminations)
      → verified: `HttpBizfileClient` walks search → detail → history;
      Active Motif lifecycle reproduced in memo
- [x] 2.2 Define output schema in `scripts/data/ucc/schema.py` (TypedDict)
      including `filing_type` enum and `parent_filing_number`
      → verified: `UCCFiling`, `UCCLifecycle`, `UCCMatch`, etc. TypedDicts
      + `FilingType` StrEnum. (Note: `scripts/` is mypy-excluded; tests
      assert the shape instead.)
- [x] 2.3 Rate-limiting and resumable run state (jsonl checkpoint)
      → verified: `DEFAULT_DELAY_SECONDS=1.0`, JSONL checkpoint with
      skip-if-done in `ca_extractor.main()`
- [x] 2.4 Bulk run over `data/ucc1_pilot_ca_org_cohort.jsonl`; write
      `data/ucc1_pilot_raw.jsonl`
      → **partial:** ran on the 9 CA-organized firms from the partial
      Phase 1 run. 14 hits total before matcher filtering; filing_type
      distribution recorded in memo.

## Phase 3: Matching

- [x] 3.1 Create `scripts/data/ucc/matcher.py` with `UCCMatcher` reusing
      `sbir_etl` name-normalization helpers, filtering to debtor-side
      matches only (drop rows where the search hit was on the
      secured-party field)
      → verified: 20-pair MATCH/NON_MATCH dataset in test_matcher.py;
      Pacific Biosciences secured-party-side case correctly dropped
- [x] 3.2 Tag each raw filing with `match_confidence` ∈ {high, medium,
      low}
      → verified: `classify_match()` returns one of high/medium/low/drop;
      `match_extraction()` retains high/medium only
- [x] 3.3 Drop low-confidence matches; write
      `data/ucc1_pilot_matches.jsonl`
      → verified: matcher.main() writes UCCMatch rows; the 14 hits from
      the partial run yielded 4 retained (Active Motif), 10 dropped as
      false positives — 100% precision (memo §Active Motif)

## Phase 4: Lifecycle reconstruction — DEFERRED

Per memo's Stop recommendation. The 4 retained Active Motif filings
don't require lifecycle reconstruction to support the pilot's headline
finding (equipment-finance + community-banking, no venture debt).
Re-open if a Future-options path (multi-state, paid DE bulk, or BDC
SoI pivot) yields a population where active/terminated state is
analytically meaningful.

- [ ] 4.1 `LifecycleReconstructor` — deferred
- [ ] 4.2 Orphan UCC-3 tracking — deferred
- [ ] 4.3 `data/ucc1_pilot_lifecycles.jsonl` — deferred

## Phase 5: Secured-party classification — DEFERRED

Per memo's Stop recommendation. With only 4 retained filings the
classifier would be classifying by hand. The four observed secured
parties (LEAF Capital, DE LAGE LANDEN, Endeavor Bank, CSC) were
classified directly in the memo.

- [ ] 5.1 Seed `data/ucc1_pilot_lender_taxonomy.json` — deferred
- [ ] 5.2 Classify each match — deferred
- [ ] 5.3 Foreign secured-party flag — deferred

## Phase 6: M&A event corroboration — DEFERRED

Per memo's Stop recommendation. With only 1 CA-organized firm with
real UCC-1 matches and no recorded M&A event, the join is empty.
Re-open with a larger denominator.

- [ ] 6.1 `ma_corroborate.py` — deferred
- [ ] 6.2 Termination/assignment delta computation — deferred
- [ ] 6.3 Window sensitivity — deferred
- [ ] 6.4 Underpower flag — deferred

## Phase 7: Analysis & memo

- [ ] 7.1 Create `scripts/data/ucc/analyze_pilot.py` — **DEFERRED.**
      The partial-run sample (14 hits, 4 retained) was small enough to
      summarize by hand directly in the memo. A scripted analyzer
      becomes worthwhile only after the cohort scales up.
- [ ] 7.2 Hand-review 50 random matches for precision — **DEFERRED.**
      The partial run produced only 14 hits total; all 14 were
      hand-classified (4 true positives, 10 false positives, all
      caught by the matcher) — 100% precision on the observed set, but
      n=14 not n=50.
- [x] 7.3 Append headline numbers and the completed gate-condition
      statement to `docs/research/sbir-ucc1-pilot.md`
      → verified: §Pilot Results — Partial Run added; gate-condition
      statement (partial sample) recorded
- [x] 7.4 Add a one-paragraph "extend or stop" recommendation to the
      memo
      → verified: §Recommendation: Stop here; promote to multi-state
      or pivot to BDC — references Future-options A+ / B / C

## Phase 8: Tests

- [x] 8.1 Unit test for name normalization edge cases (Inc / LLC / Corp,
      punctuation, DBAs)
      → verified: `test_normalize_name_*` + 20-pair MATCH/NON_MATCH set
      in `tests/unit/scripts/ucc/test_matcher.py`
- [ ] 8.2 Unit test for secured-party classifier — **DEFERRED** with
      Phase 5
- [x] 8.3 Fixture-based test for matcher on the 20-pair test set,
      including a debtor/secured-party role-confusion case
      → verified: Pacific Biosciences SP-side test in
      `test_is_debtor_side_match_drops_pacific_biosciences_as_secured_party`
- [ ] 8.4 Fixture-based test for `LifecycleReconstructor` — **DEFERRED**
      with Phase 4
- [x] 8.5 Fixture-based test for `CohortStateFilter` covering: CA-organized
      domestic entity, foreign entity registered in CA, no-result, multiple
      entities with similar names
      → verified: `tests/unit/scripts/ucc/test_cohort_state_filter.py`
      (CA domestic, CA foreign, DE-organized-foreign, None record, empty
      record, pick-best ranking)

## Out of scope for this spec

Anything in `design.md` "What This Does NOT Include". If the pilot
recommends extending, open a follow-on spec — do not let scope creep
into this one.
