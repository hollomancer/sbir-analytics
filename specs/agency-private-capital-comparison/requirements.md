# SBIR vs. Private-Capital Comparison — Requirements (agency-parameterized; NSF as initial target)

> **Status:** Phase 1 implemented; Phase 2 is a gated backlog item now that the
> Form D / M&A infrastructure from PR #286 is available. Do not start Phase 2
> until the private-capital control-cohort comparison is selected as a current
> research priority.
> Supports inventory questions **F3** (private-capital comparison), **B2** (commercialization outcomes), **B3** (transition rates) in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** F3 / B2 / B3 — SBIR vs. private-capital cohort comparison (NSF initial target)
**Answers for:** entrepreneurial finance researchers, SBIR program managers, policy analysts
**Complexity tier:** Relational → Inferential (Tier 2–3)

---

## Done when

> **Phase 1:** A policy analyst can state: "NVCA reports seed→A graduation at ~30%. NSF Phase I→II graduation is [X]% on cohort [vintage range, n=Y]. The difference is attributable to [Z]." Produces the exact reconciliation pattern of `leverage-ratio-analysis`.
>
> **Phase 2:** An entrepreneurial finance researcher can state: "On vintage [X], NAICS-2 [Y], state [Z]: NSF Phase II awardees transitioned to federal contract at [A]% within 5 years; matched non-SBIR Form D issuers transitioned at [B]%. Selection-bias and matching caveats: [see threats-to-validity section]."

---

## User Stories

**As a policy analyst benchmarking NSF's SBIR program against published venture-capital performance metrics,**
I want Phase I→II graduation rates, 5-year survival proxies, and M&A exit rates computed for the NSF cohort and placed alongside NVCA/Howell/Lerner baselines with a reconciliation narrative, so that I can report how NSF SBIR performs relative to seed-stage private capital in a form suitable for OSTP or congressional briefings.

**As an entrepreneurial finance researcher studying whether SBIR awardees outperform comparable private-capital-financed firms,**
I want a covariate-matched control cohort of non-SBIR Form D issuers with outcome deltas computed against the NSF SBIR cohort, so that I can assess whether the SBIR treatment effect on commercialization holds after controlling for vintage, NAICS sector, and firm geography.

---

Research-questions tags: **B2/B3** (commercialization), **A4** (private-capital signals),
**[L21]** (ITIF "America's Seed Fund"), **[L10]** (Lerner), **[L11]** (Howell), **[L23]** (Form D).

## Background

ITIF [L21] frames NSF SBIR as the federal analogue of a seed-stage venture fund.
Lerner [L10] and Howell [L11] establish empirically that SBIR awardees grow
faster, attract more follow-on private capital, and produce more patents than
matched non-awardees — but neither study uses a *private-capital cohort* as the
control group. This spec builds that comparison for the configured funding agency,
with NSF as the initial implementation target: how does the SBIR portfolio of
the configured agency perform on commercialization-outcome metrics relative to
firms financed via private capital (Reg D / Form D filers)?

The user-stated framing: "compare NSF SBIR portfolio rank against pre-seed/seed
VCs." Per scope review, we drop the "rank" composite and frame the deliverable
as a **comparison table with reconciliation narrative**, matching the pattern
established by `specs/archive/completed-features/follow-on-multiplier-analysis/`. Form D is intentionally
*not* filtered to seed-only — its broader coverage (debt, later-stage, multiple
instrument types) is treated as feature, not bug, because the policy question
is "what private-capital alternative would these firms otherwise rely on,"
not "what would seed VCs alone do."

## Reuse Posture: PR #286

This spec was originally drafted under the assumption that EDGAR ingest, Form
D parsing, CIK resolution, and M&A signal extraction were all greenfield work.
That assumption was wrong. **PR #286 (`claude/sbir-ma-exit-analysis`) builds
all of that infrastructure** and was discovered mid-spec:

- `sbir_etl/enrichers/sec_edgar/{client,enricher,form_d_scoring}.py` — full
  EDGAR client (~1,800 lines), rate-limited (10 req/s SEC limit), checkpointed
