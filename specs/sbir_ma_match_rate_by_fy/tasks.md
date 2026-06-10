# Tasks: SBIR M&A Match Rate by Fiscal Year

Estimated total: 1–1.5 days. No new extraction; analysis only.

## T0. Resolve open questions (design.md §"Open questions")

- [ ] Confirm canonical join key between awards and SEC enrichment
  (UEI/DUNS vs. normalized company name) for both `sbir_ma_events.jsonl`
  and the `sec_edgar_enriched_companies` asset.
- [ ] Confirm `data/form_d_details.jsonl` schema and SBIR-firm linkage
  (CIK and/or normalized name).
- [ ] Confirm `data/sec_edgar_scan.jsonl` mention columns and
  classification labels.
- [ ] Decide FY2024 right-censoring policy (footnote vs. exclude).
  → verify: each question answered in design.md before T1.

## T1. Implement match-rate script

- [ ] Create `scripts/analysis/sbir_ma_match_rate_by_fy.py`.
- [ ] Build awardee denominator (FY2015–2024, distinct firms).
- [ ] Union dated signal sources with tier + signal-type labels.
- [ ] Tier-rank dedupe (one row per firm).
- [ ] Compute per-FY counts and rates; Wilson CI on aggregate.
- [ ] Compute Item-2.01-only sub-rate.
- [ ] Write three output files to `reports/`.
  → verify: run end-to-end on local parquets; rows match
  `awardees_in_fy ≥ matched_total`; aggregate rate is in
  plausible range (5–15% based on prior 8.1% all-time figure).

## T2. Unit tests

- [ ] `tests/unit/scripts/test_ma_match_rate_by_fy.py`:
  - Tier-rank dedupe with synthetic firm having High + Low signals.
  - FY boundary cases (Sep 30 vs. Oct 1).
  - Exhibit-21-only match flagged `date_upper_bound = true`.
  - Wilson CI matches a known reference value.
  - Item 2.01 sub-rate filters correctly when 1.01 also present.
  → verify: `pytest tests/unit/scripts/test_ma_match_rate_by_fy.py -v`.

## T3. Dagster asset

- [ ] `packages/sbir-analytics/sbir_analytics/assets/sbir_ma_match_rate.py`.
- [ ] Thin wrapper that invokes the script and registers
  outputs as Dagster assets for the `reports/` files.
- [ ] No new resources; reuse existing parquet IO managers.
  → verify: `dagster asset materialize --select sbir_ma_match_rate_by_fy`
  produces all three reports.

## T4. Report and write-up

- [ ] Populate `reports/sbir_ma_match_rate_by_fy.md` with: methodology,
  per-FY table, aggregate FY2015–2024 row with CI, Item 2.01 footnote,
  caveats (Exhibit-21 dating, private acquirers, right-censoring,
  pre-window acquisitions).
- [ ] Cross-link from `docs/research-questions.md` A4.
  → verify: numbers in MD match the CSV exactly; markdown lints clean.

## T5. Quality sweep

- [ ] Run `quality-sweep` agent on changed files.
- [ ] Run full test suite: `pytest tests/unit -v`.
  → verify: zero ruff / mypy errors; all tests pass.

## Out of scope (not in this spec)

- Form 15 (deregistration) extraction.
- Per-item-code attribution from EFTS (would require re-fetching).
- Acquirer market-cap / sector enrichment.
- Backfill of acquisitions before FY2015.
