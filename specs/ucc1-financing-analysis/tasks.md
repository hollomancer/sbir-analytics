# UCC-1 Financing Analysis — Tasks

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

- [ ] 0.6 Write `scripts/data/ucc/export_cohort.py` — one-shot script that
      reproduces the Form D high-confidence SBIR cohort per the rules in
      `sbir-form-d-fundraising-analysis.md` (high tier + name OR ZIP
      match against `data/form_d_details.jsonl`). Output:
      `data/form_d_high_conf_cohort.jsonl` with `{company_name, state,
      agency, first_award_year, last_award_year, total_award_amount,
      form_d_filing_count, form_d_total_raised}`
      → verify: row count ≈ 3,640 per the prior analysis; sample 10
      records inspected
- [ ] 0.7 Reproduce the cohort row count documented in the prior analysis
      (±5%) as a sanity check on the export
      → verify: count printed; deviation explained if outside ±5%
- [ ] 0.8 Establish `SBIR_DATA_DIR` env-var convention for cross-worktree
      data access (default to `/Users/hollomancer/projects/sbir-analytics/data`)
      → verify: a `scripts/data/ucc/_common.py` helper resolves data paths
      via the env var; ucc1 scripts use it consistently

## Phase 1: Cohort narrowing

- [ ] 1.1 Create `scripts/data/ucc/cohort_state_filter.py` with
      `CohortStateFilter` that takes the Form D cohort and emits a
      CA-organized subset by querying CA SOS Business Search
      (`bizfileonline.sos.ca.gov/search/business`)
      → verify: 10-firm hand-curated test set (5 CA-organized, 5
      DE-organized doing business in CA) classified correctly
- [ ] 1.2 Per-firm rate limit (≤1 req/sec to bizfileOnline), resumable
      checkpoint
      → verify: kill / restart preserves progress on a 20-firm sample
- [ ] 1.3 Bulk run; write `data/ucc1_pilot_ca_org_cohort.jsonl`
      → verify: subset size N reported; CA-organized fraction of cohort
      reported (this is one of the headline gap metrics)
- [ ] 1.4 If N < 50, stop and report — sample too small for meaningful
      conclusions; pilot conclusion is "CA-only scope is structurally
      undersized; future work needs DE coverage to be informative"
      → verify: gate decision recorded in memo

## Phase 2: UCC extraction

- [ ] 2.1 Create `scripts/data/ucc/ca_extractor.py` with `CAUCCExtractor`
      that, per debtor name, submits a bizfileOnline UCC search with
      Advanced filter `File Type = Financing Statement`, expands each
      result, and pulls the full History modal (initial + UCC-3
      amendments / continuations / assignments / terminations)
      → verify: returns full lifecycle records for Inhibrx and Pacific
      Biosciences matching the Phase 0 manual probes
- [ ] 2.2 Define output schema in `scripts/data/ucc/schema.py` (TypedDict)
      including `filing_type` enum and `parent_filing_number`
      → verify: extractor emits the schema; mypy/ruff clean
- [ ] 2.3 Rate-limiting and resumable run state (jsonl checkpoint)
      → verify: kill / restart preserves progress on a 20-firm sample
- [ ] 2.4 Bulk run over `data/ucc1_pilot_ca_org_cohort.jsonl`; write
      `data/ucc1_pilot_raw.jsonl`
      → verify: row count > 0; per-firm latency logged; `filing_type`
      distribution printed; firms with zero results counted separately

## Phase 3: Matching

- [ ] 3.1 Create `scripts/data/ucc/matcher.py` with `UCCMatcher` reusing
      `sbir_etl` name-normalization helpers, filtering to debtor-side
      matches only (drop rows where the search hit was on the
      secured-party field)
      → verify: hand-curated 20-pair test set (10 match / 10 non-match)
      passes; Pacific Biosciences "UC Berkeley debtor / Pacific Biosciences
      secured party" row is correctly excluded
- [ ] 3.2 Tag each raw filing with `match_confidence` ∈ {high, medium,
      low}
      → verify: histogram of tiers logged
- [ ] 3.3 Drop low-confidence matches; write
      `data/ucc1_pilot_matches.jsonl`
      → verify: schema validated; sample of 10 inspected

## Phase 4: Lifecycle reconstruction

