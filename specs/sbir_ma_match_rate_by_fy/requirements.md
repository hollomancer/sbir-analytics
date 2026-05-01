# Requirements: SBIR M&A Match Rate by Fiscal Year

## Question of record

What is the SBIR-awardee → M&A-event match rate for FY2015–2024,
attributable by fiscal year, using SEC filings as evidence?

The user's literal question is "8-K Item 2.01 match rate." That cannot
be answered in isolation: Item 2.01 has ~30–40% precision alone (per
`docs/research/sbir-ma-exit-analysis.md:40-42`) and is bucketed with
Item 1.01 in the existing pipeline. We answer the underlying question
by combining the full signal stack.

## Scope

- **In:** SBIR awardees (any agency) with ≥1 award FY2015–2024,
  matched against SEC filings indicating acquisition in the same window.
- **In:** Per-FY breakdown of match counts and rates.
- **In:** Signal-tier breakdown (high / medium / low confidence).
- **Out:** New signal extraction — reuse existing `EdgarMAEvent`,
  `EdgarMention`, and Form D enrichment outputs.
- **Out:** Re-running EFTS or Form D fetches.
- **Out:** Backfilling Form 15 (deregistration) — tracked separately.

## Definitions

- **Awardee universe (denominator):** distinct SBIR firms with award
  start date in FY2015–2024 (federal FY: Oct 1 – Sep 30).
- **Match (numerator):** awardee has ≥1 dated M&A signal where the
  signal's filing date falls in FY2015–2024.
- **Acquisition FY:** fiscal year of the earliest qualifying signal
  per awardee (one match per firm).
- **Confidence tier per match:** the highest tier among that firm's
  qualifying signals, using the existing tier rules in
  `scripts/data/detect_sbir_ma_events.py`.

## Signals used and date attribution

| Signal | Tier | Date used |
|---|---|---|
| `subsidiary` (Exhibit 21) | High | First 10-K filing date listing firm — **upper bound only** |
| Form D `is_business_combination` | High | Form D filing date |
| `acquisition` (10-K/10-Q text) | Medium | Filing date of the confirming 10-K/10-Q |
| `ma_definitive` 8-K (Item 1.01/2.01) | Low | 8-K filing date |
| `ma_definitive` tender (SC TO-T, SC 14D9) | Low | Tender filing date |
| `ma_proxy` (DEFM14A/PREM14A) | Low | Proxy filing date |
| `ownership_active` (SC 13D) | Low | 13D filing date (pre-event marker) |

Exhibit 21 alone cannot date a transaction. When Exhibit 21 is the
only signal, the match is attributed to the FY of the earliest 10-K
in which the firm appears — flagged as `date_upper_bound = true`.

## Outputs

1. `reports/sbir_ma_match_rate_by_fy.csv` — one row per FY, columns:
   `fiscal_year, awardees_in_fy, matched_high, matched_medium,
   matched_low, matched_total, match_rate_high, match_rate_total`.
2. `reports/sbir_ma_match_rate_by_fy.md` — narrative summary with
   methodology, caveats, and the FY2015–2024 aggregate.
3. `reports/sbir_ma_matched_firms_fy2015_2024.csv` — firm-level
   detail: `award_recipient, primary_award_fy, match_fy,
   tier, signals, acquirer (if known), date_upper_bound`.

## Acceptance criteria

- AC1: Numerator and denominator are reproducible from existing
  parquet outputs (no new network calls required).
- AC2: Per-FY denominator equals the count of distinct firms whose
  earliest FY2015–2024 award is in that FY.
- AC3: Each matched firm appears exactly once (deduped on firm key).
- AC4: Aggregate FY2015–2024 high+medium match rate is reported with
  a 95% Wilson confidence interval.
- AC5: The Item-2.01-only sub-rate is reported as a methodological
  footnote, not as the headline number.
- AC6: Caveats section explicitly addresses: Exhibit-21 dating,
  private acquirers (no SEC filings), SBIR firms acquired before any
  award in the window, and right-censoring (recent acquisitions not
  yet filed).