- `sbir_etl/models/sec_edgar.py` — typed models for filings, mentions, Form D
- `packages/sbir-analytics/sbir_analytics/assets/sec_edgar_enrichment.py` —
  Dagster asset, with companion job
- `scripts/data/{fetch_form_d_index,fetch_form_d_details,detect_sbir_ma_events,
  refine_ma_medium_tier,analyze_sbir_ma_exits,analyze_form_d_tiers,
  explore_form_d_clusters,scan_sbir_edgar}.py` — pipeline scripts
- `data/sbir_ma_events.jsonl` — curated M&A events, confidence-tiered
- 3-layer CIK resolution (threshold + containment + distinctive-word) with
  city-co-occurrence disambiguation; 552 high-confidence Form D M&A signals,
  4,022 EFTS-mention candidates refined to 1,203 confirmed targets after
  directional text refinement (false-positive removal)
- Published findings in `docs/research/`: 8.1% SBIR M&A exit rate, 1.82x
  Form D-to-SBIR leverage ratio (high-confidence), agency stratification,
  top-acquirer landscape, serial-acquirer count

This spec **consumes** PR #286's outputs rather than reimplementing them.
Phase 2 collapses from "ingest + parse + crosswalk + cohort + compare" to
"filter to NSF + build control cohort + compute deltas".

## Phasing

This spec ships in two sequential phases, each independently useful.

- **Phase 1 — Published-baseline comparison.** Compute NSF SBIR cohort outcomes
  on metrics with cited public VC baselines. No new data ingest. Independent
  of PR #286.
- **Phase 2 — NSF-vs-private-capital matched cohort.** Consume PR #286
  artifacts to filter to NSF awardees, construct a non-SBIR Form D control
  cohort, and compute outcome deltas. Gated on PR #286 merging to main.

Phase 1 is the gating deliverable. Phase 2 starts after #286 merges and our
branch rebases on top.

## Phase 1 Requirements

1. **SHALL** isolate the cohort for the configured funding agency using that
   agency's ALN(s) (e.g. NSF uses ALN `47.041` and `47.084`). NSF is the
   initial implementation target.
2. **SHALL** compute the following cohort outcomes, stratified by award
   vintage (5-year buckets) and Phase (I, II):
   - Phase I → Phase II graduation rate
   - Phase II → first non-SBIR federal contract transition rate (reuse
     existing transition detector, ≥85% precision benchmark)
   - 5-year survival proxy (firm appears as recipient/vendor in any federal
     dataset 5 years post-Phase-II). Denominator is unique companies per
     stratum, not award rows.
   - M&A exit rate — reuses #286's `data/sbir_ma_events.jsonl` once that PR
     merges (was previously gated as "not-yet-available"). Agency-filtered
     slice is a one-line join. Join is UEI/DUNS-first; falls back to
     normalized company name when UEI/DUNS are absent.
   - Patent rate — **deferred to Phase 2**. The asset does not accept
     PATLINK as an input in Phase 1; adding PATLINK is out of scope here.
3. **SHALL** present results alongside cited public VC baselines:
   - Seed → Series A graduation (NVCA / CB Insights public summaries)
   - 5-year startup survival (BLS BED, public)
   - Exit rate at 5 / 10 years (NVCA, public)
   - Lerner [L10] and Howell [L11] published effect sizes
4. **SHALL** produce a reconciliation narrative explaining each delta between
   the cohort metric and the cited VC baseline, including selection-bias
   caveats ("NSF awardees pre-selected on technical merit and proposal
   quality; VC-financed firms self-select on lawyer access and growth
   narrative").
5. **SHOULD** stratify outcomes by CET technology area (reuse CET classifier)
   so the comparison is not blurred by sector mix.
6. **SHALL** report match rates and entity-resolution coverage as sensitivity
   metadata (mirrors `follow-on-multiplier-analysis` requirement 7).

### Phase 1 Gate Condition

Can produce a single artifact (notebook or markdown report) that states:
"NVCA reports seed→A graduation at ~30%. NSF Phase I→II graduation is [X]%
on cohort [vintage range, n=Y]. The difference is attributable to [Z]."
Reproduces the exact reconciliation pattern of `follow-on-multiplier-analysis`.

## Phase 2 Requirements

Phase 2 consumes PR #286 artifacts. None of the EDGAR/Form-D ingest or
parsing work belongs in this spec.

7. **SHALL** filter PR #286's SBIR↔EDGAR signal tables (`sec_edgar_enrichment`
   asset outputs and `data/sbir_ma_events.jsonl`) to the configured agency's
   SBIR awardees only (e.g. NSF: ALN 47.041 / 47.084).
