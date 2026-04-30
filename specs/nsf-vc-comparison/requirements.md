# NSF SBIR vs. Private-Capital Comparison — Requirements

Research-questions tags: **B2/B3** (commercialization), **A4** (private-capital signals),
**[L21]** (ITIF "America's Seed Fund"), **[L10]** (Lerner), **[L11]** (Howell), **[L23]** (Form D).

## Background

ITIF [L21] frames NSF SBIR as the federal analogue of a seed-stage venture fund.
Lerner [L10] and Howell [L11] establish empirically that SBIR awardees grow
faster, attract more follow-on private capital, and produce more patents than
matched non-awardees — but neither study uses a *private-capital cohort* as the
control group. This spec builds that comparison for NSF specifically: how does
the NSF SBIR portfolio perform on commercialization-outcome metrics relative to
firms financed via private capital (Reg D / Form D filers)?

The user-stated framing: "compare NSF SBIR portfolio rank against pre-seed/seed
VCs." Per scope review, we drop the "rank" composite and frame the deliverable
as a **comparison table with reconciliation narrative**, matching the pattern
established by `specs/leverage-ratio-analysis/`. Form D is intentionally
*not* filtered to seed-only — its broader coverage (debt, later-stage, multiple
instrument types) is treated as feature, not bug, because the policy question
is "what private-capital alternative would these firms otherwise rely on,"
not "what would seed VCs alone do."

## Phasing

This spec ships in two sequential phases, each independently useful.

- **Phase 1 — Published-baseline comparison.** Compute NSF SBIR cohort outcomes
  on metrics with cited public VC baselines (Lerner, Howell, ITIF, NVCA/CB
  Insights public summaries). No new data ingest.
- **Phase 2 — Form D matched-cohort comparison.** Ingest SEC EDGAR Form D
  filings, build a CIK ↔ UEI/EIN crosswalk, construct a matched cohort of
  private-capital-financed firms, and compute the same outcome metrics on the
  matched cohort.

Phase 1 is the gating deliverable. Phase 2 is contingent on Phase 1 yielding a
defensible NSF metric set and on Form D ingest landing for A4 / M&A.

## Phase 1 Requirements

1. **SHALL** isolate the NSF SBIR cohort using ALN `47.041` and `47.084`
   (existing identification classifier).
2. **SHALL** compute the following NSF-cohort outcomes, stratified by award
   vintage (5-year buckets) and Phase (I, II):
   - Phase I → Phase II graduation rate
   - Phase II → first non-SBIR federal contract transition rate (reuse
     existing transition detector, ≥85% precision benchmark)
   - 5-year survival proxy (firm appears as recipient/vendor in any federal
     dataset 5 years post-Phase-II)
   - Patent rate (patents linked to award via PATLINK / award-recipient ÷
     awards)
   - M&A exit rate (placeholder — populated when M&A spec lands; emit
     "not-yet-available" until then)
3. **SHALL** present results alongside cited public VC baselines:
   - Seed → Series A graduation (NVCA / CB Insights public summaries)
   - 5-year startup survival (BLS BED, public)
   - Exit rate at 5 / 10 years (NVCA, public)
   - Lerner [L10] and Howell [L11] published effect sizes
4. **SHALL** produce a reconciliation narrative explaining each delta between
   the NSF metric and the cited VC baseline, including selection-bias caveats
   ("NSF awardees pre-selected on technical merit and proposal quality; VC-
   financed firms self-select on lawyer access and growth narrative").
5. **SHOULD** stratify NSF outcomes by CET technology area (reuse CET
   classifier) so the comparison is not blurred by sector mix.
6. **SHALL** report match rates and entity-resolution coverage as sensitivity
   metadata (mirrors `leverage-ratio-analysis` requirement 7).

### Phase 1 Gate Condition

Can produce a single artifact (notebook or markdown report) that states:
"NVCA reports seed→A graduation at ~30%. NSF Phase I→II graduation is [X]%
on cohort [vintage range, n=Y]. The difference is attributable to [Z]."
Reproduces the exact reconciliation pattern of `leverage-ratio-analysis`.

## Phase 2 Requirements

7. **SHALL** ingest SEC EDGAR Form D filings (XML/JSON via EDGAR full-text or
   bulk archives), persisted to the standard staging layout (DuckDB-backed).
   Coordinates with existing `sec_edgar` enrichment-source config in
   `config/base.yaml` (currently disabled-by-default stub).
8. **SHALL** parse Form D fields needed for cohort comparison: filer CIK,
   issuer name + address + state, issuer NAICS (self-reported), filing date,
   amount sold, total offering, security type (equity / debt / option /
   convertible), industry group, minimum-investment-accepted.
9. **SHALL** construct a CIK ↔ UEI/EIN crosswalk using:
   - EIN where Form D supplies it (often blank; record availability rate)
   - Issuer-name + state fuzzy match against the existing entity-resolution
     vendor universe (UEI → CAGE → DUNS cascade, name fallback)
   - Address normalization for tie-breaking
   - Crosswalk match rate must be reported per cohort year; under 30% match
     triggers a Phase 2 stop-and-discuss gate.
10. **SHALL** define the comparison cohort as Form D issuers that are *not*
    matched to any SBIR awardee (so we compare NSF-funded firms vs.
    privately-financed firms with no SBIR exposure).
11. **SHALL** match NSF and Form D cohorts on covariates: vintage year, NAICS-2
    sector, state. Document the resulting cohort sizes and balance.
12. **SHALL** compute the same outcomes from Phase 1 on the Form D cohort,
    using the same federal-contract / patent / M&A signals (where applicable
    to private firms).
13. **SHALL** publish a threats-to-validity section before any headline
    finding. Required entries: SAFE/convertible undercount, late-stage
    inclusion, NAICS self-report noise, CIK↔UEI match-rate floor, technical-
    merit vs. lawyer-access selection bias.
14. **SHOULD** decompose the Form D cohort by security-type and offering size
    so that downstream readers can isolate the (noisy but estimable) seed-
    stage subset if they want.

### Phase 2 Gate Condition

Can state: "On vintage [X], NAICS-2 [Y], state [Z]: NSF Phase II awardees
transitioned to federal contract at [A]% within 5 years; matched Form D
issuers transitioned at [B]%. Selection-bias and matching caveats below."
The reconciliation matters more than the headline number.

## Dependencies

- NSF identification (ALN 47.041 / 47.084) — `sbir_etl/models/sbir_identification.py` (EXISTS)
- Transition detection (≥85% precision) — `packages/sbir-ml/sbir_ml/transition/` (EXISTS)
- Entity resolution cascade — UEI/DUNS/CAGE/fuzzy-name (EXISTS)
- PATLINK patent linkage (EXISTS)
- CET classifier (EXISTS, used for Phase 1 stratification)
- M&A detection — `specs/merger_acquisition_detection/` (REQUIREMENTS-ONLY;
  Phase 1 emits placeholder, Phase 2 consumes when available)
- SEC EDGAR ingest stub — `config/base.yaml` `sec_edgar` source (DISABLED;
  Phase 2 enables and implements)
- Form D ingest is also implicitly claimed by the M&A spec; Phase 2 of this
  spec is the canonical implementation, M&A spec consumes the same artifacts.

## Out of Scope

- Composite "portfolio rank" / scoring construct — explicitly rejected.
- Crunchbase / PitchBook integration (deferred to a future licensed-data spec).
- Causal-effect estimation. This spec is descriptive comparison only; any
  causal claims require IV / regression-discontinuity machinery beyond scope.
- Non-NSF SBIR programs. DoD / NIH / DOE comparisons are downstream extensions.
