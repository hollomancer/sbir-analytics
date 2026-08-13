# Requirements: SBIR M&A Signal Counts by Fiscal Year

**Target epistemic tier:** `exploratory`

> **Status (2026-08-09):** The original match-rate design is superseded. The
> fail-closed signal-count reporter is implemented, but a real-data report is
> blocked because `data/sbir_ma_events.jsonl` is unavailable.
>
> **Research question anchor:** F2 — M&A evidence by vintage, descriptive
> diagnostic only.

## Question of record

How many normalized SBIR company-name keys in a supplied, fingerprinted M&A
signal artifact have observation dates in each federal fiscal year from FY2015
through FY2024, by upstream confidence tier?

This deliverable does **not** estimate an acquisition rate, exit rate, hazard,
or treatment effect. The prior design grouped numerators by signal fiscal year
and denominators by first-award fiscal year. Those are different populations,
so their quotient is not a coherent incidence or cohort rate. A future rate
must use the same award-vintage cohort in both numerator and denominator and
define a fixed observation horizon and censoring policy.

## Evidence boundary

- Input: `data/sbir_ma_events.jsonl`, produced historically by
  `scripts/archive/data/detect_sbir_ma_events.py`.
- Grain: one normalized `company_name` key, using only `strip()` and
  case-folding.
- Observation date: top-level `event_date`.
- Federal FY: October through December map to the following calendar year;
  January through September map to the current calendar year.
- Confidence: the exact `high`, `medium`, or `low` value present in the
  supplied artifact. Low is sensitivity-only.
- Window: FY2015–FY2024 by default.

The top-level date is a hybrid signal-observation proxy. The historical
producer selected the earlier valid date between an issuer's earliest Form D
business-combination filing and its aggregate latest EFTS mention. It is not a
transaction announcement, agreement, or closing date, and it can be unrelated
to the signal supporting the row's winning confidence tier.

The artifact contains SBIR-only detected names. Its rows are not verified
distinct firms, deals, acquisitions, or exits, and it provides no outcome
coverage for a non-SBIR comparison cohort.

## Outputs

When a valid input is supplied, the reporter writes:

1. `reports/sbir_ma_signal_counts_by_fy.csv` — one row per selected FY with
   high, medium, high-plus-medium, low-sensitivity, and total normalized-name
   key counts.
2. `reports/sbir_ma_signal_counts_by_fy.md` — the same table plus input
   fingerprint, input/deduplication counts, date-status reconciliation, method,
   and interpretation limits.

Generated reports remain gitignored. The source artifact's SHA-256 and byte
count are embedded in the Markdown output so a later materialization identifies
the exact evidence supplied.

## Acceptance criteria

- AC1: `2020-09-30` maps to FY2020 and `2020-10-01` maps to FY2021.
- AC2: Missing, invalid, valid-out-of-window, and in-window dates are counted
  separately and reconcile overall and within each tier.
- AC3: Case- and edge-whitespace-equivalent company names count once when date
  and tier agree; conflicting duplicates fail validation.
- AC4: High plus medium and total tier columns reconcile in every FY row.
- AC5: Input SHA-256, bytes, input rows, distinct keys, and collapsed duplicates
  appear in deterministic output.
- AC6: Missing, empty, malformed, non-UTF-8, or contract-violating input exits
  nonzero before an all-zero report can be written.
- AC7: Input and output paths cannot alias; both outputs are staged before
  publication and a partial replacement is rolled back.
- AC8: Outputs contain no rate, exit-rate, control, Wilson-interval, Item-2.01,
  or causal-comparison fields or claims.
- AC9: No network call, raw SEC reconstruction, Dagster asset, or firm-detail
  duplicate is added.

## Materialization gate

The historical JSONL was gitignored and was not committed with PR #286. The
2026-08-09 audit found neither it nor its upstream Form D/EFTS refinement
artifacts in the development checkout, live checkout, or persistent runtime
data. Only published aggregate tier totals remain; they cannot recover exact FY
counts, missing dates, duplicate diagnostics, or an input fingerprint.

The final published tier assignments also cannot be regenerated from the
tracked producer alone because the refinement/apply-back artifacts are absent.
The reporter therefore describes only the tiers in the exact supplied artifact
and must not assert the historical published totals.

## Deferred requirements for a genuine rate

A separately reviewed design is required before reporting a rate. It must, at
minimum, define a canonical firm identity, assign numerator events to the same
award-vintage cohort used for the denominator, use a fixed follow-up horizon,
handle left and right censoring, establish symmetric outcome coverage, and
retain per-filing provenance. Item 2.01 cannot be isolated from the curated
JSONL schema because its aggregate signal fields conflate filing items/types.
