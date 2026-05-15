# UCC-1 Financing Analysis — Tasks

## Phase 0: Feasibility check (before any code)

- [ ] 0.1 Manually pull UCC-1 records for 5 known SBIR firms via DE web search,
      including at least one firm with a known M&A exit (to confirm UCC-3
      terminations and assignments are retrievable from the portal)
      → verify: initial + amendment + termination records all returnable;
      schema fields available; rate limits observable
- [ ] 0.2 Manually pull UCC-1 records for 5 known SBIR firms via CA bizfileOnline,
      same M&A-exit condition as above
      → verify: same as 0.1 for CA
- [ ] 0.3 Confirm Form D high-confidence cohort export path and field names
      → verify: cohort CSV/JSONL accessible with `company_name`, `state`,
      `agency`, `first_award_year`
- [ ] 0.4 Confirm `data/sbir_ma_events.jsonl` schema and date semantics
      → verify: `event_date` field present; high+medium tier filter agreed;
      sample of 5 records inspected
- [ ] 0.5 Document any access blockers in `docs/research/sbir-ucc1-pilot.md` stub
      → verify: stub committed; gate-condition statement template in place

If 0.1 or 0.2 reveal CAPTCHA / aggressive blocking, or if UCC-3 records
are not retrievable per state, stop and revisit sourcing before proceeding.

## Phase 1: Extraction

- [ ] 1.1 Create `scripts/data/ucc/de_extractor.py` with `DEExtractor` class
      that returns initials *and* related UCC-3s (amendments,
      continuations, assignments, terminations) per debtor
      → verify: returns full lifecycle records for the 5 firms from 0.1,
      including the M&A-exit firm's termination
- [ ] 1.2 Create `scripts/data/ucc/ca_extractor.py` with `CAExtractor`
      class (same lifecycle requirement)
      → verify: same for CA
- [ ] 1.3 Define common output schema in `scripts/data/ucc/schema.py`
      (TypedDict) including `filing_type` enum and `parent_filing_number`
      → verify: both extractors emit the schema; mypy/ruff clean
- [ ] 1.4 Add per-state rate-limiting and resumable run state (sqlite or
      jsonl checkpoint)
      → verify: kill / restart preserves progress on a 20-firm sample
- [ ] 1.5 Bulk run over Form D high-confidence cohort, write
      `data/ucc1_pilot_raw.jsonl`
      → verify: row count > 0 per state; per-firm latency logged;
      `filing_type` distribution printed

## Phase 2: Matching

- [ ] 2.1 Create `scripts/data/ucc/matcher.py` with `UCCMatcher` reusing
      `sbir_etl` name-normalization helpers
      → verify: hand-curated 20-pair test set (10 match / 10 non-match) passes
- [ ] 2.2 Tag each raw filing with `match_confidence` ∈ {high, medium, low}
      → verify: histogram of tiers logged
- [ ] 2.3 Drop low-confidence matches; write `data/ucc1_pilot_matches.jsonl`
      → verify: schema validated; sample of 10 inspected

## Phase 3: Lifecycle reconstruction

- [ ] 3.1 Create `scripts/data/ucc/lifecycle.py` with
      `LifecycleReconstructor` that groups matches by
      `parent_filing_number` and derives status / terminated_on /
      assignment_chain / last_event_date per UCC-1
      → verify: hand-curated 5-filing fixture (initial + continuation +
      assignment + termination) yields expected status sequence
- [ ] 3.2 Track and log orphan UCC-3s (no resolvable parent in the cohort)
      → verify: orphan rate printed; sample of 5 inspected
- [ ] 3.3 Write `data/ucc1_pilot_lifecycles.jsonl` (one row per initial UCC-1)
      → verify: row count matches initial-UCC-1 count in matches;
      status distribution printed

## Phase 4: Secured-party classification

- [ ] 4.1 Seed `data/ucc1_pilot_lender_taxonomy.json` with the venture-debt
      lender list from `design.md`
      → verify: file exists; counts of distinct secured parties printed
- [ ] 4.2 Classify each match; log unknowns ranked by frequency
      → verify: top-50 unknowns reviewed; taxonomy extended as warranted
- [ ] 4.3 Flag foreign secured parties (address country ≠ US)
      → verify: count printed; spot-check 5

## Phase 5: M&A event corroboration

- [ ] 5.1 Create `scripts/data/ucc/ma_corroborate.py` joining lifecycles to
      `data/sbir_ma_events.jsonl` (high+medium tier)
      → verify: joined record count printed; firms with M&A event but no
      UCC-1 match counted separately
- [ ] 5.2 Compute `termination_within_180d`, `days_termination_to_event`,
      and `assignment_within_180d` per joined firm
      → verify: distribution histogram printed (leading vs. lagging)
- [ ] 5.3 Report sensitivity at ±30d, ±90d, ±180d, ±365d windows
      → verify: four corroboration rates printed; included in memo

## Phase 6: Analysis & memo

- [ ] 6.1 Create `scripts/data/ucc/analyze_pilot.py` computing headline metrics
      → verify: match rate, venture-debt prevalence, top-N lenders,
      lifecycle status distribution, M&A corroboration rate, agency
      stratification all printed
- [ ] 6.2 Hand-review 50 random matches (25 DE / 25 CA) for precision
      → verify: precision number recorded in memo
- [ ] 6.3 Write `docs/research/sbir-ucc1-pilot.md` with the gate-condition
      statement and headline numbers
      → verify: memo answers "fraction with venture debt", "top lenders",
      "match precision", "M&A corroboration rate at each window"
- [ ] 6.4 Add a one-paragraph "extend or stop" recommendation to the memo
      → verify: explicit recommendation; if "extend", list which of
      multi-state / IP-collateral / commercial-feed should come next

## Phase 7: Tests

- [ ] 7.1 Unit test for name normalization edge cases (Inc / LLC / Corp,
      punctuation, DBAs)
      → verify: pytest passes
- [ ] 7.2 Unit test for secured-party classifier on the venture-debt seed list
      → verify: pytest passes
- [ ] 7.3 Fixture-based test for matcher on the 20-pair test set
      → verify: pytest passes
- [ ] 7.4 Fixture-based test for `LifecycleReconstructor` covering: clean
      termination, lapsed (no termination, no continuation, >5y),
      assignment chain, orphan UCC-3
      → verify: pytest passes

## Out of scope for this spec

Anything in `design.md` "What This Does NOT Include". If the pilot
recommends extending, open a follow-on spec — do not let scope creep into
this one.