- [ ] 4.1 Create `scripts/data/ucc/lifecycle.py` with
      `LifecycleReconstructor` that groups matches by
      `parent_filing_number` and derives status / terminated_on /
      assignment_chain / last_event_date per UCC-1; reconcile computed
      `lapsed` against the CA portal's own status flag and log any
      disagreements
      → verify: hand-curated 5-filing fixture (initial + continuation +
      assignment + termination) yields expected status sequence
- [ ] 4.2 Track and log orphan UCC-3s (no resolvable parent in the
      cohort)
      → verify: orphan rate printed; sample of 5 inspected
- [ ] 4.3 Write `data/ucc1_pilot_lifecycles.jsonl` (one row per initial
      UCC-1)
      → verify: row count matches initial-UCC-1 count in matches;
      status distribution printed

## Phase 5: Secured-party classification

- [ ] 5.1 Seed `data/ucc1_pilot_lender_taxonomy.json` with the
      venture-debt + equipment + bank + tax-authority lender lists from
      `design.md`
      → verify: file exists; counts of distinct secured parties printed
- [ ] 5.2 Classify each match; log unknowns ranked by frequency
      → verify: top-50 unknowns reviewed; taxonomy extended as warranted
- [ ] 5.3 Flag foreign secured parties (address country ≠ US)
      → verify: count printed; spot-check 5

## Phase 6: M&A event corroboration

- [ ] 6.1 Create `scripts/data/ucc/ma_corroborate.py` joining lifecycles
      to `data/sbir_ma_events.jsonl` (filter `confidence ∈ {high,
      medium}`)
      → verify: joined record count printed; CA-organized firms with
      M&A event but no UCC-1 match counted separately
- [ ] 6.2 Compute `termination_within_180d`, `days_termination_to_event`,
      and `assignment_within_180d` per joined firm
      → verify: distribution histogram printed (leading vs. lagging)
- [ ] 6.3 Report sensitivity at ±30d, ±90d, ±180d, ±365d windows
      → verify: four corroboration rates printed; included in memo
- [ ] 6.4 If the M&A-event-and-matched-UCC-1 intersection has fewer than
      10 firms, report as "underpowered" rather than a rate
      → verify: explicit underpower flag in memo when applicable

## Phase 7: Analysis & memo

- [ ] 7.1 Create `scripts/data/ucc/analyze_pilot.py` computing headline
      metrics: CA-organized subset size vs full cohort size, match rate,
      Financing Statement prevalence, top-N secured parties by category,
      lifecycle status distribution, M&A corroboration rate, agency
      stratification, foreign-secured-party count
      → verify: all metrics printed
- [ ] 7.2 Hand-review 50 random matches for precision
      → verify: precision number recorded in memo
- [ ] 7.3 Append headline numbers and the completed gate-condition
      statement to `docs/research/sbir-ucc1-pilot.md` (the memo already
      exists from Phase 0; this updates the Status header and adds a
      Results section)
      → verify: memo answers the spec's headline questions for the
      CA-organized subset; coverage-gap framing is explicit
- [ ] 7.4 Add a one-paragraph "extend or stop" recommendation to the
      memo
      → verify: explicit recommendation; if "extend", references one of
      A+ (multi-state free), C (paid DE bulk), or B (BDC SoI pivot) per
      the Phase 0 memo's "Future options"

## Phase 8: Tests

- [ ] 8.1 Unit test for name normalization edge cases (Inc / LLC / Corp,
      punctuation, DBAs)
      → verify: pytest passes
- [ ] 8.2 Unit test for secured-party classifier on the seed lists
      (incl. tax-authority category)
      → verify: pytest passes
- [ ] 8.3 Fixture-based test for matcher on the 20-pair test set,
      including a debtor/secured-party role-confusion case
      → verify: pytest passes
- [ ] 8.4 Fixture-based test for `LifecycleReconstructor` covering:
      clean termination, lapsed (no termination, no continuation, >5y),
      assignment chain, orphan UCC-3, computed-vs-portal status
      disagreement
      → verify: pytest passes
- [ ] 8.5 Fixture-based test for `CohortStateFilter` covering: CA-organized
      domestic entity, foreign entity registered in CA, no-result, multiple
      entities with similar names
      → verify: pytest passes

## Out of scope for this spec

Anything in `design.md` "What This Does NOT Include". If the pilot
recommends extending, open a follow-on spec — do not let scope creep
into this one.
