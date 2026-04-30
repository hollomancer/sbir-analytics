# NSF SBIR vs. Private-Capital Comparison — Design

## Architecture

Builds on existing NSF identification, transition detection, PATLINK, and
entity-resolution pipelines. New code lives in `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/`
(an outcomes-comparison artifact, parallel to `leverage_ratio/`).

## Phase 1 — Published-Baseline Comparison

### Data Flow

```
SBIR.gov awards → filter ALN ∈ {47.041, 47.084} → NSF cohort
                                                       ↓
                                          stratify by vintage / phase / CET
                                                       ↓
                                          compute outcome metrics:
                                              - I → II graduation
                                              - II → federal-contract transition
                                              - 5-yr survival proxy
                                              - patent rate
                                              - M&A exit rate (placeholder)
                                                       ↓
                                          present alongside cited VC baselines
                                                       ↓
                                          reconciliation narrative
```

### Components

1. **`NSFCohortBuilder`** — Filters award universe to NSF SBIR (ALN-based),
   stratifies by vintage / phase, attaches CET labels.
2. **`OutcomeMetricsCalculator`** — Reuses existing transition detector, PATLINK,
   and (when available) M&A detection. Emits per-cohort rates with confidence
   intervals (Wilson) and sample sizes.
3. **`PublishedBaselineRegistry`** — Hard-coded table of cited VC baselines with
   source citation + as-of date. Examples:
   - NVCA 2023 Yearbook: seed→A ~33% (5-yr cohort)
   - BLS BED: ~50% 5-yr survival, all small firms
   - Lerner [L10]: SBIR awardees grew 27% faster over 10 yrs (effect size, not rate)
4. **`ReconciliationNarrative`** — For each (NSF metric, baseline) pair, emit
   a structured comparison record: delta, plausible-cause attribution,
   selection-bias caveat. Output as JSON + markdown, mirroring the leverage-
   ratio reconciler.

### Output

- `nsf_cohort_outcomes.parquet` — long-format metrics table (vintage × phase ×
  CET × metric)
- `nsf_vs_published_baselines.md` — human-readable reconciliation narrative
- `nsf_baseline_comparison.json` — structured comparison records for
  programmatic consumption

## Phase 2 — Form D Matched-Cohort Comparison

### Data Flow

```
EDGAR full-text / bulk archives → Form D filings (XML)
                                       ↓
                              parse + normalize fields
                                       ↓
                              CIK ↔ UEI/EIN crosswalk
                                  (EIN, name+state fuzzy, address)
                                       ↓
                          drop Form D issuers matched to any SBIR awardee
                                       ↓
                       match remaining Form D issuers to NSF cohort
                          on (vintage, NAICS-2, state)
                                       ↓
                       compute same outcome metrics on matched cohort
                                       ↓
                       cohort-vs-cohort comparison + threats-to-validity
```

### Components

5. **`FormDIngestor`** — Adds a new `sec_edgar` enrichment source under
   `sbir_etl/enrichers/sec_edgar/`, following the `BaseAsyncAPIClient`
   pattern used by `sam_gov`, `usaspending_api`, `patentsview_api`. Pulls
   Form D submissions from EDGAR (bulk archive preferred over full-text
   search for completeness + rate-limit margin), persists raw XML to
   `data/raw/sec_edgar/form_d/` and parsed records to a DuckDB staging
   table. Idempotent + incremental (track last-processed accession number).
6. **`FormDParser`** — XML → typed records. Captures all fields listed in
   requirement 8. Strict on schema violations; logs to AlertCollector.
7. **`CIKCrosswalk`** — Extends the existing production `VendorCrosswalk`
   class (`packages/sbir-ml/sbir_ml/transition/features/vendor_crosswalk.py`)
   by adding a `cik` field to `CrosswalkRecord`, a `find_by_cik` accessor,
   and an `_index_cik` lookup map alongside the existing UEI/CAGE/DUNS
   indexes. Implements the EIN-then-fuzzy-name cascade on top of existing
   `find_by_name` machinery. Outputs per-record match confidence and method
   tier. Reports per-vintage match rate (Phase 2 gate: ≥30% before
   continuing).