8. **SHALL** construct a non-SBIR control cohort: Form D issuers in #286's
   index that are *not* matched to any SBIR awardee (CIK is not in the
   resolved SBIR-CIK set produced by #286). Bucket by issuer-reported
   vintage (filing year), NAICS-2, state.
9. **SHALL** match the agency cohort and control cohort on covariates: vintage
   year, NAICS-2, state. Coarsened-exact matching, no propensity scoring in
   v1. Document cohort sizes and balance.
10. **SHALL** compute Phase 1's outcome metrics on the matched control cohort
    where applicable: federal-contract presence (FPDS join), patent rate
    (PATLINK), M&A exit rate (#286's events table). Survival proxy and
    Phase-graduation rates do not apply to the control cohort and are
    reported as N/A.
11. **SHALL** publish a threats-to-validity section before any headline
    finding. Required entries: SAFE/convertible undercount, late-stage Form
    D inclusion, NAICS self-report noise, #286's CIK-resolution recall floor
    (~28% of SBIR companies appear in EDGAR per #286), technical-merit vs.
    lawyer-access selection bias, control-cohort exclusion of pre-Form-D
    SBIR awardees who later raised capital.
12. **SHOULD** decompose results by Form D security-type (equity / debt /
    option / convertible) and offering-size buckets so downstream readers
    can zoom in on the noisy seed-stage subset if they want. Use #286's
    Form D scoring tiers directly.
13. **SHOULD** reproduce #286's published 1.82x SBIR-to-Form-D leverage
    ratio scoped to the configured agency only, as a cross-check on the
    dataset slice.

### Phase 2 Gate Condition

Can state: "On vintage [X], NAICS-2 [Y], state [Z]: the configured agency's
Phase II awardees transitioned to federal contract at [A]% within 5 years;
matched non-SBIR Form D issuers transitioned at [B]%. Selection-bias and
matching caveats below." The reconciliation matters more than the headline
number.

## Dependencies

- NSF identification (ALN 47.041 / 47.084) — `sbir_etl/models/sbir_identification.py` (EXISTS)
- Transition detection (≥85% precision) — `packages/sbir-ml/sbir_ml/transition/` (EXISTS)
- Entity resolution cascade — UEI/DUNS/CAGE/fuzzy-name (EXISTS)
- PATLINK patent linkage (EXISTS)
- CET classifier (EXISTS, used for Phase 1 stratification)
- **PR #286** — provides EDGAR ingest, Form D parsing, CIK resolution, M&A
  event detection, Form D scoring tiers. Gates all of Phase 2. After merge,
  this branch must rebase on top of main.
- `VendorCrosswalk` — used by #286's CIK resolver. Spec authors should not
  modify it directly; if a CIK field is needed for downstream analysis,
  request it via the #286 owners or a follow-on PR rather than fork it here.

## Out of Scope

- Composite "portfolio rank" / scoring construct — explicitly rejected.
- Crunchbase / PitchBook integration (deferred to a future licensed-data spec).
- Causal-effect estimation. This spec is descriptive comparison only; any
  causal claims require IV / regression-discontinuity machinery beyond scope.
- Patent rate in Phase 1 — deferred to Phase 2 (the asset does not accept
  PATLINK as an input; adding it is out of scope for the current iteration).
- Re-implementation of any infrastructure delivered by PR #286. If a #286
  artifact is missing or wrong for our purposes, file an issue against the
  #286 follow-up; do not duplicate.
