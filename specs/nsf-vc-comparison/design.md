# NSF SBIR vs. Private-Capital Comparison — Design

## Architecture

Builds on existing NSF identification, transition detection, PATLINK,
entity-resolution pipelines, and (post-merge) the SEC EDGAR / Form D / M&A
infrastructure landed by PR #286. New code lives in
`packages/sbir-analytics/sbir_analytics/assets/nsf_vc/` (an outcomes-comparison
artifact, parallel to `leverage_ratio/`).

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
                                              - M&A exit rate (#286 join)
                                                       ↓
                                          present alongside cited VC baselines
                                                       ↓
                                          reconciliation narrative
```

### Components

1. **`NSFCohortBuilder`** — Filters award universe to NSF SBIR (ALN-based),
   stratifies by vintage / phase, attaches CET labels.
2. **`OutcomeMetricsCalculator`** — Reuses existing transition detector,
   PATLINK, and #286's `sbir_ma_events.jsonl` for the M&A-exit metric. Emits
   per-cohort rates with Wilson confidence intervals and sample sizes.
3. **`PublishedBaselineRegistry`** — Hard-coded table of cited VC baselines
   with source citation + as-of date. Examples:
   - NVCA 2023 Yearbook: seed→A ~33% (5-yr cohort)
   - BLS BED: ~50% 5-yr survival, all small firms
   - Lerner [L10]: SBIR awardees grew 27% faster over 10 yrs (effect size)
4. **`ReconciliationNarrative`** — For each (NSF metric, baseline) pair,
   emit a structured comparison record: delta, plausible-cause attribution,
   selection-bias caveat. Output as JSON + markdown, mirroring the leverage-
   ratio reconciler.

### Output

- `nsf_cohort_outcomes.parquet` — long-format metrics table (vintage × phase
  × CET × metric)
- `nsf_vs_published_baselines.md` — human-readable reconciliation narrative
- `nsf_baseline_comparison.json` — structured comparison records

## Phase 2 — NSF-vs-Private-Capital Matched Cohort

Gated on PR #286 merging to main. Phase 2 is a pure analysis layer over
#286's outputs — no ingest, no parsing, no CIK resolution.

### Data Flow

```
#286 outputs:                              SBIR awards:
  - sec_edgar_enrichment asset               - NSF filter (ALN 47.041/47.084)
  - sbir_ma_events.jsonl                          ↓
  - resolved CIK ↔ SBIR-company set         NSF SBIR cohort
       ↓                                          ↓
filter Form D index → drop matches ↔ any SBIR co
       ↓
non-SBIR Form D control universe
       ↓
bucket by (filing year, NAICS-2, state)
       ↓                                          ↓
                cohort matching (coarsened-exact)
                        ↓
              compute outcomes on both sides:
                - federal-contract presence (FPDS join, both sides)
                - patent rate (PATLINK, both sides)
                - M&A exit rate (#286 events, both sides)
                - Phase graduation / survival (NSF only, control N/A)
                        ↓
              cohort-vs-cohort delta + threats-to-validity
```

### Components

5. **`NSFAwardeeFilter`** — Apply ALN 47.041 / 47.084 filter to the
   SBIR-CIK resolution set produced by #286's `sec_edgar_enrichment`.
   Output: NSF-CIK set + NSF-UEI set.
6. **`PrivateCapitalControlCohortBuilder`** — Read #286's Form D index
   table, drop any issuer whose CIK appears in the broader SBIR-CIK set
   (not just NSF — we want the control to be capital-financed-but-no-SBIR
   firms, period). Bucket the remainder by (filing-year, NAICS-2, state).
7. **`CohortMatcher`** — Coarsened-exact matching on (vintage-year,
   NAICS-2, state). Reports cohort balance and unmatched residuals. No
   propensity scoring in v1 — intentionally simple and reproducible.
8. **`MatchedCohortOutcomes`** — Joins both cohorts to FPDS contracts,
   PATLINK patents, and #286's M&A events table. Emits per-cohort rates
   with Wilson CIs.
9. **`ThreatsToValidity`** — Emits the structured caveats record. Required
   entries:
   - SAFE/convertible undercount (Form D weak on these)
   - Late-stage Form D inclusion (we are intentionally broader than seed)
   - NAICS self-report noise on Form D issuers
   - #286's CIK-resolution recall (~28% of SBIR companies appear in EDGAR)
   - Technical-merit vs. lawyer-access selection bias
   - Control-cohort excludes pre-Form-D SBIR awardees who *later* raised
     capital (timing leak)

   This component runs *first* and gates the headline output — if any
   required caveat is missing or stale, the headline is suppressed.

### Output

- `nsf_vs_form_d_comparison.parquet` — long-format cohort-vs-cohort metrics
- `nsf_vs_form_d_comparison.md` — headline reconciliation narrative
- `threats_to_validity.json` — gating caveats record

## Methodology Notes

### Why Form D, not seed-VC-only

Per user direction: broader Form D coverage (debt, late-stage, multiple
instrument types) is treated as feature. The framing is "private capital
broadly" rather than "seed VC narrowly." This makes the comparison more
robust to SAFE undercount (a seed-stage-specific blind spot) at the cost
of a coarser instrument mix. PR #286's Form D scoring tiers are exposed
to downstream readers via component 12 of the requirements so they can
zoom in on a tighter slice if they want.

### Why no propensity scoring in v1

Coarsened-exact matching is reproducible, debuggable, and matches the
conservative tone of the leverage-ratio spec. Propensity scoring requires
firm-level covariates that don't reliably exist on the Form D side
(founding date, founder background, prior funding). Defer to a v2 if v1
yields a publishable result.

### Why no causal claim

The user asked for a comparison; the scope-guard flagged that NSF-vs-
private selection bias is severe and one-way. We deliberately frame the
deliverable as "descriptive comparison with reconciliation narrative" —
same posture as `leverage-ratio-analysis`. Causal claims (e.g., "NSF
SBIR causes N% higher transition than private capital would have")
require RDD or IV designs and are out of scope.

### Why Phase 2 doesn't extend `VendorCrosswalk`

Earlier draft proposed extending `VendorCrosswalk` with a CIK field. PR
#286 already does CIK resolution (via 3-layer filtering with city
disambiguation) and exposes the resolved set as the canonical SBIR-CIK
mapping. Modifying `VendorCrosswalk` here would conflict with #286 or
duplicate effort — defer any cross-cutting refactor to a follow-on once
both branches have settled.

## Risks

- **PR #286 merges with significant changes to its output schema**: the
  Phase 2 components reference #286's table layout. If #286's review
  prompts schema changes before merge, Phase 2's data-access layer needs
  a one-pass update. Cost: ~1 day of touch-up, not a blocker.
- **NSF cohort size**: NSF SBIR is smaller than DoD; vintage-stratified
  Wilson intervals may be wide. Pre-register minimum cohort size (n=50
  per stratum) before reporting stratified rates.
- **Form D control cohort dwarfs NSF cohort**: many more Form D filers
  than NSF awardees. Matched-cohort reporting must match 1:k or use
  weighting; document explicitly.
- **Timing leak in control cohort**: Form D issuers may have filed *after*
  receiving SBIR. Today's spec drops issuers matched to SBIR ever.
  Acceptable for v1, flagged in threats-to-validity.