8. **`PrivateCapitalCohortBuilder`** — Filters Form D issuers to those *not*
   matched to any SBIR awardee. Buckets by vintage / NAICS-2 / state.
9. **`CohortMatcher`** — Coarsened-exact matching on (vintage-year, NAICS-2,
   state). Reports cohort balance and unmatched residuals. No propensity
   scoring in v1 — intentionally simple, defensible, and reproducible.
10. **`ThreatsToValidity`** — Emits a structured caveats record with the five
    required entries (SAFE undercount, late-stage inclusion, NAICS noise,
    crosswalk floor, selection bias). This component runs *first* in the
    pipeline and gates the headline output — if any required caveat is
    missing or stale, the headline is suppressed.

### CIK ↔ UEI/EIN Crosswalk Strategy

The crosswalk is the highest-risk component. Tiered approach:

- **Tier A (high confidence, ~5–15% expected):** Form D EIN supplied + matches
  EIN in vendor universe. Confidence 0.95.
- **Tier B (medium, ~15–30%):** Issuer name (normalized) + state exact match
  to vendor universe. Confidence 0.75.
- **Tier C (low, ~10–20%):** Issuer name fuzzy match (rapidfuzz, ≥90 score) +
  state + city match. Confidence 0.50.
- **Unmatched:** the rest. Reported as residual.

Backtest set: a hand-labeled sample of 200 issuer↔awardee pairs, drawn from
known SBIR firms with public Form D filings (e.g., from PR #286 and existing
SEC EDGAR research). Target: Tier A+B precision ≥0.95, recall (against
backtest) ≥0.50.

### Output

- `form_d_filings.parquet` — parsed Form D records
- `cik_uei_crosswalk.parquet` — match table with confidence + tier
- `private_capital_cohort_outcomes.parquet` — long-format metrics, parallel
  schema to NSF cohort
- `nsf_vs_form_d_comparison.md` — headline reconciliation narrative
- `threats_to_validity.json` — gating caveats record

## Methodology Notes

### Why Form D, not seed-VC-only

Per user redirect: broader Form D coverage (debt, late-stage, multiple
instrument types) is treated as feature. The framing is "private capital
broadly" rather than "seed VC narrowly." This makes the comparison more
robust to SAFE undercount (which is a seed-stage problem) at the cost of
being a coarser instrument-mix. Phase 2 component 14 (security-type
decomposition) preserves the option of zooming in on the seed slice if
downstream readers want it.

### Why no propensity scoring in v1

Coarsened-exact matching is reproducible, debuggable, and matches the
conservative tone of the leverage-ratio spec. Propensity scoring requires
firm-level covariates that don't reliably exist on the Form D side
(founding date, founder background, prior funding). Defer to a v2 if v1
yields a publishable result.

### Why no causal claim

The user asked for a comparison; the scope-guard flagged that NSF-vs-private
selection bias is severe and one-way. We deliberately frame the deliverable
as "descriptive comparison with reconciliation narrative" — same posture
as `leverage-ratio-analysis`. Causal claims (e.g., "NSF SBIR causes
N% higher transition than private capital would have") require RDD or IV
designs and are explicitly out of scope.

## Risks

- **CIK↔UEI match rate <30%**: Phase 2 gate triggers stop-and-discuss. Likely
  outcome: drop CIK matching as primary key, fall back to name+state-only
  cohort buckets without firm-level joining.
- **Form D ingest scope creep**: this spec is the canonical implementation;
  M&A spec consumes the artifact. Coordinate with whoever picks up the M&A
  spec to avoid duplicate ingest pipelines.
- **NSF cohort size**: NSF SBIR is smaller than DoD; vintage-stratified Wilson
  intervals may be wide. Pre-register minimum cohort size (n=50 per stratum)
  before reporting stratified rates.
