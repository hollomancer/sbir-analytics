# UCC-1 Financing Analysis — Tasks

## Phase 0: Feasibility check (before any code)

- [ ] 0.1 Manually pull UCC-1 records for 5 known SBIR firms via DE web search
      → verify: filings retrievable, schema fields available, rate limits observable
- [ ] 0.2 Manually pull UCC-1 records for 5 known SBIR firms via CA bizfileOnline
      → verify: same as above for CA
- [ ] 0.3 Confirm Form D high-confidence cohort export path and field names
      → verify: cohort CSV/JSONL accessible with `company_name`, `state`, `agency`, `first_award_year`
- [ ] 0.4 Document any access blockers in `docs/research/sbir-ucc1-pilot.md` stub
      → verify: stub committed; gate-condition statement template in place

If 0.1 or 0.2 reveal CAPTCHA / aggressive blocking, stop and revisit
sourcing before proceeding.

## Phase 1: Extraction

- [ ] 1.1 Create `scripts/data/ucc/de_extractor.py` with `DEExtractor` class
      → verify: returns normalized records for the 5 firms from 0.1
- [ ] 1.2 Create `scripts/data/ucc/ca_extractor.py` with `CAExtractor` class
      → verify: same for CA
- [ ] 1.3 Define common output schema in `scripts/data/ucc/schema.py` (TypedDict)
      → verify: both extractors emit the schema; mypy/ruff clean
- [ ] 1.4 Add per-state rate-limiting and resumable run state (sqlite or jsonl checkpoint)
      → verify: kill / restart preserves progress on a 20-firm sample
- [ ] 1.5 Bulk run over Form D high-confidence cohort, write `data/ucc1_pilot_raw.jsonl`
      → verify: row count > 0 per state; per-firm latency logged

## Phase 2: Matching

- [ ] 2.1 Create `scripts/data/ucc/matcher.py` with `UCCMatcher` reusing
      `sbir_etl` name-normalization helpers
      → verify: hand-curated 20-pair test set (10 match / 10 non-match) passes
- [ ] 2.2 Tag each raw filing with `match_confidence` ∈ {high, medium, low}
      → verify: histogram of tiers logged
- [ ] 2.3 Drop low-confidence matches; write `data/ucc1_pilot_matches.jsonl`
      → verify: schema validated; sample of 10 inspected

## Phase 3: Secured-party classification

- [ ] 3.1 Seed `data/ucc1_pilot_lender_taxonomy.json` with the venture-debt
      lender list from `design.md`
      → verify: file exists; counts of distinct secured parties printed
- [ ] 3.2 Classify each match; log unknowns ranked by frequency
      → verify: top-50 unknowns reviewed; taxonomy extended as warranted
- [ ] 3.3 Flag foreign secured parties (address country ≠ US)
      → verify: count printed; spot-check 5

## Phase 4: Analysis & memo

- [ ] 4.1 Create `scripts/data/ucc/analyze_pilot.py` computing headline metrics
      → verify: match rate, venture-debt prevalence, top-N lenders, agency
      stratification all printed
- [ ] 4.2 Hand-review 50 random matches (25 DE / 25 CA) for precision
      → verify: precision number recorded in memo
- [ ] 4.3 Write `docs/research/sbir-ucc1-pilot.md` with the gate-condition
      statement and headline numbers
      → verify: memo answers "fraction with venture debt", "top lenders",
      "match precision"
- [ ] 4.4 Add a one-paragraph "extend or stop" recommendation to the memo
      → verify: explicit recommendation; if "extend", list which of
      multi-state / UCC-3 lifecycle / IP-collateral / commercial-feed
      should come next

## Phase 5: Tests

- [ ] 5.1 Unit test for name normalization edge cases (Inc / LLC / Corp,
      punctuation, DBAs)
      → verify: pytest passes
- [ ] 5.2 Unit test for secured-party classifier on the venture-debt seed list
      → verify: pytest passes
- [ ] 5.3 Fixture-based test for matcher on the 20-pair test set
      → verify: pytest passes

## Out of scope for this spec

Anything in `design.md` "What This Does NOT Include". If the pilot
recommends extending, open a follow-on spec — do not let scope creep into
this one.
