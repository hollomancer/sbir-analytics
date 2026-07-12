# UCC-1 National Coverage — Tasks

> **Status (2026-07-12):** Not started. Builds on the CA pilot in
> `scripts/data/ucc/` and `specs/ucc1-financing-analysis/`.

## Kill / skip rules (apply before each state batch)

- **Skip permanently:** Delaware (FIPS 10) — no free public portal.
- **Skip until manual review:** portals with hard CAPTCHA, paywalls, or no public
  search after a single probe script run.
- **Stop a state batch** when anti-bot blocks exceed the documented rate limit for
  two consecutive runs without a documented mitigation path.

## Phase 0 — Framework

- [ ] 0.1 Add `UCC1StateExtractor` base class in `scripts/data/ucc/base_extractor.py`
- [ ] 0.2 Refactor `ca_extractor.py` to subclass the base extractor without behavior drift
- [ ] 0.3 Add `registry.py` with FIPS → extractor mapping; register DE as unavailable
- [ ] 0.4 Add coverage-metadata helper (DE exclusion flag + per-state status)

## Phase 1 — First five non-CA states (TX, VA, MA, CO, MD)

- [ ] 1.1 Texas extractor + portal notes (session model, rate limit, anti-bot)
- [ ] 1.2 Virginia extractor + portal notes
- [ ] 1.3 Massachusetts extractor + portal notes
- [ ] 1.4 Colorado extractor + portal notes
- [ ] 1.5 Maryland extractor + portal notes
- [ ] 1.6 Integration test: one known SBIR awardee per state through `matcher.py`

## Phase 2 — Storage and reporting

- [ ] 2.1 Normalize multi-state output to `data/derived/ucc1_filings.parquet`
- [ ] 2.2 Wire refresh cadence under `config/base.yaml` → `enrichment_refresh.ucc1.*`
- [ ] 2.3 Document Delaware-exclusion caveat in F1/A-CP9 reporting templates
