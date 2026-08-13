# Tasks: SBIR M&A Signal Counts by Fiscal Year

> **Status (2026-08-09):** Implementation complete; real-data materialization
> blocked by the unavailable historical input artifact. The former match-rate
> and Dagster plan is superseded.

## T0. Review the former design

- [x] Verify the curated JSONL schema and date semantics.
- [x] Audit the proposed numerator and denominator grain.
- [x] Confirm whether Item 2.01 can be isolated from the curated schema.
- [x] Search development, live, persistent-runtime, and historical PR artifacts
  for the real input.
  - Result: the proposed rate was incoherent, Item 2.01 is not recoverable, and
    the gitignored real artifact and upstream refinement inputs are absent.

## T1. Implement the fail-closed count reporter

- [x] Add `scripts/data/sbir_ma_signal_counts_by_fy.py`.
- [x] Validate UTF-8 JSONL, company name, tier, and exact ISO dates.
- [x] Fingerprint source bytes and deduplicate normalized name keys.
- [x] Assign signal-observation FY and aggregate FY2015–FY2024 tier counts.
- [x] Reconcile overall and per-tier date categories.
- [x] Render deterministic CSV and Markdown with explicit evidence limits.

## T2. Unit tests

- [x] Test September 30 / October 1 FY boundaries.
- [x] Test missing, invalid, out-of-window, and tier reconciliation.
- [x] Test case/edge-whitespace duplicate collapse and conflict failure.
- [x] Test strict malformed/empty input rejection.
- [x] Test deterministic output bytes and source fingerprinting.
- [x] Test missing input creates no plausible empty report.
- [x] Test path-alias rejection and staged-publication rollback.
- [x] Test the output contract excludes rate/control/Item-2.01 claims.

## T3. Materialize the real report

- [ ] Supply a reviewed `data/sbir_ma_events.jsonl` artifact with a retained
  fingerprint and documented tier lineage.
- [ ] Run the reporter twice and verify byte-identical CSV/Markdown.
- [ ] Review annual counts and all exclusion diagnostics before publication.
  - **Blocked:** the historical source was gitignored and is unavailable; old
    aggregate totals cannot reconstruct a fiscal-year series.

## T4. Quality checks

- [x] Run focused pytest, Ruff, MyPy, documentation checks, and `git diff
  --check` on this implementation.
- [x] Run the repository unit suite before publication.

## Superseded scope

The following former tasks are intentionally removed from this quick
diagnostic: awardee denominators, FY match/exit rates, Wilson intervals,
Item-2.01 sub-rates, raw EFTS/Form D re-union, firm-detail duplication, and a
Dagster asset. Any genuine cohort rate requires a new reviewed design with a
common cohort grain, fixed horizon, censoring, canonical identity, and
symmetric outcome coverage.
